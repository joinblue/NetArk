#!/usr/bin/env python3
"""Public regression tests for MCP tool schemas, 4-key annotations, Pi .ts hints, and tool handlers."""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.mcp_tools_core import MCP_TOOLS_SCHEMA, handle_mcp_tool_call, run_closed_mcp_init  # noqa: E402


class TestMCPToolsAndAnnotations(unittest.TestCase):
    """Verify MCP schema token budget, annotations parity, and query/record/guard execution."""

    def test_mcp_schema_annotations_and_budget(self) -> None:
        self.assertEqual([t["name"] for t in MCP_TOOLS_SCHEMA], ["netark_query", "netark_record", "netark_guard"])
        compact = json.dumps(MCP_TOOLS_SCHEMA, separators=(",", ":"))
        self.assertLessEqual(len(compact), 4000)
        self.assertLessEqual(len(compact) // 4, 1000)
        expected_ro = {"netark_query": True, "netark_record": False, "netark_guard": True}
        req_keys = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
        for tool in MCP_TOOLS_SCHEMA:
            ann = tool.get("annotations", {})
            self.assertEqual(set(ann.keys()), req_keys)
            self.assertIs(ann["readOnlyHint"], expected_ro[tool["name"]])
            self.assertIs(ann["openWorldHint"], False)

    def test_pi_extensions_declare_annotations(self) -> None:
        pi_dir = ROOT / "templates" / "hosts" / "pi" / "extensions"
        for rel in ("model-router.ts", "subagent/index.ts", "web-research.ts"):
            text = (pi_dir / rel).read_text(encoding="utf-8")
            self.assertIn("annotations:", text, rel)
            for key in ("readOnlyHint:", "destructiveHint:", "idempotentHint:", "openWorldHint:"):
                self.assertIn(key, text, f"{rel} missing {key}")

    def test_query_record_and_guard_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_res = run_closed_mcp_init(tmp, target="memory", lang="en")
            self.assertEqual(init_res["status"], "ok")

            q0 = handle_mcp_tool_call("netark_query", {"query": "000"}, tmp)
            self.assertTrue(q0["found"])
            self.assertIsInstance(q0.get("total_lines"), int)
            self.assertIsInstance(q0.get("sections"), list)

            pre = handle_mcp_tool_call(
                "netark_record",
                {"intent": "note", "title": "Public Test Note", "mode": "preflight", "body": "- [FACT] Verified.\n"},
                tmp,
            )
            self.assertTrue(pre["ok"], pre)
            wr = handle_mcp_tool_call(
                "netark_record",
                {"intent": "note", "title": "Public Test Note", "mode": "write", "body": "- [FACT] Verified.\n"},
                tmp,
            )
            self.assertTrue(wr["ok"], wr)
            self.assertTrue((Path(tmp) / wr["target_path"]).is_file())

            for act in ("status", "oracle", "handover", "setup"):
                gres = handle_mcp_tool_call("netark_guard", {"action": act}, tmp)
                self.assertTrue(gres["ok"], (act, gres))

    def test_init_avoids_node_id_and_node_key_collisions(self) -> None:
        year = datetime.date.today().year
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_res = run_closed_mcp_init(tmp, target="memory", lang="en")
            self.assertEqual(init_res["status"], "ok")
            (root / "memory" / "LEDGER.md").unlink()
            soul_p = root / "memory" / "codex" / "000_SOUL.md"
            soul_p.write_text(soul_p.read_text(encoding="utf-8").replace("MEM-2026-0001", f"MEM-{year}-0004"), encoding="utf-8")

            reinit = run_closed_mcp_init(tmp, target="memory", lang="en")
            self.assertEqual(reinit["bootstrapped_memory_nodes"], ["memory/LEDGER.md"])
            ledger_txt = (root / "memory" / "LEDGER.md").read_text(encoding="utf-8")
            m_id = re.search(rf'(?m)^node_id:\s*["\']?(MEM-{year}-(\d{{4,}}))', ledger_txt)
            self.assertIsNotNone(m_id, ledger_txt[:200])
            self.assertGreaterEqual(int(m_id.group(2)), 6)
            self.assertTrue(handle_mcp_tool_call("netark_guard", {"action": "oracle"}, tmp)["ok"])

    def test_version_parity_and_docs_sync(self) -> None:
        pyproj = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        ver = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproj).group(1)
        init_ver = re.search(r'(?m)^__version__\s*=\s*"([^"]+)"', (ROOT / "src" / "netark_mcp" / "__init__.py").read_text(encoding="utf-8")).group(1)
        srv_ver = re.search(r'(?m)^NETARK_VERSION\s*=\s*"([^"]+)"', (ROOT / "scripts" / "netark_mcp_server.py").read_text(encoding="utf-8")).group(1)
        self.assertEqual(ver, init_ver)
        self.assertEqual(ver, srv_ver)
        for flag in ("--version", "-V"):
            proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "netark_mcp_server.py"), flag], text=True, capture_output=True, check=True)
            self.assertEqual(proc.stdout.strip(), f"netark-mcp {ver}")
        docs_hc = (ROOT / "docs" / "HOOK_CONTRACT.md").read_text(encoding="utf-8")
        tmpl_hc = (ROOT / "templates" / "mcp" / "HOOK_CONTRACT.md").read_text(encoding="utf-8")
        self.assertEqual(docs_hc, tmpl_hc)
        self.assertIn("--target pi", docs_hc)
        self.assertIn("--target pi", (ROOT / "docs" / "QUICKSTART.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
