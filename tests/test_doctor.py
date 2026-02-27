"""
Tests for MIZAN Doctor — Self-Healing Diagnostic System
========================================================
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from doctor import (
    CheckStatus,
    DoctorReport,
    check_core_imports,
    check_data_directory,
    check_database,
    check_dependencies,
    check_env_file,
    check_masalik_memory,
    check_port,
    check_python_version,
    check_secret_key,
    format_report_plain,
    report_to_dict,
    run_doctor,
)


class TestIndividualChecks:
    def test_python_version_passes(self):
        result = check_python_version()
        # We're running Python 3.11+
        assert result.status == CheckStatus.PASS
        assert "3." in result.message

    def test_dependencies_pass(self):
        result = check_dependencies()
        assert result.status == CheckStatus.PASS

    def test_core_imports_runs(self):
        result = check_core_imports()
        # May pass or fail depending on environment, but should not crash
        assert result.status in (CheckStatus.PASS, CheckStatus.FAIL)
        assert "module" in result.message.lower()

    def test_masalik_memory_passes(self):
        result = check_masalik_memory()
        assert result.status == CheckStatus.PASS
        assert "fitrah" in result.message
        assert "pathways" in result.message

    def test_database_passes(self):
        result = check_database()
        assert result.status == CheckStatus.PASS
        assert "SQLite OK" in result.message

    def test_port_available(self):
        # Test an unlikely port
        result = check_port(59999, "Test")
        assert result.status == CheckStatus.PASS


class TestEnvFileCheck:
    def test_missing_env_no_fix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("doctor._get_project_root", return_value=Path(tmpdir)):
                result = check_env_file(auto_fix=False)
                assert result.status == CheckStatus.FAIL

    def test_missing_env_auto_fix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create .env.example so fix can work
            (tmppath / ".env.example").write_text("ANTHROPIC_API_KEY=\nSECRET_KEY=change-this")

            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_env_file(auto_fix=True)
                assert result.status == CheckStatus.FIXED
                assert (tmppath / ".env").exists()

    def test_existing_env_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-test-key-123456")

            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_env_file()
                assert result.status == CheckStatus.PASS


class TestSecretKeyCheck:
    def test_default_key_warns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / ".env").write_text("SECRET_KEY=change-this-to-a-secure-random-string")

            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_secret_key(auto_fix=False)
                assert result.status == CheckStatus.WARN

    def test_default_key_auto_fix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / ".env").write_text("SECRET_KEY=change-this-to-a-secure-random-string")

            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_secret_key(auto_fix=True)
                assert result.status == CheckStatus.FIXED
                # Verify the key was actually replaced
                content = (tmppath / ".env").read_text()
                assert "change-this-to-a-secure-random-string" not in content
                assert len(content) > 20

    def test_custom_key_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / ".env").write_text("SECRET_KEY=my-custom-secure-key-abc123")

            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_secret_key()
                assert result.status == CheckStatus.PASS


class TestDataDirectoryCheck:
    def test_missing_data_dir_auto_fix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_data_directory(auto_fix=True)
                assert result.status == CheckStatus.FIXED
                assert (tmppath / "data").exists()

    def test_existing_data_dir_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "data").mkdir()

            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_data_directory()
                assert result.status == CheckStatus.PASS


class TestDoctorReport:
    def test_full_doctor_runs(self):
        report = run_doctor(auto_fix=False, check_only=True)
        assert isinstance(report, DoctorReport)
        assert len(report.checks) > 10

    def test_report_counts(self):
        report = run_doctor(check_only=True)
        total = report.passed + report.warnings + report.failures + report.fixes_applied
        skipped = sum(1 for c in report.checks if c.status == CheckStatus.SKIP)
        assert total + skipped == len(report.checks)

    def test_format_plain(self):
        report = run_doctor(check_only=True)
        text = format_report_plain(report)
        assert "MIZAN Doctor" in text
        assert "passed" in text

    def test_report_to_dict(self):
        report = run_doctor(check_only=True)
        d = report_to_dict(report)
        assert "healthy" in d
        assert "checks" in d
        assert isinstance(d["checks"], list)
        assert all("name" in c and "status" in c for c in d["checks"])


class TestDoctorAutoFix:
    def test_auto_fix_creates_data_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            with patch("doctor._get_project_root", return_value=tmppath):
                result = check_data_directory(auto_fix=True)
                assert result.status == CheckStatus.FIXED
                assert (tmppath / "data").is_dir()
