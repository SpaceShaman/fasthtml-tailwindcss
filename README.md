# fasthtml-tailwindcss

Tailwind CSS for [FastHTML](https://github.com/AnswerDotAI/fasthtml) with a persistent compiler across server reloads.

Install with uv or pip:

```sh
uv add fasthtml-tailwindcss
# or
pip install fasthtml-tailwindcss
```

## Usage

```python
from fasthtml.common import Div, fast_app
from fasthtml_tailwindcss import TailwindHead

app, rt = fast_app()
app.hdrs.append(TailwindHead(app, watch=True))


@rt("/")
def get():
    return Div("Hello", cls="rounded-lg bg-blue-500 p-4 text-white")
```

Run your application normally, for example with `uv run uvicorn main:app --reload`. The package bundles the official standalone Tailwind compiler: no Node.js, npm, CDN, CSS endpoint or additional command is needed.

`TailwindHead` builds CSS during ASGI startup and embeds it in a `<style>` element. The server waits for the first successful compilation. Each full page receives the latest completed CSS. Refresh the browser to see updates; automatic browser refresh and updating styles during HTMX fragment swaps are not included.

- `watch=True`: compile once, then watch source files. The compiler survives application reloads.
- `watch=False` (default): compile once with minification, then reuse the result across reloads. Source changes do not rebuild CSS during that session.

A local helper keeps the session alive while applications renew a shared heartbeat file, and shuts down 15 seconds after the last heartbeat. A quick manual restart is treated like a reload. A later start creates a fresh session and builds again. Keep ASGI lifespan enabled.

## Options

All configuration is passed to `TailwindHead`:

```python
TailwindHead(
    app,
    watch=True,
    sources=["app"],
    css="@theme { --color-brand: #7854f7; }",
)
```

For a custom input stylesheet:

```python
TailwindHead(app, watch=True, input="assets/app.css")
```

- `sources`: source files or directories. Defaults to the project directory with the built-in input; with a custom input, its own source detection is used unless extra sources are supplied.
- `input`: optional stylesheet replacing the built-in `@import "tailwindcss"`. Relative CSS imports resolve from that file.
- `css`: optional inline CSS appended after the input. Useful for `@theme`, variants and explicit `@source inline(...)` declarations.

Paths are resolved relative to the nearest `pyproject.toml` above the working directory, or the working directory if none exists. There is one session per project and OS user. Multiple application workers share it. To change options, stop all servers for that project and wait 15 seconds; settings are not changed automatically in an active session.

Tailwind scans complete class names in source files. Use `"bg-red-500"` rather than constructing names such as `f"bg-{color}-500"`. Classes inside installed component libraries need explicit sources or safelisting.

Generated files and compiler diagnostics (`compiler.log`) live in the OS user cache under `fasthtml-tailwindcss`. Nothing is written into your application or installed package. Inline CSS requires an appropriate Content Security Policy if your application sets one.

## Development

```sh
uv sync --group test
uv run --group test pytest
uv build
```

Wheel builds download and verify the matching official standalone executable. Wheels target Linux x64/ARM64 (glibc 2.28+ or musl 1.2+), macOS 13+ (Intel/Apple Silicon), and Windows x64. Source distributions contain the build hook and checksum manifest; building one requires network access unless the verified compiler is already present locally.

The package version follows Tailwind, with `.postN` for Python-only fixes. The release workflow checks upstream daily, tests the platform wheels and publishes through PyPI Trusted Publishing. Configure the publisher for `SpaceShaman/fasthtml-tailwindcss`, workflow `release.yml`, environment `pypi`; allow workflow version commits on the default branch.

## License

The wrapper and Tailwind CSS are MIT licensed. Both license notices are included in distributions.
