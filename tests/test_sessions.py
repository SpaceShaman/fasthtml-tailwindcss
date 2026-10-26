import concurrent.futures
import copy
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fasthtml_tailwindcss import _client


def test_once_build_survives_reload(project, application):
    app, head = application()
    with TestClient(app) as client:
        assert ".p-4{" in client.get("/").text
        output = head._session.output
        original = output.read_bytes()
        timestamp = output.stat().st_mtime_ns
        assert copy.deepcopy(head) is head
    (project / "components.py").write_text('classes = "text-7xl"\n')
    app, head = application()
    with TestClient(app) as client:
        assert head._session.output == output
        assert output.stat().st_mtime_ns == timestamp
        assert output.read_bytes() == original
        assert "text-7xl" not in client.get("/").text


def test_watch_rebuilds_and_survives_reload(project, application):
    app, head = application(watch=True)
    with TestClient(app) as client:
        output = head._session.output
        assert ".p-4" in client.get("/").text
        (project / "components.py").write_text('classes = "text-7xl"\n')
        deadline = time.monotonic() + 10
        while ".text-7xl" not in output.read_text():
            assert time.monotonic() < deadline, "Watcher did not rebuild"
            time.sleep(0.05)
        assert ".text-7xl" in client.get("/").text
    before = output.stat().st_mtime_ns
    app, head = application(watch=True)
    with TestClient(app):
        assert head._session.output == output
        assert output.stat().st_mtime_ns == before


@pytest.mark.parametrize("watch", [True, False])
def test_immediate_restart_with_changed_watch(project, watch):
    import json
    import subprocess
    import sys

    script = """import json, sys
from pathlib import Path
from fasthtml.common import FastHTML
from fasthtml_tailwindcss import TailwindHead, _client
_client.user_cache_path = lambda *args, **kwargs: Path("cache").resolve()
head = TailwindHead(watch=sys.argv[1] == "True", sources=["components.py"])
app = FastHTML(hdrs=[head], sess_cls=None)
print(json.dumps(str(head._session.directory)))
"""

    def start(mode):
        result = subprocess.run(
            [sys.executable, "-c", script, str(mode)],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return Path(json.loads(result.stdout))

    previous = start(watch)
    assert _client.running(previous)
    (project / "components.py").write_text('classes = "text-7xl"\n')
    current = start(not watch)
    assert current != previous
    assert ".text-7xl" in (current / "style.css").read_text()
    assert _client.running(previous)
    assert _client.running(current)


def test_concurrent_workers_share_one_build(project):
    config = _client.configuration(
        watch=False, sources=["components.py"], input=None, css=None
    )
    sessions = [_client.Session(config) for _ in range(4)]
    with concurrent.futures.ThreadPoolExecutor() as pool:
        list(pool.map(lambda s: s.connect(), sessions))
    assert len({s.output for s in sessions}) == 1
    directory = _client.cache_directory(config)
    assert (directory / "config.json").is_file()
    assert int((directory / "pid").read_text()) > 0
