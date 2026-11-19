"""CLI entrypoint shim for the isolated `netark-mcp` wheel/uv package."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional


def _bootstrap_core_root() -> Path:
    pkg_dir = Path(__file__).resolve().parent
    bundled_core = pkg_dir / "_core"
    core_root = bundled_core if (bundled_core / "schemas").is_dir() else pkg_dir.parents[1]
    root_str = str(core_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return core_root


def main(argv: Optional[List[str]] = None) -> int:
    """Bootstrap embedded core modules and dispatch to scripts.netark_mcp_server.main."""
    _bootstrap_core_root()
    from scripts.netark_mcp_server import main as server_main

    return server_main(argv)


if __name__ == "__main__":
    sys.exit(main())
