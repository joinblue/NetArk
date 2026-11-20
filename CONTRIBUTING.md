# Contributing to NetArk (`netark-mcp`)

Thank you for your interest in **NetArk**!

## Solo-Maintained Scope & Boundaries

NetArk is maintained by a single developer (`joinblue`) with limited review bandwidth:

- **Accepted PRs Only**: Only **bug fixes** and **features previously discussed and approved in a GitHub Issue** are accepted. Unsolicited feature PRs or large refactors will be closed without review.
- **Tests & CI Required**: Every PR must include regression tests covering the change and pass all CI checks (`ci.yml`).
- **CLA Required**: All external contributors must sign the [Contributor License Agreement (`CLA.md`)](CLA.md) (check the box in the PR template or comment on the PR when prompted by the CLA bot).

## Core Engineering Rules

1. **Zero Runtime Dependencies**: Code under `src/netark_mcp/`, `schemas/`, and `scripts/` must use **Python 3.10+ standard library only** (`dependencies = []` in `pyproject.toml`).
2. **AST Hygiene**: Keep functions under **<= 4 control-flow nesting levels**, avoid silent `except: pass`, and keep modules concise (`<= 400` effective code lines).
3. **Cross-Platform**: Ensure path handling, CLI flags, and stdio JSON-RPC work on **Linux, macOS, and Windows**.

## Local Verification

```bash
uv run --no-project python schemas/netark_guard_core.py --self-test
uv run --no-project python scripts/netark_guard_daemon.py --self-test
uv run --no-project python scripts/netark_init.py --self-test

uv build --wheel --sdist
uv run --no-project --with dist/*.whl netark-mcp --help
```
