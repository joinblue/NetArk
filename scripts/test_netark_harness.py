#!/usr/bin/env python3
"""
NetArk (N.E.T.A.R.K.) Core Harness, Epistemic Schema, @D/@M/@C/@G Codebook & V1.2 Code Hygiene Verification Suite
=================================================================================================================
Verifies D-01..D-07, #6..#10 & V1.2 Code Hygiene (P1/P2/GATE-01/GATE-02) architectural invariants:
  1. 5 Clean Core Memory Nodes (`000_SOUL`, `100_ARCH_RULES`, `200_DECISIONS`, `LEDGER`, `HANDOVER`)
     pass `schema_validator.py --run-oracle` with zero `PotoTypeV0` or `.Friday` pollution.
  2. `schema_validator.py` deterministically rejects `affected_paths` referencing `.gitignore` paths.
  3. `@D/@M/@C/@G` Turn-1 Codebook Map achieves >= 80% compression, renders `[DAG]`/`[SYN]`/`[AST]`/`[HYG-AST]`/`[HYG-DEBUG]`
     entries, and supports deterministic short-code lookup (`000..900`, `C0..Cn`) in `reverse_lookup`.
  4. `.netark/role-models.json` is version-controlled, `.netark/auth.json` is gitignored,
     and `.netark/agents/*.md` frontmatter models 100% align with `role-models.json`.
  5. `.netark/extensions/{epistemic-gate.ts,workspace-guard.ts}` enforce Turn-1 codebook injection,
     `query_library` short-code lookup, and `SEC-PREWRITE-SECRET`.
  6. `P1` (`CODE-ARROW-NESTING` > 4), `P2` (`CODE-SILENT-EXCEPT`), `GATE-01` (all non-test `.py` <= 400 lines
     and split module caps), and `GATE-02` (401~550 soft warning buffer, > 550 with `new > old` hard block).
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

from schemas.code_hygiene_ast import check_python_ast_hygiene  # noqa: E402
from schemas.schema_validator import is_gitignored_path  # noqa: E402
from scripts.netark_guard_daemon import _check_governance_pre_write  # noqa: E402


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
    assert re.search(r"Causal Topology Graph \(\d+ nodes\): PASSED \(0 broken links, 0 cycles\)", proc.stdout), (
        f"Unexpected oracle topology summary:\n{proc.stdout}"
    )

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
        "@R (Write Route):",
        "@M (Nodes):",
        "@C (Scripts):",
        "@G (",
        "[DAG]",
        "[SYN]",
        "[AST]",
        "[HYG-AST]",
        "[HYG-DEBUG]",
        "[DELEGATE]",
    ):
        assert required_section in compact, f"Missing {required_section} in compact_text:\n{compact}"

    (PROJECT_ROOT / "memory" / "wiki").mkdir(parents=True, exist_ok=True)
    tmp_wiki = PROJECT_ROOT / "memory" / "wiki" / "310_TEST_AUTO_INIT_MEMO.md"
    try:
        tmp_wiki.write_text("# 測試自動補標頭備忘錄\n\n- [FACT] 驗證開架區免手寫標頭自動立案。\n", encoding="utf-8")
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "sync_doc_metadata.py"), "--file", str(tmp_wiki), "--project-root", str(PROJECT_ROOT)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            check=True,
        )
        synced_txt = tmp_wiki.read_text(encoding="utf-8")
        assert synced_txt.startswith("---\n") and 'artifact_type: "note"' in synced_txt and '"000.SOUL.v1"' in synced_txt
    finally:
        if tmp_wiki.exists():
            tmp_wiki.unlink()

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
    elt_ts = (PROJECT_ROOT / ".netark" / "extensions" / "epistemic-library-tools.ts").read_text(encoding="utf-8")
    gsp_ts = (PROJECT_ROOT / ".netark" / "extensions" / "guard-shell-parser.ts").read_text(encoding="utf-8")
    assert "codebook_map" in eg_ts and "compact_text" in eg_ts and "check_python_ast_hygiene" in eg_ts
    assert "reverse_lookup" in eg_ts
    assert "SEC-PREWRITE-SECRET" in wg_ts and "editsText" in wg_ts
    assert "recordGuardAuditEvent" in wg_ts
    assert "soc2_audit.jsonl" in wg_ts
    assert "歷史與本輪攔截統計" in wg_ts
    assert "query_library" in elt_ts and "code_intelligence_map" in elt_ts and "resolveToolExecArgs" in elt_ts
    assert "parseShellCommandQuoteAware" in gsp_ts and "isReadOnlyBashCommand" in gsp_ts
    node_check = (
        "import { registerEpistemicLibraryTools } from './.netark/extensions/epistemic-library-tools.ts';"
        "const tools={}; registerEpistemicLibraryTools({registerTool:(t)=>{tools[t.name]=t;}});"
        "const r1=await tools.query_library.execute('call-1',{query:'100'},undefined,undefined,{cwd:process.cwd()});"
        "if(!r1?.content?.[0]?.text?.includes('100.ARCH-RULES.v1')) throw new Error('query_library 5-arg failed');"
        "const r2=await tools.code_intelligence_map.execute('call-2',{limit:2},undefined,undefined,{cwd:process.cwd()});"
        "if(!r2?.content?.[0]?.text) throw new Error('code_intelligence_map 5-arg failed');"
    )
    subprocess.run(["node", "--experimental-strip-types", "--input-type=module", "-e", node_check], cwd=str(PROJECT_ROOT), check=True, capture_output=True)
    for ts_file in sorted((PROJECT_ROOT / ".netark" / "extensions").glob("*.ts")):
        ts_src = ts_file.read_text(encoding="utf-8")
        assert ".Friday" not in ts_src and "PotoTypeV0" not in ts_src
        assert "export default function" in ts_src, f"Missing default factory export in {ts_file.name}"
    print("  ✅ Harness 5 passed.")


def test_06_code_hygiene_p1_p2_and_modularity_gates() -> None:
    print("🧪 [Harness 6] Verifying P1 (Arrow Nesting > 4), P2 (Silent Except), GATE-01 (<= 400 Lines) & GATE-02 (400/550 Buffer)...")
    deep_code = "def deep_fn(items):\n if items:\n  for x in items:\n   while x > 0:\n    try:\n     if x == 1:\n      return 1\n    except ValueError:\n     return 0\n"
    res_p1 = check_python_ast_hygiene(deep_code, "scripts/sample.py")
    assert res_p1 is not None and res_p1["allowed"] is False and res_p1["code"] == "CODE-ARROW-NESTING", f"Expected P1 block, got: {res_p1}"

    elif_code = "def flat_elif(x):\n if x == 1: return 1\n elif x == 2: return 2\n elif x == 3: return 3\n elif x == 4: return 4\n elif x == 5: return 5\n else: return 0\n"
    assert check_python_ast_hygiene(elif_code, "scripts/sample.py") is None

    silent_pass = "def f():\n try:\n  x = 1\n except Exception:\n  pass\n"
    res_p2 = check_python_ast_hygiene(silent_pass, "scripts/sample.py")
    assert res_p2 is not None and res_p2["allowed"] is False and res_p2["code"] == "CODE-SILENT-EXCEPT", f"Expected P2 block, got: {res_p2}"

    silent_dots = "def f():\n try:\n  x = 1\n except Exception:\n  ...\n"
    res_p2_dots = check_python_ast_hygiene(silent_dots, "scripts/sample.py")
    assert res_p2_dots is not None and res_p2_dots["allowed"] is False and res_p2_dots["code"] == "CODE-SILENT-EXCEPT"

    exempt_pass = "def f():\n try:\n  x = 1\n except Exception:  # noqa: silent-except\n  pass\n"
    assert check_python_ast_hygiene(exempt_pass, "scripts/sample.py") is None

    py_files = [p for p in list((PROJECT_ROOT / "schemas").glob("*.py")) + list((PROJECT_ROOT / "scripts").glob("*.py")) if not p.name.startswith("test_")]
    for p in py_files:
        src_txt = p.read_text(encoding="utf-8")
        lc = len(src_txt.splitlines())
        assert lc <= 400, f"GATE-01 violation: {p.relative_to(PROJECT_ROOT)} has {lc} lines (> 400)"
        if p.name != "netark_guard_core.py":
            hyg = check_python_ast_hygiene(src_txt, str(p.relative_to(PROJECT_ROOT)))
            assert hyg is None, f"Self-hygiene violation in {p.relative_to(PROJECT_ROOT)}: {hyg}"

    budget_caps = {
        "schemas/code_hygiene_ast.py": 260, "schemas/codebook_compiler.py": 340,
        "scripts/auto_update_map.py": 350, "scripts/netark_guard_daemon.py": 394,
        "schemas/topology_graph.py": 300, "schemas/schema_validator.py": 370,
        "schemas/doc_initializer.py": 280, "scripts/sync_doc_metadata.py": 320,
        "scripts/test_netark_harness.py": 330, ".netark/extensions/guard-shell-parser.ts": 320,
        ".netark/extensions/workspace-guard.ts": 380, ".netark/extensions/epistemic-library-tools.ts": 320,
        ".netark/extensions/epistemic-gate.ts": 360,
    }
    for rel_file, max_lc in budget_caps.items():
        fp = PROJECT_ROOT / rel_file
        assert fp.exists(), f"Missing split module: {rel_file}"
        lc = len(fp.read_text(encoding="utf-8").splitlines())
        assert lc <= max_lc, f"Budget cap violation: {rel_file} has {lc} lines (> {max_lc})"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        (tmp_root / "src").mkdir(parents=True, exist_ok=True)
        (tmp_root / "src" / "mod.py").write_text("x = 1\n" * 420, encoding="utf-8")
        res_buf = _check_governance_pre_write("write_file", {"Path": "src/mod.py", "Content": "x = 1\n" * 425}, cwd=tmp)
        assert res_buf is None or (res_buf.get("allowed") is True and "Modularity Buffer" in str(res_buf.get("warning", ""))), f"Expected 401~550 buffer pass, got: {res_buf}"

        (tmp_root / "src" / "big.py").write_text("x = 1\n" * 555, encoding="utf-8")
        res_hard = _check_governance_pre_write("write_file", {"Path": "src/big.py", "Content": "x = 1\n" * 556}, cwd=tmp)
        assert res_hard is not None and res_hard.get("allowed") is False and res_hard.get("code") == "MODULARITY-GATE", f"Expected >550 (+1 line) hard block, got: {res_hard}"
        res_shrink = _check_governance_pre_write("write_file", {"Path": "src/big.py", "Content": "x = 1\n" * 552}, cwd=tmp)
        assert res_shrink is None or res_shrink.get("allowed") is True, f"Expected shrink on >550 file to pass, got: {res_shrink}"
    print("  ✅ Harness 6 passed (P1, P2, GATE-01 <= 400 lines, GATE-02 400/550 tiered gate verified).")


def test_07_ribc_spec_gate() -> None:
    print("🧪 [Harness 7] Verifying SPEC-RIBC-GATE Logic...")
    import tempfile, subprocess
    test_js = """
