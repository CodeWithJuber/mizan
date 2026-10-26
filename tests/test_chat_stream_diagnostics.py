"""Privacy and fixed-query checks for the one-shot read-only incident probe."""

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location(
    "chat_diagnostics",
    Path(__file__).resolve().parents[1] / "scripts" / "chat_stream_diagnostics.py",
)
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


def fixture_timestamp(fraction: float) -> str:
    """Keep seeded rows and logs within the diagnostic's configured UTC window."""
    start = datetime.fromisoformat(diag.START.replace("Z", "+00:00"))
    end = datetime.fromisoformat(diag.END.replace("Z", "+00:00"))
    assert end > start and 0 < fraction < 1
    return (start + (end - start) * fraction).isoformat()


def test_logs_emit_categories_and_allowlisted_locations_never_raw_values():
    raw = "\n".join(
        [
            f"{fixture_timestamp(0.25)} APITimeoutError: Bearer private-token user content here",
            f'{fixture_timestamp(0.75)} File "/app/api/chat_stream.py", line 76, in bounded_send',
            f'{fixture_timestamp(0.75)} File "/secret/private-user.py", line 8, in private_function',
            f'{fixture_timestamp(0.75)} 10.1.2.3 "POST /api/chat/stream HTTP/1.1" 499 0',
            f"{fixture_timestamp(0.75)} Chat transport exceeded the delivery deadline private-session",
        ]
    )
    result = diag.summarize_logs(raw)
    assert result["categories"]["provider_timeout"] == 1
    assert result["categories"]["transport_deadline"] == 1
    assert result["chat_stream_http_status_counts"] == {"499": 1}
    assert result["stack_locations"] == [{"file": "api/chat_stream.py", "line": 76, "count": 1}]
    assert not any(
        secret in json.dumps(result)
        for secret in (
            "private-token",
            "user content",
            "private-user",
            "private_function",
            "10.1.2.3",
            "private-session",
        )
    )


def test_nginx_parser_never_returns_hostnames_headers_or_arbitrary_values():
    raw = """# configuration file /etc/nginx/private-host.conf:
server {
 server_name private.example;
 location /api/ {
  proxy_set_header Authorization "Bearer private-key";
  proxy_read_timeout 300s;
  proxy_buffering off;
  send_timeout $private_value;
 }
}
"""
    result = diag.nginx_directives(raw)
    assert [row["value"] for row in result] == ["300s", "off"]
    assert result[0]["scope"] == ["server", "location:/api/"]
    assert "private" not in json.dumps(result)


def test_database_reads_only_exact_qa_and_matching_request_without_writing(tmp_path):
    path = tmp_path / "fixture.db"
    request_id = "11111111-1111-4111-8111-111111111111"
    conn = sqlite3.connect(path)
    conn.executescript("""
CREATE TABLE agent_messages(session_id TEXT, role TEXT, content TEXT, created_at TEXT, metadata TEXT);
CREATE TABLE chat_stream_requests(owner_id TEXT,request_id TEXT,session_id TEXT,status TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE chat_sessions(session_id TEXT,owner_id TEXT);
""")
    rows = [
        (
            "ours",
            "user",
            diag.QA_TEXT,
            fixture_timestamp(0.25),
            {"request_id": request_id},
        ),
        (
            "ours",
            "assistant",
            "",
            fixture_timestamp(0.75),
            {
                "request_id": request_id,
                "status": "cancelled",
                "usage_incomplete": True,
                "answer_delivered": False,
                "code": "private-key",
                "private": "secret",
                "usage": {"input_tokens": 42, "calls": [{"model": "private-model"}]},
            },
        ),
        (
            "ours",
            "assistant",
            "unrelated private answer",
            fixture_timestamp(0.375),
            {"request_id": "other"},
        ),
        (
            "another",
            "user",
            "unrelated private prompt",
            fixture_timestamp(0.3125),
            {},
        ),
    ]
    conn.executemany(
        "INSERT INTO agent_messages VALUES(?,?,?,?,?)",
        [(*row[:4], json.dumps(row[4])) for row in rows],
    )
    conn.execute("INSERT INTO chat_sessions VALUES('ours','private-owner')")
    conn.execute(
        "INSERT INTO chat_stream_requests VALUES(?,?,?,?,?,?)",
        (
            "private-owner",
            request_id,
            "ours",
            "cancelled",
            fixture_timestamp(0.25),
            fixture_timestamp(0.75),
        ),
    )
    conn.commit()
    conn.close()
    before = path.read_bytes()
    result = diag.read_qa_db(path)
    assert path.read_bytes() == before
    assert len(result["matches"]) == 1
    message = result["matches"][0]["assistant"]
    assert len(message) == 1 and message[0]["content_length"] == 0
    assert message[0]["status"] == "cancelled"
    assert message[0]["code"] is None
    assert message[0]["usage_counters"]["input_tokens"] == 42
    assert result["matches"][0]["ledger"][0]["status"] == "cancelled"
    assert not any(
        secret in json.dumps(result)
        for secret in ("private", "unrelated", request_id, diag.QA_TEXT)
    )


