"""Exact finite entailment from separate, partially recorded episodes.

Each observation means EXISTS a completion with its sense. Query answers must
hold for ALL compatible functions and ALL query completions. No probability.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

from .finite_context import FiniteContextMemory, exact_text
from .learning import LearningError

FORMAT = 'existential-context-v1'
MAX_CELLS = 256
MAX_OBSERVATIONS = 256


class _Limit(Exception):
    pass


class ExistentialContextMemory:
    def __init__(self, ontology, senses, max_nodes=200000):
        self._schema = FiniteContextMemory(ontology, senses)
        if len(self._schema._cells) > MAX_CELLS:
            raise LearningError('Existential solver supports at most 256 context cells.')
        if type(max_nodes) is not int or not 1 <= max_nodes <= 1000000:
            raise LearningError('max_nodes must be an integer from 1 to 1000000.')
        self.max_nodes = max_nodes
        self._rows = {}
        self._events = []
        self._origin = None

    def observe(self, language, symbol, evidence_id, context, sense, source):
        key = self._schema._key(language, symbol)
        evidence_id = exact_text(evidence_id, 'evidence ID')
        context = self._schema._context(context)
        sense = exact_text(sense, 'sense')
        source = exact_text(source, 'source')
        if sense not in self._schema._senses:
            raise LearningError('Sense is outside supplied inventory.')
        current = self._rows.get(key, {})
        if evidence_id in current:
            raise LearningError('Duplicate evidence ID; retract before replacement.')
        if len(current) >= MAX_OBSERVATIONS:
            raise LearningError('At most 256 observations per language/symbol key.')
        row = {'context': context, 'sense': sense, 'source': source}
        self._rows.setdefault(key, {})[evidence_id] = row
        self._events.append({'kind': 'observe', 'language': language, 'symbol': symbol,
                             'id': evidence_id, **deepcopy(row)})
        return self._mutation('OBSERVATION_RECORDED')

    def retract(self, language, symbol, evidence_id, source):
        key = self._schema._key(language, symbol)
        evidence_id = exact_text(evidence_id, 'evidence ID')
        source = exact_text(source, 'source')
        if evidence_id not in self._rows.get(key, {}):
            raise LearningError('Unknown evidence ID.')
        del self._rows[key][evidence_id]
        if not self._rows[key]:
            del self._rows[key]
        self._events.append({'kind': 'retract', 'language': language,
                             'symbol': symbol, 'id': evidence_id, 'source': source})
        return self._mutation('OBSERVATION_RETRACTED')

    def _mutation(self, status):
        return {'status': status, 'revision': len(self._events), 'ledger_changed': True,
                'verified': False, 'accepted_as_fact': False, 'context_changed': False}

    def _completions(self, partial):
        return tuple(i for i, cell in enumerate(self._schema._cells)
                     if all(cell[self._schema._fields.index(f)] == v
                            for f, v in partial.items()))

    def _clauses(self, key):
        return [(self._completions(row['context']),
                 1 << self._schema._senses.index(row['sense']))
                for row in self._rows.get(key, {}).values()]

    def _solve(self, clauses, budget):
        """Complete witness branching; domain masks encode one sense per cell.

        A clause is satisfied when a cell is forced to its sense. A single
        remaining witness forces that cell. Otherwise every possible witness
        is searched; branches may overlap but omit no satisfying assignment.
        """
        initial = [(1 << len(self._schema._senses))-1] * len(self._schema._cells)

        def visit(domains):
            if budget['nodes'] >= self.max_nodes:
                raise _Limit
            budget['nodes'] += 1
            while True:
                changed = False
                unresolved = []
                for cells, bit in clauses:
                    if any(domains[c] == bit for c in cells):
                        continue
                    available = [c for c in cells if domains[c] & bit]
                    if not available:
                        return None
                    if len(available) == 1:
                        domains[available[0]] = bit
                        changed = True
                    else:
                        unresolved.append((available, bit))
                if not changed:
                    break
            if not unresolved:
                return [mask & -mask for mask in domains]
            cells, bit = min(unresolved, key=lambda clause: len(clause[0]))
            for cell in cells:
                branch = domains.copy()
                branch[cell] = bit
                found = visit(branch)
                if found is not None:
                    return found
            return None

        return visit(initial)

    def _witness(self, assignment, query_cells, sense):
        bit = 1 << self._schema._senses.index(sense)
        cell = next(c for c in query_cells if assignment[c] == bit)
        return {'context': self._schema._dict(self._schema._cells[cell]), 'sense': sense,
                'function': [{'context': self._schema._dict(c),
                              'sense': self._schema._senses[value.bit_length()-1]}
                             for c, value in zip(self._schema._cells, assignment)]}

    def resolve(self, language, symbol, context):
        key = self._schema._key(language, symbol)
        context = self._schema._context(context)
        clauses = self._clauses(key)
        query_cells = self._completions(context)
        base = {'language': language, 'symbol': symbol, 'context': context,
                'ledger_format': FORMAT, 'state_sha256': self.state_sha256(),
                'revision': len(self._events), 'domain_cells': len(self._schema._cells),
                'completion_count': len(query_cells), 'observation_count': len(clauses),
                'evidence_ids': sorted(self._rows.get(key, {})),
                'verified': False, 'accepted_as_fact': False, 'context_changed': False,
                'assumptions': 'Truthful separate episodic observations; a stable total deterministic function of a sufficient finite schema; correct supplied sense inventory.',
                'import_is_detached': self._origin is not None}
        budget = {'nodes': 0}
        try:
            if self._solve(clauses, budget) is None:
                return {**base, 'status': 'INCONSISTENT_EVIDENCE', 'answered': False,
                        'possible_senses': [], 'candidate_set_complete': True,
                        'witnesses': [], 'solver_nodes': budget['nodes']}
            supported = []
            for sense in self._schema._senses:
                bit = 1 << self._schema._senses.index(sense)
                model = self._solve([*clauses, (query_cells, bit)], budget)
                if model is not None:
                    supported.append((sense, model))
        except _Limit:
            return {**base, 'status': 'RESOURCE_LIMIT', 'answered': False,
                    'possible_senses': None, 'candidate_set_complete': False,
                    'witnesses': [], 'solver_nodes': budget['nodes'],
                    'reason': 'Exact search exhausted its node budget; no complete sense set established.'}
        possible = sorted(s for s, _ in supported)
        result = {**base, 'possible_senses': possible, 'candidate_set_complete': True,
                  'solver_nodes': budget['nodes']}
        if len(possible) == 1:
            return {**result, 'status': 'EVIDENCE_ENTAILED', 'answered': True,
                    'sense': possible[0], 'witnesses': [],
                    'entailment_basis': 'Every compatible total function and query completion agrees, conditional on the declared assumptions.'}
        witnesses = [self._witness(model, query_cells, sense)
                     for sense, model in sorted(supported)[:2]]
        return {**result, 'status': 'AMBIGUOUS_FINITE_MEANING', 'answered': False,
                'witnesses': witnesses}

    @classmethod
    def from_revision(cls, memory, source, *, pending_semantics, max_nodes=200000):
        """Detached, explicitly authorized existential reading of pending episodes.

        Pending rows are historical records, not assumed valid automatically.
        The caller asserts they are truthful separate episodes under this schema.
        Later changes to the source ledger do not synchronize this snapshot.
        """
        from .context_revision import RevisionedContextMemory
        if not isinstance(memory, RevisionedContextMemory):
            raise LearningError('A RevisionedContextMemory instance is required.')
        source = exact_text(source, 'episodic interpretation source')
        if pending_semantics != 'episodic_exists':
            raise LearningError('Explicit pending_semantics=episodic_exists is required.')
        state = memory._core.to_dict()
        result = cls(state['ontology'], state['senses'], max_nodes)
        result._origin = {'revision_state_sha256': memory.state_sha256(),
                          'source': source, 'pending_semantics': pending_semantics,
                          'mode': 'detached_snapshot'}
        for row in state['examples']:
            result.observe(row['language'], row['symbol'], 'active:'+row['id'],
                           row['context'], row['sense'], row['source'])
        for pending in memory.pending():
            row = pending['observation']
            provenance = json.dumps({'original_source': row['source'],
                                      'interpretation_source': source,
                                      'pending_id': pending['pending_id']}, sort_keys=True,
                                     ensure_ascii=False)
            result.observe(row['language'], row['symbol'], 'pending:'+pending['pending_id'],
                           row['context'], row['sense'], provenance)
        return result

    def to_dict(self):
        state = self._schema.to_dict()
        return {'format': FORMAT, 'ontology': state['ontology'], 'senses': state['senses'],
                'max_nodes': self.max_nodes, 'origin': deepcopy(self._origin),
                'events': deepcopy(self._events)}

    @classmethod
    def from_dict(cls, value):
        fields = {'format', 'ontology', 'senses', 'max_nodes', 'origin', 'events'}
        if not isinstance(value, dict) or set(value) != fields or value['format'] != FORMAT:
            raise LearningError('Unsupported existential checkpoint.')
        origin = value['origin']
        if origin is not None:
            if (not isinstance(origin, dict) or set(origin) != {'revision_state_sha256', 'source', 'pending_semantics', 'mode'}
                    or origin['pending_semantics'] != 'episodic_exists' or origin['mode'] != 'detached_snapshot'
                    or not isinstance(origin['revision_state_sha256'], str)
                    or len(origin['revision_state_sha256']) != 64
                    or any(c not in '0123456789abcdef' for c in origin['revision_state_sha256'])):
                raise LearningError('Malformed import provenance.')
            exact_text(origin['source'], 'source')
        if not isinstance(value['events'], list):
            raise LearningError('Events must be an array.')
        result = cls(value['ontology'], value['senses'], value['max_nodes'])
        result._origin = deepcopy(origin)
        for event in value['events']:
            if not isinstance(event, dict):
                raise LearningError('Malformed event.')
            kind = event.get('kind')
            common = {'kind', 'language', 'symbol', 'id', 'source'}
            if kind == 'observe' and set(event) == common | {'context', 'sense'}:
                result.observe(event['language'], event['symbol'], event['id'],
                               event['context'], event['sense'], event['source'])
            elif kind == 'retract' and set(event) == common:
                result.retract(event['language'], event['symbol'], event['id'], event['source'])
            else:
                raise LearningError('Malformed event fields or kind.')
        return result

    def state_sha256(self):
        return hashlib.sha256(json.dumps(self.to_dict(), ensure_ascii=False,
                             sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def validate_receipt(self, receipt):
        base = {'verified': False, 'accepted_as_fact': False, 'context_changed': False}
        if not isinstance(receipt, dict) or receipt.get('ledger_format') != FORMAT:
            return {**base, 'status': 'INVALID_RECEIPT', 'valid': False}
        if receipt.get('state_sha256') != self.state_sha256():
            return {**base, 'status': 'STALE_RECEIPT', 'valid': False}
        try:
            current = self.resolve(receipt['language'], receipt['symbol'], receipt['context'])
        except (KeyError, TypeError, LearningError):
            return {**base, 'status': 'INVALID_RECEIPT', 'valid': False}
        valid = current == receipt
        return {**base, 'status': 'CURRENT_RECEIPT' if valid else 'INVALID_RECEIPT',
                'valid': valid, 'note': 'Local snapshot consistency only; not source authentication or parent-ledger freshness.'}

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))
