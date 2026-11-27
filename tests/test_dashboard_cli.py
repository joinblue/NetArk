#!/usr/bin/env python3
"""Public regression tests for single-project read-only Dashboard scanner & HTTP-only background server."""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dashboard.backend import graph_scanner, server  # noqa: E402
from schemas.mcp_tools_core import run_closed_mcp_init  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class TestDashboardCLI(unittest.TestCase):
    """Verify single-project dashboard scanning, HTTP-only startup, and disable switch."""

    def test_scanner_and_background_server(self) -> None:
        prev_root = graph_scanner._WORKSPACE_ROOT
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp).resolve()
            run_closed_mcp_init(str(ws), target="memory", lang="en")
            graph_scanner.set_workspace_root(ws)
            try:
                projects = graph_scanner.list_registered_projects()
                self.assertTrue(any(p["id"] == ws.name for p in projects), projects)
                payload = graph_scanner.build_project_graph_payload(ws.name)
                self.assertGreaterEqual(len(payload.get("nodes", [])), 5)

                with patch.dict(os.environ, {"NETARK_DASHBOARD": "0"}):
                    dis = server.start_background_dashboard(str(ws))
                    self.assertEqual(dis.get("status"), "disabled")
                    self.assertIsNone(dis.get("url"))

                port = _free_port()
                with patch.dict(os.environ, {"NETARK_DASHBOARD": "1", "NETARK_DASHBOARD_PORT": str(port)}):
                    info = server.start_background_dashboard(str(ws))
                    self.assertEqual(info.get("status"), "started")
                    try:
                        with urllib.request.urlopen(f"{info['url']}/api/projects", timeout=2.0) as resp:
                            self.assertEqual(resp.status, 200)
                            data = json.loads(resp.read().decode("utf-8"))
                            self.assertTrue(any(p["id"] == ws.name for p in data.get("projects", [])))
                    finally:
                        srv = info.get("server")
                        if srv is not None:
                            srv.shutdown()
                            srv.server_close()
            finally:
                if prev_root is not None:
                    graph_scanner.set_workspace_root(prev_root)
                else:
                    graph_scanner._WORKSPACE_ROOT = None
                    graph_scanner.REGISTERED_PROJECTS.clear()


if __name__ == "__main__":
    unittest.main()
