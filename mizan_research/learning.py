"""Finite candidate elimination with abstention, provenance and reversible teaching.

No candidate weights, probability distributions or neural network are used.
The hypothesis class and the structured meaning of teaching examples are inputs.
"""
from itertools import product, permutations
from collections import Counter
from dataclasses import dataclass

class LearningError(ValueError):
    pass

class ConceptLearner:
    def __init__(self, dimensions):
        self.dimensions = {k: tuple(v) for k, v in dimensions.items()}
        self.keys = tuple(self.dimensions)
        self.hypotheses = tuple(product(*[(None, *self.dimensions[k]) for k in self.keys]))
        self.examples = {}

    def _validate(self, features):
        if set(features) != set(self.keys):
            raise LearningError('A complete structured feature observation is required.')
        if any(features[k] not in self.dimensions[k] for k in self.keys):
            raise LearningError('Observation contains a value outside the declared ontology.')

    def holds(self, hypothesis, features):
        return all(v is None or features[k] == v for k, v in zip(self.keys, hypothesis))

    def candidates(self):
        return tuple(h for h in self.hypotheses if all(self.holds(h, e['features']) == e['label'] for e in self.examples.values()))

    def teach(self, example_id, features, label, source='explicit teaching'):
        self._validate(features)
        if type(label) is not bool:
            raise LearningError('A teaching label must be explicitly true or false.')
        if example_id in self.examples:
            raise LearningError('Duplicate example id; retract the old evidence explicitly.')
        before = len(self.candidates())
        self.examples[example_id] = {'features': dict(features), 'label': label, 'source': source}
        after = len(self.candidates())
        return {'before': before, 'after': after, 'status': 'INCONSISTENT_TEACHING' if not after else 'UPDATED'}

    def retract(self, example_id):
        if example_id not in self.examples:
            raise LearningError('Unknown teaching id.')
        del self.examples[example_id]

    def classify(self, features):
        self._validate(features)
        candidates = self.candidates()
        if not candidates:
            return {'status': 'INCONSISTENT_TEACHING', 'candidate_count': 0}
        values = {self.holds(h, features) for h in candidates}
        status = 'TRUE' if values == {True} else 'FALSE' if values == {False} else 'UNDETERMINED'
        return {'status': status, 'candidate_count': len(candidates), 'possible_answers': sorted(values)}

    def next_example(self):
        """Minimize the worst-case surviving hypothesis count; no probability prior."""
        hs = self.candidates()
        if len(hs) < 2:
            return None
        options = []
        for xs in product(*(self.dimensions[k] for k in self.keys)):
            obj = dict(zip(self.keys, xs))
            yes = sum(self.holds(h, obj) for h in hs)
            no = len(hs) - yes
            if yes and no:
                options.append((max(yes, no), xs, yes, no))
        if not options:
            return None
        worst, xs, yes, no = min(options)
        return {'features': dict(zip(self.keys, xs)), 'survivors_if_true': yes, 'survivors_if_false': no, 'worst_case_survivors': worst}

    def meanings(self):
        return [{k: v for k, v in zip(self.keys, h) if v is not None} for h in self.candidates()]

    def to_dict(self):
        return {'dimensions': {k: list(v) for k, v in self.dimensions.items()}, 'examples': self.examples}

    @classmethod
    def from_dict(cls, value):
        obj = cls(value['dimensions'])
        for key, example in value['examples'].items():
            obj.teach(key, example['features'], example['label'], example['source'])
        return obj


@dataclass(frozen=True)
class GrammarHypothesis:
    # mapping is aligned with the learner's token inventory; order indexes event fields.
    mapping: tuple
    order: tuple


