"""Recall optimization must preserve graph learning and traversal semantics."""

from copy import deepcopy
from dataclasses import asdict

import pytest

from memory.masalik import Mafhum, MasalikNetwork, Silah, extract_concepts


def legacy_recall(net, query, top_k=10):
    """Previous full-edge scan, retained as an independent equivalence oracle."""
    query_concepts = extract_concepts(query)
    if not query_concepts:
        return []
    activations = {}
    for concept in query_concepts:
        if concept in net.concepts:
            net.concepts[concept].fire(strength=1.0)
            activations[concept] = 1.0
    for wave in range(2):
        spread_factor = 0.6 if wave == 0 else 0.3
        new_activations = {}
        for concept, act_level in list(activations.items()):
            if act_level < 0.05:
                continue
            for pathway in net.pathways.values():
                other = None
                if pathway.source == concept:
                    other = pathway.target
                elif pathway.target == concept:
                    other = pathway.source
                if other is None:
                    continue
                spread = act_level * pathway.weight * spread_factor
                if spread > 0.01:
                    new_activations[other] = min(1.0, new_activations.get(other, 0.0) + spread)
                    pathway.strengthen(0.02)
        for concept, activation in new_activations.items():
            activations[concept] = min(1.0, activations.get(concept, 0.0) + activation)
            if concept in net.concepts:
                net.concepts[concept].fire(strength=activation)
    query_set = set(query_concepts)
    results = [
        (concept, activation)
        for concept, activation in activations.items()
        if concept not in query_set and activation > 0.05
    ]
    results.sort(key=lambda item: -item[1])
    return results[:top_k]


def snapshot(net):
    return {
        "concepts": {key: asdict(node) for key, node in net.concepts.items()},
        "pathways": {key: asdict(path) for key, path in net.pathways.items()},
    }


@pytest.fixture
def network(tmp_path, monkeypatch):
    monkeypatch.setenv("MIZAN_NLP_NATIVE_WSD", "false")
    monkeypatch.setattr("memory.masalik.time.time", lambda: 1_700_000_000.0)
    net = MasalikNetwork(persist_path=str(tmp_path / "graph.json"))
    net.encode("alpha beta gamma", importance=0.8)
    net.encode("gamma delta epsilon", importance=0.4)
    net.encode("alpha delta zeta", importance=0.6)
    return net


@pytest.mark.parametrize("query", ["alpha", "gamma alpha", "knowledge truth", "unknown", ""])
@pytest.mark.parametrize("top_k", [0, 2, 10])
def test_recall_matches_legacy_results_and_every_learning_update(network, query, top_k):
    reference = deepcopy(network)
    for _ in range(3):
        assert network.recall(query, top_k) == legacy_recall(reference, query, top_k)
        # Includes weights, co-activations, node activation/resting levels and
        # timestamps, so equal answers alone cannot mask changed learning.
        assert snapshot(network) == snapshot(reference)


def test_recall_observes_encode_consolidate_prune_and_reload(network):
    def compare():
        reference = deepcopy(network)
        assert network.recall("alpha gamma", 10) == legacy_recall(reference, "alpha gamma", 10)
        assert snapshot(network) == snapshot(reference)

    compare()
    network.encode("alpha theta iota", importance=0.9)
    compare()
    for concept in ["kappa", "lambda"]:
        network._get_or_create(concept)
    network._activation_history = [{"alpha", "kappa", "lambda"}] * 3
    assert network.tafakkur()["new_connections"] > 0
    compare()
    assert network.apply_nisyan(force_hours=100_000)["pruned_pathways"] > 0
    compare()
    assert network.save_to_disk()
    restored = MasalikNetwork(persist_path=network._persist_path)
    assert snapshot(restored) == snapshot(network)
    reference = deepcopy(restored)
    assert restored.recall("alpha gamma") == legacy_recall(reference, "alpha gamma")
    assert snapshot(restored) == snapshot(reference)


def test_recall_observes_replaced_removed_and_mutated_edges(network):
    network.recall("alpha")
    # Public mappings and mutable Silah endpoints existed before the index.
    # They must not leave stale adjacency or cause duplicate reinforcement.
    network.pathways["self-loop"] = Silah(source="alpha", target="alpha", weight=0.7)
    network.pathways["parallel-edge"] = Silah(source="alpha", target="beta", weight=0.4)
    network.pathways["alpha->beta"] = Silah(source="zeta", target="alpha", weight=0.2)
    network.pathways["alpha->gamma"].source = "epsilon"
    del network.pathways["delta->gamma"]
    reference = deepcopy(network)
    assert network.recall("alpha gamma") == legacy_recall(reference, "alpha gamma")
    assert snapshot(network) == snapshot(reference)


class CountedEdges(dict):
    """Count full-graph iteration without using machine-dependent time limits."""

    visited = 0

    def values(self):
        for value in super().values():
            self.visited += 1
            yield value

    def items(self):
        for item in super().items():
            self.visited += 1
            yield item


def test_recall_scans_all_edges_once_instead_of_once_per_activated_concept(network):
    names = [f"node{chr(97 + i)}zz" for i in range(20)]
    network.concepts = {name: Mafhum(id=name) for name in names}
    network.pathways = CountedEdges(
        {
            f"{source}->{target}": Silah(source=source, target=target, weight=0.7)
            for index, source in enumerate(names)
            for target in names[index + 1 :]
        }
    )
    reference = deepcopy(network)
    network.pathways.visited = reference.pathways.visited = 0
    assert network.recall(names[0]) == legacy_recall(reference, names[0])
    assert network.pathways.visited == len(network.pathways)
    assert reference.pathways.visited == len(reference.pathways) * (len(names) + 1)
    assert snapshot(network) == snapshot(reference)


def test_unknown_query_does_not_scan_or_mutate_unrelated_graph(network):
    network.pathways = CountedEdges(network.pathways)
    before = snapshot(network)
    network.pathways.visited = 0
    assert network.recall("unseenword") == []
    assert network.pathways.visited == 0
    assert snapshot(network) == before
