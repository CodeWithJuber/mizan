"""Explicit schema revision, pending evidence and stale-answer rejection.

No missing context is discovered here. A teacher supplies fields, values and
bindings. Pending history is retained but not used as existential constraints.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

from .finite_context import FiniteContextMemory, exact_text
from .learning import LearningError

FORMAT = 'context-revision-v1'


class RevisionedContextMemory:
    def __init__(self, ontology, senses):
        self._core = FiniteContextMemory(ontology, senses)
        initial = self._core.to_dict()
        self._initial = {'ontology': initial['ontology'], 'senses': initial['senses']}
        self._events = []
        self._pending = {}
        self._epoch = 0

    @classmethod
    def from_finite(cls, memory):
        state = memory.to_dict()
        result = cls(state['ontology'], state['senses'])
        for row in state['examples']:
            result.observe(row['language'], row['symbol'], row['id'], row['context'],
                           row['sense'], row['source'])
        return result

    def _apply(self, event):
        """Validate before mutation; only successful transitions enter the log."""
        event = deepcopy(event)
        kind = event.get('kind')
        required = {
            'observe': {'kind', 'language', 'symbol', 'id', 'context', 'sense', 'source'},
            'retract': {'kind', 'language', 'symbol', 'id', 'source'},
            'refine': {'kind', 'field', 'values', 'source'},
            'bind': {'kind', 'pending_id', 'additions', 'source'},
        }
        if kind not in required or set(event) != required[kind]:
            raise LearningError('Malformed revision event.')
        exact_text(event['source'], 'source')
        if kind == 'observe':
            detail = self._core.observe(event['language'], event['symbol'], event['id'],
                                        event['context'], event['sense'], event['source'])
        elif kind == 'retract':
            exact_text(event['id'], 'evidence ID')
            detail = self._core.retract(event['language'], event['symbol'], event['id'])
        elif kind == 'refine':
            field = exact_text(event['field'], 'field')
            state = self._core.to_dict()
            if field in state['ontology']:
                raise LearningError('Refinement may add a new field only; existing fields cannot be overwritten.')
            ontology = {**state['ontology'], field: event['values']}
            replacement = FiniteContextMemory(ontology, state['senses'])
            additions = {}
            for index, row in enumerate(state['examples']):
                pending_id = f'e{len(self._events)+1}-o{index}'
                additions[pending_id] = {'pending_id': pending_id, 'from_epoch': self._epoch,
                                         'observation': deepcopy(row),
                                         'refinement_source': event['source']}
            self._pending.update(additions)
            self._core = replacement
            self._epoch += 1
            detail = {'status': 'SCHEMA_REFINED', 'new_pending_count': len(additions)}
        else:
            pending_id = exact_text(event['pending_id'], 'pending evidence ID')
            if pending_id not in self._pending:
                raise LearningError('Unknown or already bound pending evidence.')
            prior = self._pending[pending_id]['observation']
            additions = event['additions']
            fields = set(self._core.to_dict()['ontology'])
            if not isinstance(additions, dict) or set(additions) != fields-set(prior['context']):
                raise LearningError('Binding must supply exactly the newly missing fields; old fields cannot change.')
            context = {**prior['context'], **additions}
            source = json.dumps({'original_source': prior['source'],
                                 'binding_source': event['source'],
                                 'pending_id': pending_id}, ensure_ascii=False, sort_keys=True)
            evidence_id = 'bound:' + pending_id
            detail = self._core.observe(prior['language'], prior['symbol'], evidence_id,
                                        context, prior['sense'], source)
            del self._pending[pending_id]
            detail['bound_evidence_id'] = evidence_id
        self._events.append(event)
        return {**detail, 'epoch': self._epoch, 'revision': len(self._events),
                'pending_count': len(self._pending), 'ledger_changed': True,
                'schema_changed': kind == 'refine', 'verified': False,
                'accepted_as_fact': False, 'context_changed': False}

    def observe(self, language, symbol, evidence_id, context, sense, source):
        return self._apply({'kind': 'observe', 'language': language, 'symbol': symbol,
                            'id': evidence_id, 'context': context, 'sense': sense, 'source': source})

    def retract(self, language, symbol, evidence_id, source):
        return self._apply({'kind': 'retract', 'language': language, 'symbol': symbol,
                            'id': evidence_id, 'source': source})

    def refine(self, field, values, source):
        return self._apply({'kind': 'refine', 'field': field, 'values': values, 'source': source})

    def pending(self):
        return deepcopy(list(self._pending.values()))

    def bind(self, pending_id, additions, source):
        return self._apply({'kind': 'bind', 'pending_id': pending_id,
                            'additions': additions, 'source': source})

    def state_sha256(self):
        encoded = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                             separators=(',', ':')).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

    def resolve(self, language, symbol, context):
        value = self._core.resolve(language, symbol, context)
        return {**value, 'ledger_format': FORMAT, 'epoch': self._epoch,
                'revision': len(self._events), 'state_sha256': self.state_sha256(),
                'pending_count': len(self._pending),
                'pending_policy': 'Inactive history until explicit source-linked context binding.'}

    def validate_receipt(self, receipt):
        base = {'verified': False, 'accepted_as_fact': False, 'context_changed': False}
        if not isinstance(receipt, dict) or receipt.get('ledger_format') != FORMAT:
            return {**base, 'status': 'INVALID_RECEIPT', 'valid': False}
        if receipt.get('state_sha256') != self.state_sha256():
            return {**base, 'status': 'STALE_RECEIPT', 'valid': False,
                    'reason': 'Evidence or schema changed; resolve again against current state.'}
        try:
            current = self.resolve(receipt['language'], receipt['symbol'], receipt['context'])
        except (KeyError, LearningError, TypeError):
            return {**base, 'status': 'INVALID_RECEIPT', 'valid': False}
        if current != receipt:
            return {**base, 'status': 'INVALID_RECEIPT', 'valid': False}
        return {**base, 'status': 'CURRENT_RECEIPT', 'valid': True,
                'note': 'Content matches this ledger state, not external truth or source authentication.'}

    def to_dict(self):
        return {'format': FORMAT, 'initial': deepcopy(self._initial),
                'events': deepcopy(self._events)}

    @classmethod
    def from_dict(cls, value):
        if (not isinstance(value, dict) or set(value) != {'format', 'initial', 'events'}
                or value['format'] != FORMAT or not isinstance(value['initial'], dict)
                or set(value['initial']) != {'ontology', 'senses'}
                or not isinstance(value['events'], list)):
            raise LearningError('Unsupported revision-ledger checkpoint.')
        result = cls(value['initial']['ontology'], value['initial']['senses'])
        for event in value['events']:
            if not isinstance(event, dict):
                raise LearningError('Revision events must be objects.')
            result._apply(event)
        return result

    def save(self, path):
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2)+'\n',
                              encoding='utf-8')

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))