class GrammarLearner:
    """Jointly learn an unknown bijective lexicon and a three-role word order.

    Roles are action, agent, patient. Concepts, entity/action categories, token
    boundaries and paired event supervision are supplied, not inferred from pixels.
    """
    def __init__(self, tokens, entities, actions):
        self.tokens = tuple(tokens)
        self.entities = tuple(entities)
        self.actions = tuple(actions)
        self.concepts = self.entities + self.actions
        if len(set(self.tokens)) != len(self.tokens) or len(self.tokens) != len(self.concepts):
            raise LearningError('A unique token inventory matching the concept count is required.')
        self.token_index = {t: i for i, t in enumerate(self.tokens)}
        self.hypotheses = tuple(GrammarHypothesis(m, o) for m in permutations(self.concepts) for o in permutations(range(3)))
        self.examples = {}
        self._candidates = self.hypotheses

    def _event(self, event):
        event = tuple(event)
        if len(event) != 3 or event[0] not in self.actions or event[1] not in self.entities or event[2] not in self.entities:
            raise LearningError('The supplied event is outside the declared role ontology.')
        return event

    def _tokens(self, utterance):
        ts = tuple(utterance.split()) if isinstance(utterance, str) else tuple(utterance)
        if len(ts) != 3 or any(t not in self.token_index for t in ts):
            raise LearningError('Expected three known, whitespace-separated symbol tokens.')
        return ts

    def interpret_under(self, hypothesis, utterance):
        out = [None] * 3
        for token, role in zip(utterance, hypothesis.order):
            out[role] = hypothesis.mapping[self.token_index[token]]
        return tuple(out)

    def teach(self, example_id, utterance, event):
        ts, ev = self._tokens(utterance), self._event(event)
        if example_id in self.examples:
            raise LearningError('Duplicate grammar teaching id.')
        before = len(self._candidates)
        self.examples[example_id] = (ts, ev)
        self._candidates = tuple(h for h in self._candidates if self.interpret_under(h, ts) == ev)
        return {'before': before, 'after': len(self._candidates), 'status': 'UPDATED' if self._candidates else 'INCONSISTENT_TEACHING'}

    def retract(self, example_id):
        if example_id not in self.examples:
            raise LearningError('Unknown grammar teaching id.')
        del self.examples[example_id]
        self._candidates = tuple(h for h in self.hypotheses if all(self.interpret_under(h, ts) == ev for ts, ev in self.examples.values()))

    def parse(self, utterance):
        try:
            ts = self._tokens(utterance)
        except LearningError as e:
            return {'status': 'UNSUPPORTED', 'detail': str(e), 'meanings': []}
        if not self._candidates:
            return {'status': 'INCONSISTENT_TEACHING', 'meanings': []}
        # Do not silently discard a surviving grammar merely because this new
        # utterance is ill-typed under it. That is a distinct possible outcome.
        values = {self.interpret_under(h, ts) for h in self._candidates}
        valid = sorted(v for v in values if v[0] in self.actions and v[1] in self.entities and v[2] in self.entities)
        invalid = len(values) - len(valid)
        return {'status': 'RESOLVED' if len(valid) == 1 and invalid == 0 else 'TYPE_ERROR' if not valid else 'AMBIGUOUS', 'meanings': [list(v) for v in valid], 'invalid_interpretations': invalid, 'candidate_grammars': len(self._candidates)}

    def generate_under(self, hypothesis, event):
        reverse = dict(zip(hypothesis.mapping, self.tokens))
        return ' '.join(reverse[event[role]] for role in hypothesis.order)

    def generate(self, event):
        ev = self._event(event)
        if not self._candidates:
            return {'status': 'INCONSISTENT_TEACHING', 'utterances': []}
        values = sorted({self.generate_under(h, ev) for h in self._candidates})
        return {'status': 'RESOLVED' if len(values) == 1 else 'AMBIGUOUS', 'utterances': values}

    def next_event(self):
        if len(self._candidates) < 2:
            return None
        options = []
        for ev in product(self.actions, self.entities, self.entities):
            groups = Counter(self.generate_under(h, ev) for h in self._candidates)
            if len(groups) > 1:
                options.append((max(groups.values()), ev, len(groups)))
        if not options:
            return None
        worst, ev, groups = min(options)
        return {'event': list(ev), 'possible_utterances': groups, 'worst_case_survivors': worst}

    def to_dict(self):
        return {'tokens': list(self.tokens), 'entities': list(self.entities), 'actions': list(self.actions), 'examples': {k: {'utterance': list(v[0]), 'event': list(v[1])} for k, v in self.examples.items()}}

    @classmethod
    def from_dict(cls, value):
        obj = cls(value['tokens'], value['entities'], value['actions'])
        for key, e in value['examples'].items():
            obj.teach(key, e['utterance'], e['event'])
        return obj