def test_command_output_and_unconsumed_input_are_bounded():
    code, output, error, truncated = diag.run(
        [sys.executable, "-c", "print('x'*20000)"], maximum=100, timeout=2
    )
    assert code == -3 and truncated and len(output) + len(error) == 100
    code, _, _, _ = diag.run(
        [sys.executable, "-c", "import time;time.sleep(10)"],
        stdin="x" * 100000,
        timeout=0.1,
    )
    assert code == -2


def test_persisted_graph_count_is_read_only_and_never_returns_keys(tmp_path):
    db = tmp_path / "fixture.db"
    graph = tmp_path / "masalik_network.json"
    raw = json.dumps(
        {
            "concepts": {"private-concept": {}},
            "pathways": {"private-edge": {"private-value": "credential"}},
            "private-extra": "secret",
        }
    ).encode()
    graph.write_bytes(raw)
    result = diag.read_graph_counts(db)
    assert result == {
        "status": "counted",
        "bytes": len(raw),
        "concepts": 1,
        "pathways": 1,
    }
    assert graph.read_bytes() == raw
    assert "private" not in json.dumps(result)
    assert "credential" not in json.dumps(result)


def test_graph_limit_is_checked_before_json_parse_and_special_files_rejected(tmp_path, monkeypatch):
    graph = tmp_path / "masalik_network.json"
    db = tmp_path / "fixture.db"
    graph.write_bytes(b"x" * 65)
    monkeypatch.setattr(diag, "MAX_GRAPH_BYTES", 64)

    def no_parse(_):
        raise AssertionError("oversize file must not be parsed")

    monkeypatch.setattr(diag.json, "loads", no_parse)
    assert diag.read_graph_counts(db)["status"] == "over_size_limit"
    graph.unlink()
    graph.symlink_to(tmp_path / "private-absent-target")
    assert diag.read_graph_counts(db)["status"] == "unreadable"
    graph.unlink()
    diag.os.mkfifo(graph)
    assert diag.read_graph_counts(db)["status"] == "not_regular_file"


def test_missing_malformed_and_wrong_shape_graph_are_fixed_categories(tmp_path):
    db = tmp_path / "fixture.db"
    graph = tmp_path / "masalik_network.json"
    assert diag.read_graph_counts(db)["status"] == "missing"
    graph.write_text("{private-invalid}")
    assert diag.read_graph_counts(db)["status"] == "invalid_json"
    graph.write_text('{"concepts":[],"pathways":{}}')
    assert diag.read_graph_counts(db)["status"] == "invalid_structure"


def test_successful_unverified_receipt_and_only_authorized_environment_keys(
    monkeypatch,
):
    result = diag.metadata_receipt(
        json.dumps(
            {
                "status": "accepted",
                "completion_status": "unverified_answer",
                "answer_delivered": True,
                "task_verified": False,
                "usage": {"timings": {"other_execution_ms": 66927.5}},
                "private": "secret",
            }
        )
    )
    assert result["status"] == "accepted"
    assert result["completion_status"] == "unverified_answer"
    assert result["timings"]["other_execution_ms"] == 66927.5
    assert result["answer_delivered"] is True and result["task_verified"] is False
    assert "secret" not in json.dumps(result)
    alarms = []
    monkeypatch.setattr(diag, "signal", SimpleNamespace(alarm=alarms.append))
    reads = []

    class ProbeEnvironment:
        def get(self, key, default):
            reads.append(key)
            return {"DB_PATH": "/private/fixture.db", "MEM0_ENABLED": "TRUE"}[key]

    monkeypatch.setattr(diag, "os", SimpleNamespace(environ=ProbeEnvironment()))
    monkeypatch.setattr(diag.resource, "getrlimit", lambda _: (-1, -1))
    limits = []
    monkeypatch.setattr(diag.resource, "setrlimit", lambda key, value: limits.append((key, value)))
    monkeypatch.setattr(diag, "read_qa_db", lambda _: {"matches": []})
    monkeypatch.setattr(diag, "read_graph_counts", lambda _: {"status": "missing"})
    report = diag.child_report()
    assert reads == ["DB_PATH", "MEM0_ENABLED"]
    assert alarms == [12]
    assert limits == [(diag.resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))]
    assert report["mem0_enabled"] is True
    assert "/private" not in json.dumps(report)
