"""Privacy and fixed-query checks for the one-shot read-only incident probe."""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "chat_diagnostics", Path(__file__).parents[1] / "scripts/chat_stream_diagnostics.py"
)
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)


def test_logs_emit_categories_and_allowlisted_locations_never_raw_values():
    raw = "\n".join(
        [
            "2026-10-26T04:43:01Z APITimeoutError: Bearer private-token user content here",
            '2026-10-26T04:44:16Z File "/app/api/chat_stream.py", line 76, in bounded_send',
            '2026-10-26T04:44:16Z File "/secret/private-user.py", line 8, in private_function',
            '2026-10-26T04:44:16Z 10.1.2.3 "POST /api/chat/stream HTTP/1.1" 499 0',
            "2026-10-26T04:44:16Z Chat transport exceeded the delivery deadline private-session",
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
        ("ours", "user", diag.QA_TEXT, "2026-10-26T04:43:01+00:00", {"request_id": request_id}),
        (
            "ours",
            "assistant",
            "",
            "2026-10-26T04:44:16+00:00",
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
            "2026-10-26T04:43:03+00:00",
            {"request_id": "other"},
        ),
        ("another", "user", "unrelated private prompt", "2026-10-26T04:43:02+00:00", {}),
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
            "2026-10-26T04:43:01+00:00",
            "2026-10-26T04:44:16+00:00",
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
        [sys.executable, "-c", "import time;time.sleep(10)"], stdin="x" * 100000, timeout=0.1
    )
    assert code == -2
