#!/usr/bin/env python3
"""
NetArk (N.E.T.A.R.K.) Core Harness, Epistemic Schema, @D/@M/@C/@G Codebook & Role-Models Verification Suite
===========================================================================================================
Verifies D-01..D-07 & #6..#10 architectural invariants:
  1. 5 Clean Core Memory Nodes (`000_SOUL`, `100_ARCH_RULES`, `200_DECISIONS`, `LEDGER`, `HANDOVER`)
     pass `schema_validator.py --run-oracle` with zero `PotoTypeV0` or `.Friday` pollution.
  2. `schema_validator.py` deterministically rejects `affected_paths` referencing `.gitignore` paths.
  3. `@D/@M/@C/@G` Turn-1 Codebook Map achieves >= 80% compression, renders pure `[DAG]`/`[SYN]`/`[AST]`
     topology edges, and supports deterministic short-code lookup (`000..900`, `C0..Cn`) in `reverse_lookup`.
  4. `.netark/role-models.json` is version-controlled (not gitignored), `.netark/auth.json` is gitignored,
     and `.netark/agents/*.md` frontmatter models 100% align with `role-models.json`.
  5. `.netark/extensions/{epistemic-gate.ts,workspace-guard.ts}` enforce Turn-1 codebook injection,
     `query_library` short-code lookup, and `SEC-PREWRITE-SECRET`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "schemas"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from schemas.schema_validator import is_gitignored_path  # noqa: E402


def test_01_clean_5_core_nodes_and_oracle() -> None:
    print("🧪 [Harness 1] Verifying 5 Clean Core Memory Nodes & Independent Schema Oracle...")
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "schemas" / "schema_validator.py"), "--run-oracle"],
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, f"Oracle failed:\n{proc.stdout}\n{proc.stderr}"
    assert "Causal Topology Graph (5 nodes): PASSED (0 broken links, 0 cycles)" in proc.stdout

    expected_nodes = [
        "memory/codex/000_SOUL.md",
        "memory/codex/100_ARCH_RULES.md",
        "memory/codex/200_DECISIONS.md",
        "memory/LEDGER.md",
        "memory/episodic/HANDOVER.md",
    ]
    for rel in expected_nodes:
        p = PROJECT_ROOT / rel
        assert p.exists(), f"Missing core memory node: {rel}"
        txt = p.read_text(encoding="utf-8")
        assert "PotoTypeV0" not in txt and ".Friday" not in txt, f"V0 residue found in {rel}"
    print("  ✅ Harness 1 passed (5 core clean nodes verified).")


def test_02_block_gitignored_affected_paths() -> None:
    print("🧪 [Harness 2] Verifying Schema Validator Rejects .gitignore Paths in affected_paths...")
    assert is_gitignored_path(".netark/auth.json", PROJECT_ROOT) is True
    assert is_gitignored_path(".netark/models-store.json", PROJECT_ROOT) is True
    assert is_gitignored_path(".netark/role-models.json", PROJECT_ROOT) is False
    assert is_gitignored_path(".netark/auth.example.json", PROJECT_ROOT) is False

    bad_md = (
        '---\nnode_id: "MEM-2026-0099"\nartifact_type: "spec"\naccess_tier: "governed"\n'
        'priority: "high"\nstatus: "draft"\ncreated_at: "2026-11-08"\nupdated_at: "2026-11-08"\n'
        'author:\n  role: "architect"\n  model: "nvidia/nemotron-3-ultra-550b-a55b"\n'
        'reviewer:\n  role: null\n  model: null\n  verdict: null\n'
        'epistemic_profile:\n  fact_count: 1\n  inferred_count: 0\n  hypothesis_count: 0\n  unverified_count: 0\n'
        'verification_oracle: null\n'
        'context_index:\n  domain_code: "200"\n  subdomain: null\n  node_key: "200.BAD-TEST.v1"\n'
        '  artifact_track: "official"\n  facet_tags:\n    - "NetArk:Test:IgnoreCheck"\n'
        '  keywords:\n    - "Test"\n  summary_1line: "Test node binding gitignored auth.json"\n'
        'topology:\n  depends_on:\n    - "000.SOUL.v1"\n  supersedes: []\n  conflicts_with: []\n'
        '  verified_by: []\n  affected_paths:\n    - ".netark/auth.json"\n---\n\n'
        "# Bad Node\n\n- [FACT] Test statement (`schemas/schema_validator.py`).\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".md", dir=str(PROJECT_ROOT / "memory" / "codex"), delete=True, encoding="utf-8") as tf:
        tf.write(bad_md)
        tf.flush()
        proc_bad = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "schemas" / "schema_validator.py"), "--file", tf.name],
            cwd=str(PROJECT_ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        combined = (proc_bad.stdout + proc_bad.stderr).lower()
        assert proc_bad.returncode != 0 and (".gitignore" in combined or "gitignored" in combined), f"Expected gitignore error, got: {combined}"
    print("  ✅ Harness 2 passed.")


def test_03_codebook_topology_map_and_reverse_lookup() -> None:
    print("🧪 [Harness 3] Verifying @D/@M/@C/@G Pure Dashboard Topology Map & Short-Code Reverse Lookup...")
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "auto_update_map.py")],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        check=True,
    )
    idx_path = PROJECT_ROOT / "memory" / "index" / "CONTEXT_INDEX.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    cb = idx.get("codebook_map", {})
    assert cb.get("tier") == "L1-Full"
    assert float(cb.get("compression_ratio_pct", 0.0)) >= 80.0
    compact = cb.get("compact_text", "")
    for required_section in (
        "@D (Dirs):",
        "@M (Nodes):",
        "@C (Scripts):",
        "@G (Topology Graph — DAG / Governance Synapses / Code AST Imports):",
        "[DAG]",
        "[SYN]",
        "[AST]",
    ):
        assert required_section in compact, f"Missing {required_section} in compact_text:\n{compact}"

    rev = cb.get("reverse_lookup", {})
    for code in ("000", "100", "200", "300", "900", "C0", "C1", "C2"):
        assert code in rev, f"Short code {code} missing from reverse_lookup"
    assert rev["000"]["path"] == "memory/codex/000_SOUL.md"
    assert rev["C1"]["path"] == "schemas/netark_guard_core.py"
    print(f"  ✅ Harness 3 passed (Compression={cb['compression_ratio_pct']}%, chars={cb['compact_char_count']}).")


def test_04_role_models_and_subagent_alignment() -> None:
    print("🧪 [Harness 4] Verifying .netark/role-models.json & .netark/agents/*.md Model Alignment...")
    rm_path = PROJECT_ROOT / ".netark" / "role-models.json"
    rm = json.loads(rm_path.read_text(encoding="utf-8"))
    agent_to_role_key = {
        "scout": "scout",
        "architect": "architect",
        "challenger": "challenger",
        "worker": "code",
        "auditor": "audit",
    }
    for agent_name, role_key in agent_to_role_key.items():
        assert role_key in rm, f"Role {role_key} missing from role-models.json"
        expected_model = str(rm[role_key])
        agent_md = (PROJECT_ROOT / ".netark" / "agents" / f"{agent_name}.md").read_text(encoding="utf-8")
        m = re.search(r"^model:\s*(.+)$", agent_md, flags=re.MULTILINE)
        assert m, f"Missing model frontmatter in .netark/agents/{agent_name}.md"
        actual_model = m.group(1).strip().strip("\"'")
        assert actual_model in (expected_model, f"nvidia/{expected_model}"), f"Mismatch for {agent_name}: {actual_model} != {expected_model}"
    print("  ✅ Harness 4 passed.")


def test_05_extensions_turn1_codebook_and_guard_hooks() -> None:
    print("🧪 [Harness 5] Verifying .netark/extensions/ Turn-1 Codebook Injection & Guard Hooks...")
    eg_ts = (PROJECT_ROOT / ".netark" / "extensions" / "epistemic-gate.ts").read_text(encoding="utf-8")
    wg_ts = (PROJECT_ROOT / ".netark" / "extensions" / "workspace-guard.ts").read_text(encoding="utf-8")
    assert "codebook_map" in eg_ts and "compact_text" in eg_ts
    assert "reverse_lookup" in eg_ts
    assert "SEC-PREWRITE-SECRET" in wg_ts
    assert ".Friday" not in eg_ts and ".Friday" not in wg_ts
    print("  ✅ Harness 5 passed.")


if __name__ == "__main__":
    test_01_clean_5_core_nodes_and_oracle()
    test_02_block_gitignored_affected_paths()
    test_03_codebook_topology_map_and_reverse_lookup()
    test_04_role_models_and_subagent_alignment()
    test_05_extensions_turn1_codebook_and_guard_hooks()
    print("\n🎉 [ALL 5 HARNESS TESTS PASSED] NetArk Core Harness, Codebook Topology & Role-Models Verified!")
