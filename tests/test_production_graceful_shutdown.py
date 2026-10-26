"""Verify the production entrypoint and real Uvicorn stream drain on SIGTERM."""

import http.client
import importlib
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

REPO = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO / "docker/Dockerfile.backend.prod"


def entrypoint(tmp_path):
    source = DOCKERFILE.read_text().split("COPY <<'ENTRYPOINT' /entrypoint.sh\n", 1)[1]
    source = source.split("\nENTRYPOINT\n", 1)[0]
    path = tmp_path / "entrypoint.sh"
    path.write_text(source)
    return path


def environment():
    result = {
        key: value
        for key, value in os.environ.items()
        if key not in {"MIZAN_GRACEFUL_SHUTDOWN_SECONDS", "UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN"}
    }
    return result | {"SECRET_KEY": "synthetic-entrypoint-fixture", "PYTHONUNBUFFERED": "1"}


@pytest.mark.parametrize("value", ["9", "181", "090", "90.0", "", "private-mistaken-value"])
def test_entrypoint_rejects_unbounded_grace_without_starting_process(tmp_path, value):
    result = subprocess.run(
        ["bash", str(entrypoint(tmp_path)), sys.executable, "-c", "print('PROCESS_STARTED')"],
        env=environment() | {"MIZAN_GRACEFUL_SHUTDOWN_SECONDS": value},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 1
    assert "PROCESS_STARTED" not in result.stdout
    assert "synthetic-entrypoint-fixture" not in result.stdout + result.stderr
    assert "private-mistaken-value" not in result.stdout + result.stderr


@pytest.mark.parametrize("value,expected", [(None, "90"), ("10", "10"), ("180", "180")])
def test_entrypoint_exports_supported_uvicorn_deadline(tmp_path, value, expected):
    env = environment()
    if value is not None:
        env["MIZAN_GRACEFUL_SHUTDOWN_SECONDS"] = value
    result = subprocess.run(
        [
            "bash",
            str(entrypoint(tmp_path)),
            sys.executable,
            "-c",
            "import os; print('DEADLINE=' + os.environ['UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN'])",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    assert f"DEADLINE={expected}" in result.stdout


def test_installed_uvicorn_click_reads_exact_environment_setting(monkeypatch):
    main = importlib.import_module("uvicorn.main")
    observed = {}
    monkeypatch.setattr(main, "run", lambda *args, **kwargs: observed.update(kwargs))
    result = CliRunner().invoke(
        main.main, ["unused_fixture:app"], env={"UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN": "27"}
    )
    assert result.exit_code == 0, result.output
    assert observed["timeout_graceful_shutdown"] == 27


ASGI_APP = """
import asyncio, os
from pathlib import Path
async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        while True:
            message = await receive()
            if message['type'] == 'lifespan.startup':
                await send({'type': 'lifespan.startup.complete'})
            else:
                await send({'type': 'lifespan.shutdown.complete'})
                return
    await send({'type': 'http.response.start', 'status': 200,
                'headers': [(b'content-type', b'text/event-stream')]})
    await send({'type': 'http.response.body', 'body': b'started\\n', 'more_body': True})
    try:
        await asyncio.sleep(float(os.environ['FIXTURE_STREAM_SECONDS']))
        await send({'type': 'http.response.body', 'body': b'finished\\n', 'more_body': False})
        Path(os.environ['FIXTURE_OUTCOME']).write_text('completed')
    except asyncio.CancelledError:
        Path(os.environ['FIXTURE_OUTCOME']).write_text('cancelled')
        raise
"""


@pytest.mark.skipif(
    os.name != "posix", reason="Production uses Linux signals and inherited sockets"
)
@pytest.mark.parametrize("stream_seconds,expected", [(0.4, "completed"), (60, "cancelled")])
def test_real_sigterm_drains_short_stream_and_bounds_long_stream(
    tmp_path, stream_seconds, expected
):
    (tmp_path / "drain_fixture.py").write_text(ASGI_APP)
    outcome = tmp_path / "outcome"
    grace = 10  # Minimum supported runtime setting, not a 90-second test sleep.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=grace + 8)
    process = None
    try:
        with (tmp_path / "uvicorn.log").open("wb") as log:
            process = subprocess.Popen(
                [
                    "bash",
                    str(entrypoint(tmp_path)),
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "drain_fixture:app",
                    "--fd",
                    str(listener.fileno()),
                    "--loop",
                    "asyncio",
                    "--http",
                    "h11",
                    "--lifespan",
                    "on",
                    "--no-access-log",
                ],
                env=environment()
                | {
                    "PYTHONPATH": str(tmp_path),
                    "MIZAN_GRACEFUL_SHUTDOWN_SECONDS": str(grace),
                    "FIXTURE_STREAM_SECONDS": str(stream_seconds),
                    "FIXTURE_OUTCOME": str(outcome),
                },
                cwd=tmp_path,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                pass_fds=(listener.fileno(),),
                start_new_session=True,
            )
            listener.close()
            connection.request("GET", "/stream")
            response = connection.getresponse()
            assert response.status == 200
            assert response.readline() == b"started\n"
            started = time.monotonic()
            process.send_signal(signal.SIGTERM)
            if expected == "completed":
                assert response.read() == b"finished\n"
            else:
                with pytest.raises(http.client.IncompleteRead):
                    response.read()
            process.wait(timeout=grace + 8)
            elapsed = time.monotonic() - started
            assert outcome.read_text() == expected
            assert process.returncode in (0, -signal.SIGTERM)
            if expected == "completed":
                assert elapsed < grace
            else:
                assert grace - 1 <= elapsed < grace + 8
    finally:
        connection.close()
        listener.close()
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def test_compose_default_matches_application_grace_plus_exit_margin():
    compose = (REPO / "docker-compose.prod.yml").read_text()
    assert "stop_grace_period: 105s" in compose
    assert "MIZAN_GRACEFUL_SHUTDOWN_SECONDS=90" in compose
