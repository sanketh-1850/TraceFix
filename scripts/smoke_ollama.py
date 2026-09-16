"""Run after installing the project with pip install -e '.[dev]'."""

from tracefix.common.ollama_smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
