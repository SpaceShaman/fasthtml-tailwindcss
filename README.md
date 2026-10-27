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

Tailwind CSS for [FastHTML](https://github.com/AnswerDotAI/fasthtml) with a persistent development watcher and a build command for production CSS.

## Installation

- Development and builds:

  ```sh
  uv add "fasthtml-tailwindcss[dev]"
  ```

  Or with pip:

  ```sh
  pip install "fasthtml-tailwindcss[dev]"
  ```

- Production:

  ```sh
  uv add fasthtml-tailwindcss
  ```

  Or with pip:

  ```sh
  pip install fasthtml-tailwindcss
  ```

The `dev` extra installs the standalone compiler through [fasthtml-tailwindcss-cli](https://pypi.org/project/fasthtml-tailwindcss-cli/). No Node.js or npm is needed. Production only needs the wrapper and generated CSS.

On Alpine Linux, the compiler also needs:

```sh
apk add --no-cache libstdc++ libgcc
```

## Usage

```python
from fasthtml.common import Div, FastHTML, StaticImmutable
from fasthtml_tailwindcss import TailwindHead

app = FastHTML(hdrs=[TailwindHead(watch=True)])
app.mount("/static", StaticImmutable(directory="static"), name="static")


@app.route("/")
def get():
    return Div("Hello", cls="rounded-lg bg-blue-500 p-4 text-white")
```

`TailwindHead` creates the output directory and adds a stylesheet link. `vurl` versions the URL by content, and `StaticImmutable` lets browsers cache the CSS until it changes.

### Watch mode

```sh
uv run uvicorn main:app --reload
```

For `app/main.py`, run `uv run --directory app uvicorn main:app --reload` from the project directory.

With `watch=True`, compilation starts on the first page render and CSS rebuilds when sources change. The watcher survives server reloads, restarts if settings change, and stops 15 seconds after the last application stops using it. Refresh the browser to see changes; automatic browser refresh and stylesheet updates during HTMX fragment swaps are not included.

### Production

Use `TailwindHead()` with the default `watch=False` in the application, then build CSS in your deployment pipeline with the `dev` extra installed:

```sh
uv run fasthtml-tailwindcss build main:app
```

The command imports the app and builds minified CSS using its `TailwindHead` settings. The app must have exactly one `TailwindHead` in `hdrs`. For `app/main.py`, run `build app.main:app` from the project directory or `build main:app` from `app/`; both write to `app/static/tailwind.css` by default.

Deploy the generated CSS alongside the application. With `watch=False`, `TailwindHead` only links the stylesheet; it does not run the compiler.

## Options

All configuration is passed to `TailwindHead`:

```python
TailwindHead(
    watch=True,
    css="@theme { --color-brand: #7854f7; }",
    output="static/app.css",
)
```

- `watch`: enable the persistent development compiler. Defaults to `False`.
- `sources`: files or directories to scan. Defaults to the working directory; with a custom input, its own source detection applies unless extra sources are supplied.
- `input`: custom stylesheet, such as `input="assets/app.css"`, replacing the built-in `@import "tailwindcss"`. Relative CSS imports resolve from that file.
- `css`: CSS appended after the input, useful for `@theme`, variants, and `@source inline(...)`.
- `output`: CSS file path, defaulting to `./static/tailwind.css`. The stylesheet URL follows this path, so mount its directory at the corresponding URL.

Paths are relative to the working directory. The build command uses the application module's directory; run the server from that directory too. Temporary files and compiler logs live in `.fasthtml-tailwindcss/`, which you can add to `.gitignore`.

Use complete class names such as `"bg-red-500"`; Tailwind cannot detect names constructed with `f"bg-{color}-500"`. Classes in installed component libraries need explicit sources or safelisting.

For inline Lucide SVG icons with typed names and editor autocomplete, see [fasthtml-lucide](https://github.com/SpaceShaman/fasthtml-lucide).

## Development

### Setup and tests

```sh
uv sync --group build --group test --extra dev
uv run --group test --extra dev pytest
```

### Build

```sh
uv build --no-sources
uv build packages/cli --no-sources
```

CLI wheel builds download and verify the official executable using SHA-256. Supported platforms are Linux x64/ARM64 (glibc 2.28+ or musl 1.2+), macOS 13+ (Intel/Apple Silicon), and Windows x64. Building a CLI wheel needs network access unless the verified binary is already available locally.

### Automated releases

GitHub Actions checks daily for a new stable [Tailwind CSS release](https://github.com/tailwindlabs/tailwindcss/releases), then builds and tests both packages before publishing them to PyPI. Both package versions track the Tailwind version; wrapper-only fixes may add a `.postN` suffix.

The [Release workflow](.github/workflows/release.yml) builds and tests both packages before publishing through PyPI Trusted Publishing. Configure the same publisher (`SpaceShaman/fasthtml-tailwindcss`, workflow `release.yml`, environment `pypi`) for both PyPI projects, and allow workflow version commits on the default branch.

## Links

- [GitHub repository](https://github.com/SpaceShaman/fasthtml-tailwindcss)
- [PyPI package](https://pypi.org/project/fasthtml-tailwindcss/)
- [Tailwind CLI package](https://pypi.org/project/fasthtml-tailwindcss-cli/)

## License

The wrapper and Tailwind CSS are MIT licensed. The CLI package includes both license notices.
