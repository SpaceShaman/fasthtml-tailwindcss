import gc
import time

import pytest
from fasthtml.common import Div, FastHTML
from starlette.testclient import TestClient

from fasthtml_tailwindcss import TailwindHead


def test_custom_input_relative_imports_and_inline_css(project, application):
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


def test_first_compilation_error_blocks_construction(project):
    with pytest.raises(RuntimeError, match="Tailwind stopped"):
        TailwindHead(css=".broken { @apply definitely-not-a-tailwind-utility; }")


def test_constructor_builds_without_asgi_lifespan(project):
    head = TailwindHead(sources=["components.py"])
    assert head._session.output.exists()
    app = FastHTML(sess_cls=None, hdrs=[head])

    @app.route("/")
    def get():
        return Div("Hello", cls="p-4")

    client = TestClient(app)
    assert ".p-4{" in client.get("/").text
    client.close()


def test_releasing_component_stops_heartbeat(project):
    head = TailwindHead(sources=["components.py"])
    session = head._session
    del head
    gc.collect()
    assert not session._thread.is_alive()


def test_default_sources_and_css_escaping(project):
    head = TailwindHead(css='.closing::after { content: "</style>"; }')
    app = FastHTML(sess_cls=None, hdrs=[head])
    with TestClient(app):
        from fasthtml.common import to_xml

        result = str(to_xml(head))
        assert ".p-4{" in result
        assert result.count("</style>") == 1


def test_invalid_sources_argument(project):
    with pytest.raises(TypeError, match="sequence"):
        TailwindHead(sources="app")


def test_existing_lifespan_and_heartbeat(project):
    events = []
    head = TailwindHead(sources=["components.py"])
    app = FastHTML(
        hdrs=[head],
        sess_cls=None,
        on_startup=lambda: events.append("startup"),
        on_shutdown=lambda: events.append("shutdown"),
    )
    with TestClient(app):
        assert events == ["startup"]
        time.sleep(16)
        assert not head._session.error  # ty: ignore[unresolved-attribute]  # FastHTML defines hdrs dynamically.
        assert head._session.output.exists()  # ty: ignore[unresolved-attribute]  # FastHTML defines hdrs dynamically.
    assert events == ["startup", "shutdown"]
