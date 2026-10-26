# fasthtml-tailwindcss

[![License](https://img.shields.io/github/license/SpaceShaman/fasthtml-tailwindcss)](LICENSE)
[![Release](https://img.shields.io/github/actions/workflow/status/SpaceShaman/fasthtml-tailwindcss/release.yml?label=release)](https://github.com/SpaceShaman/fasthtml-tailwindcss/actions/workflows/release.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/fasthtml-tailwindcss)](https://pypi.org/project/fasthtml-tailwindcss/)
[![PyPI version](https://img.shields.io/pypi/v/fasthtml-tailwindcss)](https://pypi.org/project/fasthtml-tailwindcss/)
[![FastHTML](https://img.shields.io/badge/framework-FastHTML-7854F7)](https://github.com/AnswerDotAI/fasthtml)
[![Tailwind CSS](https://img.shields.io/badge/CSS-Tailwind_CSS-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Pytest](https://img.shields.io/badge/testing-pytest-0A9EDC?logo=pytest)](https://docs.pytest.org/)
[![Ruff](https://img.shields.io/badge/linting-Ruff-D7FF64?logo=ruff)](https://github.com/astral-sh/ruff)

Tailwind CSS for [FastHTML](https://github.com/AnswerDotAI/fasthtml) with a persistent compiler across server reloads and watch mode for automatic CSS rebuilds.

## Installation

Install with uv:

```sh
uv add fasthtml-tailwindcss
```

Or with pip:

```sh
pip install fasthtml-tailwindcss
```

On Alpine Linux, the standalone compiler also requires the system C++ runtime:

```sh
apk add --no-cache libstdc++ libgcc
```

## Usage

```python
from fasthtml.common import Div, FastHTML
from fasthtml_tailwindcss import TailwindHead

app = FastHTML(hdrs=[TailwindHead(watch=True)])


@app.route("/")
def get():
    return Div("Hello", cls="rounded-lg bg-blue-500 p-4 text-white")
```

Run your application normally, for example with `uv run uvicorn main:app --reload`. The package bundles the official standalone Tailwind compiler: no Node.js, npm, CDN, CSS endpoint or additional command is needed.

`TailwindHead` builds CSS when the component is constructed, usually while importing your application module, and waits for the first successful compilation. It embeds the result in a `<style>` element. Each full page receives the latest completed CSS. Refresh the browser to see updates; automatic browser refresh and updating styles during HTMX fragment swaps are not included.

- `watch=True`: compile once, then watch source files. The compiler survives application reloads.
- `watch=False` (default): compile once with minification, then reuse the result across reloads. Source changes do not rebuild CSS during that session.

A local helper keeps the session alive while applications renew a shared heartbeat file, and shuts down 15 seconds after the last heartbeat. A quick manual restart is treated like a reload. A later start creates a fresh session and builds again. The session stays active while the component exists in a running Python process; it does not depend on ASGI lifespan.

## Options

All configuration is passed to `TailwindHead`:

```python
TailwindHead(
    watch=True,
    sources=["app"],
    css="@theme { --color-brand: #7854f7; }",
)
```

For a custom input stylesheet:

```python
TailwindHead(watch=True, input="assets/app.css")
```

- `sources`: source files or directories. Defaults to the project directory with the built-in input; with a custom input, its own source detection is used unless extra sources are supplied.
- `input`: optional stylesheet replacing the built-in `@import "tailwindcss"`. Relative CSS imports resolve from that file.
- `css`: optional inline CSS appended after the input. Useful for `@theme`, variants and explicit `@source inline(...)` declarations.

Paths are resolved relative to the nearest `pyproject.toml` above the working directory, or the working directory if none exists. Sessions are shared by project, configuration and OS user. Reloads and application workers with identical options reuse the same session. Changing options, including `watch`, starts a separate session immediately; the unused session shuts down after 15 seconds.

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

## Links

- [GitHub repository](https://github.com/SpaceShaman/fasthtml-tailwindcss)
- [PyPI package](https://pypi.org/project/fasthtml-tailwindcss/)

## License

The wrapper and Tailwind CSS are MIT licensed. Both license notices are included in distributions.
