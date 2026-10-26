import concurrent.futures
import copy
import time

import pytest
from fasthtml.common import Div, FastHTML
from starlette.testclient import TestClient

from fasthtml_tailwindcss import TailwindHead, _client


@pytest.fixture(scope="session")
def helpers():
    directories = []
    yield directories
    deadline = time.monotonic() + 25
    while any((p / "pid").exists() for p in directories):
        assert time.monotonic() < deadline, (
            "Helper did not shut down after losing clients"
        )
        time.sleep(0.1)


@pytest.fixture
def project(tmp_path, monkeypatch, helpers):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_client, "user_cache_path", lambda *a, **kw: tmp_path / "cache")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="example"\nversion="0.1.0"\n'
    )
    (tmp_path / "components.py").write_text('classes = "p-4 bg-blue-500"\n')
    config = _client.configuration(
        watch=False, sources=["components.py"], input=None, css=None
    )
    helpers.append(_client.cache_directory(config))
    return tmp_path


def application(**options):
    app = FastHTML(sess_cls=None)
    head = TailwindHead(app, sources=["components.py"], **options)
    app.hdrs.append(head)  # ty: ignore[unresolved-attribute]  # FastHTML defines hdrs dynamically.

    @app.get("/")  # ty: ignore[unresolved-attribute]  # FastHTML registers HTTP methods dynamically.
    def get():
        return Div("Hello", cls="p-4 bg-blue-500")

    return app, head


def test_once_build_survives_reload(project):
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


def test_watch_rebuilds_and_survives_reload(project):
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


def test_custom_input_relative_imports_and_inline_css(project):
    assets = project / "assets"
    assets.mkdir()
    (assets / "theme.css").write_text(".custom { color: red; }\n")
    (assets / "app.css").write_text(
        '@import "tailwindcss" source(none);\n@import "./theme.css";\n'
    )
    app, _head = application(input="assets/app.css", css=".extra { color: blue; }")
    with TestClient(app) as client:
        html = client.get("/").text
        assert ".custom{" in html
        assert ".extra{" in html
        assert ".p-4{" in html


def test_first_compilation_error_blocks_startup(project):
    app, _head = application(
        css=".broken { @apply definitely-not-a-tailwind-utility; }"
    )
    with pytest.raises(RuntimeError, match="Tailwind stopped"), TestClient(app):
        pytest.fail("Application started with invalid CSS")


def test_changed_options_require_session_restart(project):
    app, _head = application()
    with TestClient(app):
        pass
    app, _head = application(watch=True)
    with pytest.raises(RuntimeError, match="settings differ"), TestClient(app):
        pass


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


def test_no_process_during_construction_and_missing_lifespan(project):
    app, head = application()
    assert not _client.cache_directory(head._config).exists()
    with pytest.raises(RuntimeError, match="lifespan"):
        head.__ft__()
    with pytest.raises(ValueError, match="one TailwindHead"):
        TailwindHead(app)


def test_default_sources_and_css_escaping(project):
    app = FastHTML(sess_cls=None)
    head = TailwindHead(app, css='.closing::after { content: "</style>"; }')
    app.hdrs.append(head)  # ty: ignore[unresolved-attribute]  # FastHTML defines hdrs dynamically.
    with TestClient(app):
        from fasthtml.common import to_xml

        result = str(to_xml(head))
        assert ".p-4{" in result
        assert result.count("</style>") == 1


def test_invalid_sources_argument(project):
    with pytest.raises(TypeError, match="sequence"):
        TailwindHead(FastHTML(sess_cls=None), sources="app")


@pytest.mark.skipif(
    __import__("os").name == "nt",
    reason="POSIX process-group shutdown for this reload test",
)
@pytest.mark.parametrize("watch", [False, True])
def test_real_uvicorn_reload(project, helpers, watch):
    import os
    import signal
    import socket
    import subprocess
    import sys
    from urllib.error import URLError
    from urllib.request import urlopen

    source = project / "main.py"
    source.write_text(f"""import os
from pathlib import Path
from fasthtml.common import FastHTML, Div
from fasthtml_tailwindcss import TailwindHead, _client
_client.user_cache_path = lambda *a, **kw: Path({str(project / "cache")!r})
app = FastHTML(sess_cls=None)
app.hdrs.append(TailwindHead(app, watch={watch!r}, sources=["main.py"]))
@app.get("/")
def get():
    return Div("first", cls="p-4")
@app.get("/pid")
def pid():
    return str(os.getpid())
""")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    def response(path="/"):
        try:
            with urlopen(base + path, timeout=1) as res:
                return res.read().decode()
        except (OSError, URLError):
            return ""

    config = _client.configuration(
        watch=watch, sources=["main.py"], input=None, css=None
    )
    directory = _client.cache_directory(config)
    with (project / "uvicorn.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--reload",
                "--port",
                str(port),
            ],
            cwd=project,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 20
            while ">first</div>" not in response():
                assert process.poll() is None, (project / "uvicorn.log").read_text()
                assert time.monotonic() < deadline, (
                    project / "uvicorn.log"
                ).read_text()
                time.sleep(0.1)
            pid = response("/pid")
            helper_pid = (directory / "pid").read_text()
            output = directory / "style.css"
            timestamp = output.stat().st_mtime_ns
            source.write_text(
                source.read_text().replace(
                    '"first", cls="p-4"', '"second", cls="text-7xl"'
                )
            )
            deadline = time.monotonic() + 20
            while ">second</div>" not in response():
                assert time.monotonic() < deadline, (
                    project / "uvicorn.log"
                ).read_text()
                time.sleep(0.1)
            assert response("/pid") != pid
            assert (directory / "pid").read_text() == helper_pid
            if watch:
                while ".text-7xl" not in response():
                    assert time.monotonic() < deadline
                    time.sleep(0.1)
            else:
                assert output.stat().st_mtime_ns == timestamp
                assert ".text-7xl" not in response()
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=15)


def test_existing_lifespan_and_heartbeat(project):
    events = []
    app = FastHTML(
        sess_cls=None,
        on_startup=lambda: events.append("startup"),
        on_shutdown=lambda: events.append("shutdown"),
    )
    head = TailwindHead(app, sources=["components.py"])
    app.hdrs.append(head)  # ty: ignore[unresolved-attribute]  # FastHTML defines hdrs dynamically.
    with TestClient(app):
        assert events == ["startup"]
        time.sleep(16)
        assert not head._session.error  # ty: ignore[unresolved-attribute]  # FastHTML defines hdrs dynamically.
        assert head._session.output.exists()  # ty: ignore[unresolved-attribute]  # FastHTML defines hdrs dynamically.
    assert events == ["startup", "shutdown"]
