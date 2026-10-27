import copy
import gc
import time

import pytest
from fasthtml.common import Div, FastHTML, StaticImmutable, to_xml
from starlette.testclient import TestClient

from fasthtml_tailwindcss import TailwindHead


@pytest.mark.parametrize("watch", [False, True])
def test_constructor_creates_output_directory_before_static_mount(project, watch):
    output = "assets/generated/tailwind.css"
    directory = project / "assets" / "generated"
    assert not directory.exists()
    head = TailwindHead(watch=watch, output=output)
    app = FastHTML(sess_cls=None, hdrs=[head])
    app.mount("/assets/generated", StaticImmutable(directory=directory), name="static")
    assert directory.is_dir()
    assert not (directory / "tailwind.css").exists()
    assert not (project / ".fasthtml-tailwindcss").exists()


def test_custom_output_in_application_directory(project):
    root = project / "app"
    (root / "static").mkdir(parents=True)
    (root / "main.py").write_text('classes = "text-7xl"\n')
    head = TailwindHead(
        watch=True, sources=["app/main.py"], output="app/static/tailwind.css"
    )
    app = FastHTML(sess_cls=None, hdrs=[head])
    app.mount("/app/static", StaticImmutable(directory=root / "static"), name="static")
    try:
        assert "/app/static/tailwind.css?v=" in str(to_xml(head))
        assert not (project / "static" / "tailwind.css").exists()
        with TestClient(app) as browser:
            response = browser.get("/app/static/tailwind.css")
            assert response.status_code == 200
            assert ".text-7xl " in response.text
    finally:
        head._session.close()


def test_watch_builds_css_and_returns_versioned_link(project, application):
    app, head = application()
    with TestClient(app) as client:
        response = client.get("/")
        assert "/static/tailwind.css?v=" in response.text
        stylesheet = client.get("/static/tailwind.css")
        assert ".p-4 " in stylesheet.text
        assert ".bg-blue-500 " in stylesheet.text
        assert head._session.output.exists()


def test_custom_input_relative_imports_and_inline_css(project, application):
    assets = project / "assets"
    assets.mkdir()
    (assets / "theme.css").write_text(".custom { color: red; }\n")
    (assets / "app.css").write_text(
        '@import "tailwindcss" source(none);\n@import "./theme.css";\n'
    )
    app, head = application(input="assets/app.css", css=".extra { color: blue; }")
    with TestClient(app) as client:
        client.get("/")
        stylesheet = client.get("/static/tailwind.css")
        assert ".custom " in stylesheet.text
        assert ".extra " in stylesheet.text
        assert ".p-4 " in stylesheet.text
        assert head._session.output.exists()


def test_compile_error_is_reported_on_first_render(project, application):
    app, _ = application(css=".broken { @apply definitely-not-a-tailwind-utility; }")
    with pytest.raises(RuntimeError, match="Tailwind stopped"), TestClient(app) as client:
        client.get("/")


def test_default_head_links_existing_css_without_starting_compiler(project, monkeypatch):
    directory = project / "app"
    (directory / "static").mkdir(parents=True)
    monkeypatch.chdir(directory)
    output = directory / "static" / "tailwind.css"
    output.write_text(".built{color:red}")
    head = TailwindHead()
    assert head._session is None
    assert copy.deepcopy(head) is head
    app = FastHTML(sess_cls=None, hdrs=[head])
    app.mount("/static", StaticImmutable(directory="static"), name="static")
    link = str(to_xml(head))
    assert "<link" in link
    assert "rel=\"stylesheet\"" in link
    assert "tailwind.css?v=" in link
    assert ".built" not in link
    with TestClient(app) as client:
        response = client.get("/static/tailwind.css")
        assert response.text == ".built{color:red}"
        assert response.headers["cache-control"] == (
            "public, max-age=31536000, immutable"
        )


def test_watch_starts_on_first_render_and_stops_when_component_is_released(
    project, application
):
    app, head = application()
    session = head._session
    assert not session._thread.is_alive()
    with TestClient(app) as client:
        client.get("/")
        assert session._thread.is_alive()
    del app, head, client
    gc.collect()
    assert not session._thread.is_alive()


def test_invalid_sources_argument(project):
    with pytest.raises(TypeError, match="sequence"):
        TailwindHead(sources="app")


def test_existing_lifespan_and_heartbeat(project, application):
    events = []
    head = TailwindHead(sources=["components.py"], watch=True)
    app = FastHTML(
        hdrs=[head],
        sess_cls=None,
        on_startup=lambda: events.append("startup"),
        on_shutdown=lambda: events.append("shutdown"),
    )
    app.mount("/static", StaticImmutable(directory="static"), name="static")
    app.route("/")(lambda: Div("Hello"))
    with TestClient(app) as client:
        client.get("/")
        assert events == ["startup"]
        time.sleep(16)
        assert not head._session.error
        assert head._session.output.exists()
    assert events == ["startup", "shutdown"]
