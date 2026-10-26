"""Regression tests for cached Masalik network statistics."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from memory.masalik import MasalikNetwork, Silah


class TestMasalikStatsCache:
    @staticmethod
    def expected_stats(net):
        """Independent, uncached calculation of the public stats contract."""
        return {
            "total_concepts": len(net.concepts),
            "total_pathways": len(net.pathways),
            "fitrah_concepts": sum(1 for c in net.concepts.values() if c.is_fitrah),
            "hikmah_pathways": sum(1 for p in net.pathways.values() if p.is_hikmah),
            "hikmah_concepts": sum(1 for c in net.concepts.values() if c.is_hikmah),
            "avg_pathway_weight": round(
                sum(p.weight for p in net.pathways.values()) / max(len(net.pathways), 1),
                3,
            ),
            "persisted": net._persist_path,
        }

    def test_unchanged_graph_is_not_rescanned(self, tmp_path, monkeypatch):
        net = MasalikNetwork(persist_path=str(tmp_path / "m.json"))
        net.encode("alpha bravo charlie")

        calls = {"count": 0}
        original = Silah.is_hikmah.fget

        def counted_is_hikmah(self):
            calls["count"] += 1
            return original(self)

        monkeypatch.setattr(Silah, "is_hikmah", property(counted_is_hikmah))

        first = net.stats()
        assert calls["count"] == len(net.pathways)
        assert first == self.expected_stats(net)

        calls["count"] = 0
        second = net.stats()
        assert calls["count"] == 0
        assert second == first

    @pytest.mark.parametrize("operation", ["encode", "recall", "nisyan", "tafakkur"])
    def test_mutations_invalidate_cached_stats(self, tmp_path, monkeypatch, operation):
        net = MasalikNetwork(persist_path=str(tmp_path / "m.json"))
        if operation == "tafakkur":
            for text in (
                "alpha bravo charlie",
                "alpha bravo delta",
                "alpha bravo echo",
            ):
                net.encode(text)
        else:
            net.encode("alpha bravo charlie")

        # Populate the cache before instrumenting the hot property.
        net.stats()
        calls = {"count": 0}
        original = Silah.is_hikmah.fget

        def counted_is_hikmah(self):
            calls["count"] += 1
            return original(self)

        monkeypatch.setattr(Silah, "is_hikmah", property(counted_is_hikmah))

        net.stats()
        assert calls["count"] == 0

        if operation == "encode":
            net.encode("delta epsilon zeta")
        elif operation == "recall":
            net.recall("alpha")
        elif operation == "nisyan":
            net.apply_nisyan(force_hours=5000.0)
        else:
            net.tafakkur()

        calls["count"] = 0
        stats = net.stats()
        assert calls["count"] == len(net.pathways)
        assert stats == self.expected_stats(net)

    def test_callers_cannot_mutate_cached_stats(self, tmp_path):
        net = MasalikNetwork(persist_path=str(tmp_path / "m.json"))
        net.encode("alpha bravo charlie")

        first = net.stats()
        first["total_pathways"] = -1
        first["persisted"] = "caller mutation"

        second = net.stats()
        assert second is not first
        assert second == self.expected_stats(net)
