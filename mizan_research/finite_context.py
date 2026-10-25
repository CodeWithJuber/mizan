"""Exact entailment over all functions of an explicitly supplied finite context."""
from copy import deepcopy
from itertools import product
from pathlib import Path
import argparse
import hashlib
import json
from .learning import LearningError

FORMAT = 'finite-context-v1'
MAX_CELLS = 4096


def exact_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise LearningError(f'A nonempty {name} string is required.')
    return value  # Intentionally no normalization, case folding or trimming.


class FiniteContextMemory:
    """No cue-arity restriction; labels and completeness of the schema are supplied."""

    def __init__(self, ontology, senses):
        if not isinstance(ontology, dict) or len(ontology) > 8:
            raise LearningError('Context schema must be an object with at most eight fields.')
        if not isinstance(senses, (list, tuple)) or not 1 <= len(senses) <= 16:
            raise LearningError('Supply one to sixteen distinct senses.')
        self._senses = tuple(exact_text(s, 'sense') for s in senses)
        if len(set(self._senses)) != len(self._senses):
            raise LearningError('Sense identifiers must be distinct exact strings.')
        self._ontology = {}
        total = 1
        for field, values in ontology.items():
            exact_text(field, 'field')
            if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 16:
                raise LearningError('Each field needs one to sixteen distinct values.')
            values = tuple(exact_text(v, 'context value') for v in values)
            if len(set(values)) != len(values):
                raise LearningError('Context values must be distinct exact strings.')
            total *= len(values)
            if total > MAX_CELLS:
                raise LearningError('Declared finite domain exceeds the 4096-cell implementation limit.')
            self._ontology[field] = values
        self._fields = tuple(self._ontology)
        self._cells = tuple(product(*(self._ontology[f] for f in self._fields)))
        self._examples = {}
        schema = {'ontology': self._ontology, 'senses': self._senses}
        self._schema_sha256 = hashlib.sha256(json.dumps(schema, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def _key(self, language, symbol):
        return exact_text(language, 'language identifier'), exact_text(symbol, 'symbol identifier')

    def _context(self, context, complete=False):
        if not isinstance(context, dict) or set(context)-set(self._fields):
            raise LearningError('Context has unknown fields or is not an object.')
        if complete and set(context) != set(self._fields):
            raise LearningError('Observations require a complete declared context.')
        result = {}
        for field in self._fields:
            if field in context:
                value = exact_text(context[field], 'context value')
                if value not in self._ontology[field]:
                    raise LearningError('Context value is outside the supplied domain.')
                result[field] = value
        return result

    def _tuple(self, context):
        return tuple(context[f] for f in self._fields)

    def _dict(self, cell):
        return dict(zip(self._fields, cell))

    def _state(self, key):
        cells = {}
        for evidence_id, row in self._examples.get(key, {}).items():
            cell = self._tuple(row['context'])
            cells.setdefault(cell, {}).setdefault(row['sense'], []).append(evidence_id)
        conflicts = []
        for cell, labels in cells.items():
            if len(labels) > 1:
                conflicts.append({'context': self._dict(cell), 'labels': sorted(labels),
                    'evidence': [{'id': i, **deepcopy(self._examples[key][i])}
                                 for ids in labels.values() for i in sorted(ids)]})
        return cells, conflicts

    def observe(self, language, symbol, evidence_id, context, sense, source):
        key = self._key(language, symbol)
        evidence_id = exact_text(evidence_id, 'evidence ID')
        context = self._context(context, complete=True)
        sense = exact_text(sense, 'sense')
        source = exact_text(source, 'evidence source')
        if sense not in self._senses:
            raise LearningError('Observed sense is outside the supplied inventory.')
        if evidence_id in self._examples.get(key, {}):
            raise LearningError('Duplicate evidence ID; retract explicitly before replacement.')
        self._examples.setdefault(key, {})[evidence_id] = {'context': context, 'sense': sense, 'source': source}
        _, conflicts = self._state(key)
        return {'status': 'INCONSISTENT_EVIDENCE' if conflicts else 'OBSERVATION_RECORDED',
                'conflicts': conflicts, 'context_changed': False, 'accepted_as_fact': False}

    def retract(self, language, symbol, evidence_id):
        key = self._key(language, symbol)
        if evidence_id not in self._examples.get(key, {}):
            raise LearningError('Unknown evidence ID.')
        removed = self._examples[key].pop(evidence_id)
        if not self._examples[key]:
            del self._examples[key]
        return {'status': 'OBSERVATION_RETRACTED', 'removed': deepcopy(removed),
                'context_changed': False, 'accepted_as_fact': False}

    def _witness(self, cells, context, sense):
        default = self._senses[0]
        assignments = {cell: next(iter(labels)) for cell, labels in cells.items()}
        assignments[context] = sense
        overrides = [{'context': self._dict(cell), 'sense': assignments[cell]}
                     for cell in self._cells if cell in assignments and assignments[cell] != default]
        return {'context': self._dict(context), 'sense': sense,
                'function': {'default_sense': default, 'overrides': overrides}}

    def resolve(self, language, symbol, context):
        key = self._key(language, symbol)
        context = self._context(context)
        cells, conflicts = self._state(key)
        base = {'language': key[0], 'symbol': key[1], 'context': context,
                'schema_sha256': self._schema_sha256, 'domain_cells': len(self._cells),
                'observed_cells': len(cells), 'observation_count': len(self._examples.get(key, {})),
                'verified': False, 'accepted_as_fact': False, 'context_changed': False,
                'assumptions': 'All meanings are total deterministic functions of this supplied finite schema; active source labels and sense inventory are assumed correct.',
                'evidence_ids': sorted(self._examples.get(key, {}))}
        if conflicts:
            return {**base, 'status': 'INCONSISTENT_EVIDENCE', 'answered': False,
                    'possible_senses': [], 'witnesses': [], 'conflicts': conflicts,
                    'compatible_function_count': {'expression': '0'}}
        choices = [([context[f]] if f in context else self._ontology[f]) for f in self._fields]
        completions = tuple(product(*choices))
        support, unobserved = {}, []
        for cell in completions:
            options = cells[cell] if cell in cells else self._senses
            if cell not in cells:
                unobserved.append(cell)
            for sense in options:
                support.setdefault(sense, cell)
        possible = sorted(support)
        remaining = len(self._cells)-len(cells)
        result = {**base, 'possible_senses': possible, 'completion_count': len(completions),
                  'unobserved_completions': len(unobserved),
                  'compatible_function_count': {'base': len(self._senses), 'exponent': remaining,
                                                 'expression': f'{len(self._senses)}^{remaining}'},
                  'evidence_complete_for_query': not unobserved}
        if len(possible) == 1:
            return {**result, 'status': 'EVIDENCE_ENTAILED', 'answered': True,
                    'sense': possible[0], 'witnesses': [],
                    'entailment_basis': 'Supplied single-sense inventory' if unobserved else 'All compatible completions have supported equal labels'}
        witnesses = [self._witness(cells, support[s], s) for s in possible[:2]]
        differing = [f for f in self._fields if witnesses[0]['context'][f] != witnesses[1]['context'][f]]
        return {**result, 'status': 'AMBIGUOUS_FINITE_MEANING', 'answered': False,
                'witnesses': witnesses,
                'repair': {'unobserved_cell_count': len(unobserved),
                           'first_label_request': self._dict(unobserved[0]) if unobserved else None,
                           'witness_context_difference_fields': differing,
                           'note': 'A distinguishing observation or actual context may be needed; this is not a claim that one requested item resolves every ambiguity.'}}

    def to_dict(self):
        return {'format': FORMAT, 'ontology': {f: list(v) for f, v in self._ontology.items()},
                'senses': list(self._senses),
                'examples': [{'language': key[0], 'symbol': key[1], 'id': evidence_id, **deepcopy(row)}
                             for key, records in sorted(self._examples.items())
                             for evidence_id, row in sorted(records.items())]}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {'format','ontology','senses','examples'} or value['format'] != FORMAT:
            raise LearningError('Unsupported finite-context checkpoint.')
        if not isinstance(value['examples'], list):
            raise LearningError('Checkpoint examples must be an array.')
        memory = cls(value['ontology'], value['senses'])
        for row in value['examples']:
            if not isinstance(row, dict) or set(row) != {'language','symbol','id','context','sense','source'}:
                raise LearningError('Malformed checkpoint observation.')
            memory.observe(row['language'], row['symbol'], row['id'], row['context'], row['sense'], row['source'])
        return memory

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['resolve','observe','retract'])
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--language', required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--context', default='{}')
    parser.add_argument('--id')
    parser.add_argument('--sense')
    parser.add_argument('--source')
    args = parser.parse_args()
    try:
        memory = FiniteContextMemory.load(args.checkpoint)
        if args.action == 'resolve':
            result = memory.resolve(args.language, args.symbol, json.loads(args.context))
        elif args.action == 'observe':
            result = memory.observe(args.language, args.symbol, args.id, json.loads(args.context), args.sense, args.source)
            memory.save(args.checkpoint)
        else:
            result = memory.retract(args.language, args.symbol, args.id)
            memory.save(args.checkpoint)
    except (LearningError, ValueError, OSError) as error:
        print(json.dumps({'status':'INPUT_ERROR', 'error':str(error), 'answered':False,
                          'verified':False, 'accepted_as_fact':False}, ensure_ascii=False))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
