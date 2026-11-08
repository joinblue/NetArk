"""Contract Tests for NetArk Standalone Control Center (`dashboard/tests/test_dashboard_shards.py`)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

DASHBOARD_ROOT = Path(__file__).resolve().parent.parent
if str(DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_ROOT))

from backend.graph_scanner import (
    build_project_graph_payload,
    get_node_detail,
    list_registered_projects,
)
from backend.server import dispatch_api_request


class TestDashboardShards(unittest.TestCase):
    def test_01_list_registered_projects(self) -> None:
        projects = list_registered_projects()
        self.assertGreaterEqual(len(projects), 1)
        default_pid = projects[0]["id"]
        self.assertEqual(default_pid, "NetArk")
        self.assertEqual(projects[0]["harness_dir"], ".netark")
        self.assertTrue(projects[0]["exists"])

    def test_02_build_project_graph_payload(self) -> None:
        default_pid = list_registered_projects()[0]["id"]
        payload = build_project_graph_payload(default_pid)
        self.assertEqual(payload["project"]["id"], default_pid)
        self.assertGreaterEqual(len(payload["nodes"]), 10)  # 5 memory nodes + code nodes
        self.assertGreaterEqual(len(payload["edges"]), 8)   # DAG + synapses + AST imports
        self.assertIn("ledger", payload)
        self.assertIn("handover", payload)
        self.assertIn("code_health", payload)
        self.assertIn("stats", payload)
        self.assertIn("alias_map", payload)
        amap = payload["alias_map"]
        self.assertIn("MEM-2026-0001", amap)
        self.assertIn("000", amap)
        self.assertIn("C0", amap)
        self.assertIn("schema_validator.py", amap)
        self.assertTrue(all("title_main" in item and "title_sub" in item for item in payload["ledger"]))

    def test_03_get_node_detail_and_neighbors(self) -> None:
        default_pid = list_registered_projects()[0]["id"]
        detail = get_node_detail(default_pid, "000.SOUL.v1")
        self.assertEqual(detail["node_id"], "MEM-2026-0001")
        self.assertIn("body_markdown", detail)
        self.assertTrue(len(detail["body_markdown"]) > 50)
        self.assertIn("code_bindings", detail)
        script_detail = get_node_detail(default_pid, "C0")
        self.assertEqual(script_detail["node_kind"], "code")
        self.assertIn("源碼預覽", script_detail["body_markdown"])

    def test_04_server_api_dispatch(self) -> None:
        default_pid = list_registered_projects()[0]["id"]
        status, data = dispatch_api_request("GET", "/api/projects")
        self.assertEqual(status, 200)
        self.assertIn("projects", data)

        status2, data2 = dispatch_api_request("GET", f"/api/project/{default_pid}/overview")
        self.assertEqual(status2, 200)
        self.assertEqual(data2["project"]["id"], default_pid)


if __name__ == "__main__":
    unittest.main()
