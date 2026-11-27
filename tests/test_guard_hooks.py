#!/usr/bin/env python3
"""Public regression tests for deterministic PreToolUse security, AST, RIBC, and context-map gates."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.mcp_tools_core import run_closed_mcp_init  # noqa: E402


def _run_agy_hook(cwd: str, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    payload = json.dumps({"workspacePaths": [cwd], "toolCall": {"name": name, "args": args}})
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "netark_mcp_server.py"), "hook", "--hook-mode", "agy", "--cwd", cwd],
        input=payload,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


class TestGuardHooks(unittest.TestCase):
    """Verify deterministic PreToolUse guard blocks without LLM drift."""

    def test_security_ast_ribc_and_context_map_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_closed_mcp_init(tmp, target="agy", lang="en")
            fake_key = "AKIA" + "IOSFODNN7EXAMPLE"
            deep_py = (
                "def f(a):\n if a:\n  for x in a:\n   while x:\n    try:\n"
                "     if x == 1:\n      return 1\n    except ValueError:\n     return 0\n"
            )
            cases = [
                ("read_file", {"Path": ".env"}, "SEC-CRED"),
                ("write_file", {"Path": "projects/demo/src/app.py", "Content": f'K = "{fake_key}"'}, "SEC-PREWRITE-SECRET"),
                ("write_file", {"Path": "projects/demo/src/deep.py", "Content": deep_py}, "CODE-ARROW-NESTING"),
                ("invoke_subagent", {"TypeName": "self", "Role": "Coder", "Prompt": "Write module"}, "SPEC-RIBC-GATE"),
                ("read_file", {"Path": "memory/codex/CONTEXT_MAP.md"}, "CONTEXT-MAP-READ-GATE"),
            ]
            for tool_name, tool_args, expected_code in cases:
                verdict = _run_agy_hook(tmp, tool_name, tool_args)
                self.assertEqual(verdict.get("decision"), "deny", (tool_name, verdict))
                self.assertIn(expected_code, verdict.get("reason", ""), verdict)


if __name__ == "__main__":
    unittest.main()
