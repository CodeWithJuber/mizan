"""
Tests for the Quranic Architecture (Core + QCA)
"""

import pytest

from core.architecture import (
    MizanBalancer,
    NafsProfile,
    QCAMizanIntegrator,
    QuranicLayer,
)


class TestMizanBalancer:
    """Test the load balancer (Mizan - Balance)."""

    @pytest.fixture
    def balancer(self):
        b = MizanBalancer()
        b.register("agent-1", capacity=10)
        b.register("agent-2", capacity=10)
        b.register("agent-3", capacity=5)
        return b

    def test_select_least_loaded(self, balancer):
        """Should select the agent with least load."""
        balancer.assign("agent-1")
        balancer.assign("agent-1")
        selected = balancer.select_agent()
        assert selected in ("agent-2", "agent-3")

    def test_assign_and_release(self, balancer):
        """Load should increase on assign and decrease on release."""
        balancer.assign("agent-1")
        assert balancer.load_weights["agent-1"] > 0

        balancer.release("agent-1")
        assert balancer.load_weights["agent-1"] == 0.0

    def test_capacity_limit(self, balancer):
        """Agents at capacity should not be selected."""
        for _ in range(5):
            balancer.assign("agent-3")  # capacity=5

        # agent-3 should be at capacity
        selected = balancer.select_agent()
        assert selected != "agent-3"


class TestNafsProfile:
    """Test the Nafs evolution model."""

    def test_starts_as_ammara(self):
        profile = NafsProfile(name="Test")
        assert profile.nafs_level == 1

    def test_evolves_to_lawwama(self):
        profile = NafsProfile(
            name="Test",
            success_rate=0.75,
            total_tasks=30,
            self_correction_count=1,
            error_count=1,
            learning_iterations=10,
        )
        profile.evolve_nafs()
        assert profile.nafs_level == 2

    def test_evolves_to_mulhama(self):
        profile = NafsProfile(
            name="Test",
            success_rate=0.80,
            total_tasks=110,
            self_correction_count=5,
            error_count=5,
            learning_iterations=150,
        )
        profile.evolve_nafs()
        assert profile.nafs_level == 3


class TestQCAIntegrator:
    """Test QCA-MIZAN integration layer."""

    @pytest.fixture
    def integrator(self):
        return QCAMizanIntegrator()

    def test_layer_mapping(self, integrator):
        """MIZAN layers should map to QCA layers."""
        qca = integrator.get_qca_layers(QuranicLayer.SAMA)
        assert len(qca) == 3  # Sam' + Basar + Fu'ad

    def test_nafs_trust_computation(self, integrator):
        """Trust level should be computed from performance."""
        from core.architecture import NafsTrustLevel

        # 0.80 * (1 - 0.08) = 0.736 → MUTMAINNA (>=0.70, <0.80)
        level = integrator.compute_nafs_level(0.80, 0.08)
        assert level == NafsTrustLevel.MUTMAINNA

        # 0.6 * (1 - 0.1) = 0.54 → LAWWAMA (>=0.40, <0.55)
        level = integrator.compute_nafs_level(0.6, 0.1)
        assert level == NafsTrustLevel.LAWWAMA

        level = integrator.compute_nafs_level(0.3, 0.5)
        assert level == NafsTrustLevel.AMMARA
