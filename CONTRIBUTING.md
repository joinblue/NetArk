# Contributing to NetArk (`netark-mcp`)

Thank you for your interest in contributing to **NetArk**!

## License & No CLA Friction
NetArk is licensed under the **Apache License 2.0**. Pursuant to Section 5 of Apache-2.0, any pull request you submit is automatically licensed under the same terms — **no external CLA signing or bot comment is required**.

## Core Engineering Principles

1. **Zero Runtime Dependencies**:
   All runtime code under `src/netark_mcp/`, `schemas/`, and `scripts/` must use **Python 3.10+ standard library only** (`dependencies = []` in `pyproject.toml`). Optional dev tools (`pytest`, `pyyaml`, `jsonschema`) belong only in `[project.optional-dependencies].dev`.
2. **AST Hygiene & Modularity**:
   - Maximum control-flow nesting depth (`if`/`for`/`while`/`try`/`with`) per function: **<= 4 levels** (prefer early returns).
   - Never write bare or silent `except: pass` blocks.
   - Keep modules cohesive and under **400 effective code lines**.
3. **Cross-Platform Determinism**:
   Ensure file path operations, CLI arguments, and JSON-RPC stdio handlers work cleanly across **Linux, macOS, and Windows**.

## Local Development & Verification

```bash
# Run deterministic core self-tests via uv
uv run python schemas/netark_guard_core.py --self-test
uv run python scripts/netark_guard_daemon.py --self-test
uv run python scripts/netark_init.py --self-test

# Build wheel & sdist and verify isolated CLI execution
uv build --wheel --sdist
uv run --no-project --with dist/*.whl netark-mcp --help
```

Please keep PRs focused, update relevant documentation in `docs/` when behavior changes, and verify that all self-tests pass before opening a PR.
