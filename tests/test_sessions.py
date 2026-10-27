import concurrent.futures
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fasthtml_tailwindcss import client, config


def test_watch_rebuilds_and_survives_reload(project, application):
    app, head = application(watch=True)
    with TestClient(app) as client:
        output = head._session.output
        initial_page = client.get("/").text
        assert "/static/tailwind.css?v=" in initial_page
        assert ".p-4 " in output.read_text()
        (project / "components.py").write_text('classes = "text-7xl"\n')
        deadline = time.monotonic() + 10
        while ".text-7xl" not in output.read_text():
            assert time.monotonic() < deadline, "Watcher did not rebuild"
            time.sleep(0.05)
        updated_page = client.get("/").text
        assert ".text-7xl " in output.read_text()
        assert updated_page != initial_page
    before = output.stat().st_mtime_ns
    app, head = application(watch=True)
    with TestClient(app) as browser:
        browser.get("/")
        assert head._session.output == output
        assert output.stat().st_mtime_ns == before


@pytest.mark.parametrize("watch", [True, False])
def test_immediate_restart_with_changed_watch(project, watch):
    script = """import json, sys
from fasthtml.common import to_xml
from fasthtml_tailwindcss import TailwindHead
from fasthtml_tailwindcss.config import state_directory
head = TailwindHead(watch=sys.argv[1] == "True", sources=["components.py"])
to_xml(head)
print(json.dumps(str(state_directory(head._config)) if head._session else None))
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
        session = json.loads(result.stdout)
        return Path(session) if session else None

    (project / "static" / "tailwind.css").write_text(".ready{color:red}")
    previous = start(watch)
    current = start(not watch)
    if previous is not None:
        assert client.running(previous)
    if current is not None:
        assert client.running(current)
    assert (previous is None) != (current is None)


def test_concurrent_workers_share_one_build(project):
    settings = config.configuration(
        sources=["components.py"], input=None, css=None
    )
    sessions = [client.Session(settings) for _ in range(4)]
    with concurrent.futures.ThreadPoolExecutor() as pool:
        list(pool.map(lambda s: s.connect(), sessions))
    assert len({s.output for s in sessions}) == 1
    directory = config.state_directory(settings)
    assert (directory / "active.json").is_file()
    assert not (directory / "config.json").exists()
    assert int((directory / "pid").read_text()) > 0


def test_changed_settings_restart_watcher(project, application):
    app, head = application()
    with TestClient(app) as browser:
        browser.get("/")
        directory = head._session.directory
        original_pid = (directory / "pid").read_text()
    head._session.close()

    app, head = application(css=".custom { color: red; }")
    with TestClient(app) as browser:
        browser.get("/")
        assert (directory / "pid").read_text() != original_pid
        assert ".custom " in head._session.output.read_text()
        assert not (directory / "config.json").exists()