import { validateRibcConstructionTask, buildSpecialistSystemPrompt } from "./.netark/extensions/ribc-spec-gate.ts";
let failCount = 0;
const assertEqual = (expected, actual, msg) => {
    if (expected !== actual) { console.error(`FAIL: ${msg}. Expected ${expected}, got ${actual}`); failCount++; }
};
const res1 = validateRibcConstructionTask("檢查目錄", "scout");
assertEqual(true, res1.allowed, "Test 1");
const res2 = validateRibcConstructionTask("修正 foo.py 行號 L12 的 typo", "code");
assertEqual(true, res2.allowed, "Test 2");
const res3 = validateRibcConstructionTask("新建模組 wallet.py 並避免 typo", "code");
assertEqual(false, res3.allowed, "Test 3");
const res4 = validateRibcConstructionTask("實作這個功能，字數已經夠長了，但我完全沒有加上防呆，也沒有任何資料格式相關的字眼，純粹來亂的", "code");
assertEqual(false, res4.allowed, "Test 4");
assertEqual(true, res4.prescription.includes("SPEC-RIBC-GATE"), "Test 4 msg");
const res5 = validateRibcConstructionTask("請依據規格實作模組。這段敘述字數非常夠，且包含必要的邊界防護與異常處理，同時有完整的型別契約與數值精度要求。字數必須大於45字元才行，我們再多打幾個字湊滿。", "worker");
assertEqual(true, res5.allowed, "Test 5");
const codePrompt = buildSpecialistSystemPrompt("code", "test-model");
assertEqual(true, codePrompt.includes("R-I-B-C"), "Test 6 code");
const scoutPrompt = buildSpecialistSystemPrompt("scout", "test-model");
assertEqual(false, scoutPrompt.includes("R-I-B-C"), "Test 6 scout");
if (failCount > 0) process.exit(1);
"""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", dir=str(PROJECT_ROOT)) as tmp:
        tmp.write(test_js)
        tmp.flush()
        proc = subprocess.run(["node", "--experimental-strip-types", tmp.name], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        assert proc.returncode == 0, f"JS test failed: {proc.stderr}"
    print("  ✅ Harness 7 passed (SPEC-RIBC-GATE logic and zero-bloat prefix verified).")


if __name__ == "__main__":
    test_01_clean_5_core_nodes_and_oracle()
    test_02_block_gitignored_affected_paths()
    test_03_codebook_topology_map_and_reverse_lookup()
    test_04_role_models_and_subagent_alignment()
    test_05_extensions_turn1_codebook_and_guard_hooks()
    test_06_code_hygiene_p1_p2_and_modularity_gates()
    test_07_ribc_spec_gate()
    print("\n🎉 [ALL 7 HARNESS TESTS PASSED] NetArk Core Harness Verified!")
