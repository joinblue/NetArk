#!/usr/bin/env python3
"""NetArk Agentic Harness Epistemic & Anti-Sycophancy Validator (Pillar 1 Oracle)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

SCHEMAS_DIR = Path(__file__).resolve().parent
if str(SCHEMAS_DIR) not in sys.path:
    sys.path.insert(0, str(SCHEMAS_DIR))

from topology_graph import (  # type: ignore  # noqa: E402
    WIKI_TYPES,
    _match_gitignore_rule,
    check_as06_node_exclusivity,
    check_topology_graph,
    detect_unlinked_topology_references,
    is_gitignored_path,
    load_all_memory_nodes,
    parse_markdown_frontmatter,
)

try:
    import jsonschema  # type: ignore
except ImportError:
    jsonschema = None

EPISTEMIC_TAGS = {
    "fact_count": re.compile(r"(?m)^\s*(?:[-*+]|\d+\.)\s+`?\[FACT\]`?(?!\*\*：)"),
    "inferred_count": re.compile(r"(?m)^\s*(?:[-*+]|\d+\.)\s+`?\[INFERRED\]`?(?!\*\*：)"),
    "hypothesis_count": re.compile(r"(?m)^\s*(?:[-*+]|\d+\.)\s+`?\[HYPOTHESIS\]`?(?!\*\*：)"),
    "unverified_count": re.compile(r"(?m)^\s*(?:[-*+]|\d+\.)\s+`?\[UNVERIFIED\]`?(?!\*\*：)"),
}

OFFICIAL_TYPES = {"constitution", "rule", "adr", "blueprint", "spec", "audit"}
PROSE_LINE_BUDGETS: Dict[str, int] = {
    "constitution": 50, "rule": 50, "adr": 50, "blueprint": 250, "spec": 160, "audit": 160,
    "wiki": 500, "note": 500, "sop": 500, "glossary": 500, "digest": 500,
}
AS05_PORTABILITY_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("Linux User Path", re.compile(r"/home/(?!<user>)[A-Za-z0-9._-]+/")),
    ("macOS User Path", re.compile(r"/Users/(?!<user>)[A-Za-z0-9._-]+/")),
    ("Windows User Path", re.compile(r"\b[A-Za-z]:\\Users\\(?!<user>)[A-Za-z0-9._-]+\\")),
    ("Local file:/// URI", re.compile(r"file:///[A-Za-z0-9._~-]+")),
]


def load_valid_taxonomy_codes(project_root: Path) -> set[str]:
    default_codes = {f"{i}00" for i in range(10)} | {"310", "320", "330", "510", "910"}
    tax_path = project_root / "memory" / "index" / "TAXONOMY.json"
    if not tax_path.exists():
        return default_codes
    try:
        data = json.loads(tax_path.read_text(encoding="utf-8"))
    except Exception:
        return default_codes
    domains = data.get("domains", {})
    if not isinstance(domains, dict) or not domains:
        return default_codes
    valid: set[str] = set()
    for code, meta in domains.items():
        valid.add(str(code))
        subs = meta.get("subdomains", {}) if isinstance(meta, dict) else {}
        if isinstance(subs, dict):
            valid.update(str(sub_code) for sub_code in subs.keys())
    return valid or default_codes


def count_prose_lines(body: str) -> int:
    in_fence = False
    prose_count = 0
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or stripped.startswith("#"):
            continue
        if (stripped.startswith("|") and stripped.endswith("|")) or re.match(r"^[-*_]{3,}$", stripped):
            continue
        prose_count += 1
    return prose_count


def check_as05_portability(raw_content: str) -> List[str]:
    errors: List[str] = []
    for label, pattern in AS05_PORTABILITY_PATTERNS:
        match = pattern.search(raw_content)
        if match:
            errors.append(
                f"[AS-05 Portability] 偵測到本機絕對路徑或使用者名稱洩漏 ({label}: `{match.group(0)}`)："
                "記憶節點內一律改用專案相對路徑或 `/home/<user>/` 佔位符。"
            )
    return errors


def generate_prescription_skeleton(md_path: Path, project_root: Path, fm: Dict[str, Any] | None) -> str:
    today_str = time.strftime("%Y-%m-%d")
    rel_path = str(md_path.relative_to(project_root)) if md_path.is_relative_to(project_root) else md_path.name
    fm_dict = fm if isinstance(fm, dict) else {}
    ctx_idx = fm_dict.get("context_index") if isinstance(fm_dict.get("context_index"), dict) else {}
    node_id = fm_dict.get("node_id", "MEM-2026-0099")
    artifact_type = fm_dict.get("artifact_type", "spec")
    node_key = ctx_idx.get("node_key", "300.MODULE-SPEC.v1")
    domain_code = ctx_idx.get("domain_code", "300")

    has_existing_header = isinstance(fm, dict) and bool(
        (fm.get("node_id") or fm.get("id"))
        and (ctx_idx.get("node_key") or ctx_idx.get("summary_1line") or fm.get("title") or fm.get("artifact_type"))
    )
    if has_existing_header:
        return (
            f"🔧 [Prescription Skeleton | 1-Turn 自癒處方籤範本 ({rel_path} — Targeted Fix Hint)]\n"
            f"偵測到 `{rel_path}` 已具備 YAML Frontmatter (`{node_id}` / `{node_key}`)，無需覆寫整份 60 行模板，請僅針對上方錯誤行進行局部修補 (`edit`)：\n"
            f"  1. [AS-01/Author]: 確保 `author.model` 與 `reviewer.model` 為不同家族模型，且 `reviewer.verdict: \"APPROVED\"`。\n"
            f"  2. [AS-02/Epistemic]: 內文列表行首 (`- [FACT]` / `1. [INFERRED]`) 實際數量須與 `epistemic_profile` 統計完全一致。\n"
            f"  3. [ProseBudget]: 若散文行數超標 (`rule<=50`, `spec<=80`, `decision<=60`)，請將段落改寫為 Markdown 表格 (`|...|`) 或程式碼區塊。\n"
            f"  4. [AS-05/Portability]: 移除本機絕對路徑 (`/home/...`, `file:///...`)，改為專案相對路徑。\n"
            f"  5. [AS-06/Topology]: 若宣告 `supersedes` 舊節點，請先將舊節點 `status` 降級為 `deprecated` 或 `archived`。\n"
            f"  6. [Section/Schema]: 檢查必填欄位 (`verification_oracle`, `context_index`, `topology`) 與 `## §` 章節結構。"
        )
    return (
        f"🔧 [Prescription Skeleton | 1-Turn 自癒處方籤範本 ({rel_path})]\n"
        f"請直接複製以下合法 YAML Frontmatter 與三段式認知內文骨架覆寫或修補 `{rel_path}`：\n"
        f"```markdown\n---\n"
        f'node_id: "{node_id}"\nartifact_type: "{artifact_type}"\naccess_tier: "standard"\npriority: "high"\n'
        f'status: "verified"\ncreated_at: "{today_str}"\nupdated_at: "{today_str}"\n'
        f'author:\n  role: "architect"\n  model: "nvidia/nemotron-3-ultra-550b-a55b"\n'
        f'reviewer:\n  role: "challenger"\n  model: "deepseek-ai/deepseek-v4.1-flash"\n  verdict: "APPROVED"\n'
        f"epistemic_profile:\n  fact_count: 1\n  inferred_count: 1\n  hypothesis_count: 0\n  unverified_count: 0\n"
        f'verification_oracle:\n  type: "schema_check"\n  command: "python3 schemas/schema_validator.py --file {rel_path}"\n'
        f'  expected_exit_code: 0\n  falsifiable_criterion: "若 {rel_path} 未通過 Schema 驗證，則本記憶節點判定無效。"\n'
        f'context_index:\n  domain_code: "{domain_code}"\n  node_key: "{node_key}"\n'
        f'  facet_tags:\n    - "NetArk:Architecture:Spec:Governance"\n  keywords:\n    - "{node_key}"\n    - "Governance"\n'
        f'  summary_1line: "請填寫 10~160 字元之單行精準摘要，供漸進式揭露索引注入。"\n'
        f'topology:\n  depends_on:\n    - "000.SOUL.v1"\n  supersedes: []\n  conflicts_with: []\n'
        f'  verified_by:\n    - "schemas/schema_validator.py"\n  affected_paths:\n    - "schemas/schema_validator.py"\n---\n\n'
        f"# 📌 `{node_key}` ({node_id}) — 節點標題\n\n"
        f"- [FACT] 客觀可驗證事實陳述（⚠️ 標籤必須緊接在列表符號 `- `、`* ` 或 `1. ` 後方行首，不可寫在一般段落、表格內或列表句尾！）。\n"
        f"- [INFERRED] 根據系統架構推導之設計結論（請確保列表行首包含至少一處 `- [FACT]` 或 `- [INFERRED]`）。\n```"
    )


def validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any], label: str) -> List[str]:
    errors: List[str] = []
    if jsonschema is not None:
        validator = jsonschema.Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            loc = ".".join(str(p) for p in err.path) or "<root>"
            errors.append(f"[{label}] {loc}: {err.message}")
    else:
        for req in schema.get("required", []):
            if req not in data:
                errors.append(f"[{label}] Missing required field: {req}")
    return errors


def validate_document(
    md_path: Path,
    project_root: Path,
    header_schema: Dict[str, Any],
    node_schema: Dict[str, Any],
    run_oracle: bool = False,
    all_nodes: Dict[str, Dict[str, Any]] | None = None,
) -> Tuple[Dict[str, Any] | None, List[str]]:
    errors: List[str] = []
    raw_content = md_path.read_text(encoding="utf-8")
    errors.extend(check_as05_portability(raw_content))

    try:
        fm, body = parse_markdown_frontmatter(md_path)
    except Exception as exc:
        errors.append(str(exc))
        return None, errors

    errors.extend(validate_against_schema(fm, header_schema, "ArtifactHeaderSchema"))
    errors.extend(validate_against_schema(fm, node_schema, "ContextNodeSchema"))

    ctx_idx = fm.get("context_index") if isinstance(fm.get("context_index"), dict) else {}
    valid_tax_codes = load_valid_taxonomy_codes(project_root)
    dom_code = ctx_idx.get("domain_code")
    if isinstance(dom_code, str) and dom_code and dom_code not in valid_tax_codes:
        errors.append(f"[AS-07 Taxonomy Unregistered] 領域碼 {dom_code} 尚未註冊於 memory/index/TAXONOMY.json，請先編輯 TAXONOMY.json 註冊該分類或改用既有分類碼。")
    sub_code = ctx_idx.get("subdomain") or fm.get("subdomain")
    if isinstance(sub_code, str) and sub_code and sub_code not in valid_tax_codes:
        errors.append(f"[AS-07 Taxonomy Unregistered] 子領域碼 {sub_code} 尚未註冊於 memory/index/TAXONOMY.json，請先編輯 TAXONOMY.json 註冊該分類或改用既有分類碼。")

    artifact_type = fm.get("artifact_type", "")
    is_official = artifact_type in OFFICIAL_TYPES
    budget = PROSE_LINE_BUDGETS.get(artifact_type)
    prose_lines = count_prose_lines(body)
    if budget is not None and prose_lines > budget:
        errors.append(
            f"[ProseBudget] 純散文行數超標 ({prose_lines} > {budget} 行，類型={artifact_type})："
            "請將冗長文字轉化為 Markdown 表格或 Mermaid 拓撲圖以降低散文膨脹。"
        )
    if md_path.name == "LEDGER.md" and len(raw_content.splitlines()) > 80:
        errors.append(f"[ProseBudget / LEDGER] memory/LEDGER.md 總行數超標 ({len(raw_content.splitlines())} > 80 行)：請立即歸檔已完工項目！")
    if md_path.name == "HANDOVER.md" and len(raw_content.splitlines()) > 65:
        errors.append(f"[ProseBudget / HANDOVER] memory/episodic/HANDOVER.md 總行數超標 ({len(raw_content.splitlines())} > 65 行)：請精簡為最新交接狀態！")

    content_checksum = fm.get("content_checksum")
    if content_checksum:
        body_for_hash = body.lstrip("\r\n") if body.startswith("\r\n") else (body.lstrip("\n") if body.startswith("\n") else body)
        actual_checksum = hashlib.sha256(body_for_hash.encode("utf-8")).hexdigest()[:16]
        alt_checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        if content_checksum not in (actual_checksum, alt_checksum):
            errors.append(f"[Checksum Mismatch] 內文 content_checksum ({content_checksum}) 與實際計算值 ({actual_checksum}) 不符！")

    status = fm.get("status")
    author_obj = fm.get("author") if isinstance(fm.get("author"), dict) else {}
    reviewer_obj = fm.get("reviewer") if isinstance(fm.get("reviewer"), dict) else {}
    orig_model, rev_model, verdict = author_obj.get("model", ""), reviewer_obj.get("model", ""), reviewer_obj.get("verdict", "")

    if is_official and status in ("verified", "archived"):
        if not reviewer_obj:
            errors.append(f"[AS-01 Anti-Sycophancy] 公文軌文件進入「{status}」狀態必須具備跨模型 reviewer 審查！")
        elif orig_model == rev_model:
            errors.append(f"[AS-01 Anti-Sycophancy] 禁止同模型自審自核！產出模型 ({orig_model}) 與審查模型 ({rev_model}) 相同，不可進入「{status}」狀態。")
        elif verdict != "APPROVED":
            errors.append(f"[AS-01 Anti-Sycophancy] 狀態為「{status}」時，reviewer.verdict 必須為 APPROVED（目前為 {verdict}）。")
    elif not is_official and reviewer_obj and status in ("verified", "archived") and verdict and verdict != "APPROVED":
        errors.append(f"[AS-01 Anti-Sycophancy] 狀態為「{status}」時，reviewer.verdict 必須為 APPROVED（目前為 {verdict}）。")

    profile = fm.get("epistemic_profile") if isinstance(fm.get("epistemic_profile"), dict) else {}
    actual_counts: Dict[str, int] = {}
    for key, pattern in EPISTEMIC_TAGS.items():
        actual = len(pattern.findall(body))
        actual_counts[key] = actual
        if profile and profile.get(key, -1) != -1 and actual != profile.get(key, -1):
            errors.append(
                f"[AS-02 Epistemic Honesty] 內文標籤數量與標頭宣告不符：{key} 宣告為 {profile.get(key, -1)}，但內文實際匹配 {actual} 次（⚠️ 標籤必須位於 Markdown 列表行首，如 `- [FACT] 內容...` 或 `1. [INFERRED] 內容...`；寫在一般段落、表格內或列表句尾均不計入）。"
            )

    if status in ("verified", "archived"):
        if actual_counts.get("unverified_count", 0) > 0:
            errors.append(f"[AS-02 Epistemic Gate] 進入「{status}」之記憶節點不得含有 [UNVERIFIED] 未驗證段落（目前有 {actual_counts['unverified_count']} 處）。")
        if is_official and (actual_counts.get("fact_count", 0) + actual_counts.get("inferred_count", 0) == 0):
            errors.append("[AS-02 Epistemic Gate] 記憶節點內文必須至少包含一處位於 Markdown 列表行首的 [FACT] 或 [INFERRED] 標記（格式範例：`- [FACT] 內容...` 或 `1. [INFERRED] 內容...`；寫在純文字段落、表格內或列表句尾均不計入！）。")

    topo = fm.get("topology") if isinstance(fm.get("topology"), dict) else {}
    for rel_path in (topo.get("affected_paths") if isinstance(topo.get("affected_paths"), list) else []):
        if is_gitignored_path(str(rel_path), project_root):
            errors.append(f"[AS-03 Gitignore Violation] topology.affected_paths 禁止綁定 .gitignore 忽略之私密金鑰或執行期快取路徑: {rel_path}")
            continue
        if not (project_root / rel_path).resolve().exists():
            errors.append(f"[AS-03 Grounding] topology.affected_paths 指向不存在的路徑: {rel_path}")

    for stub_rel in (topo.get("stub_paths") if isinstance(topo.get("stub_paths"), list) else []):
        if not isinstance(stub_rel, str) or not stub_rel.strip():
            continue
        stub_target = (project_root / stub_rel).resolve()
        if not stub_target.exists():
            errors.append(f"[AS-03 Stub Grounding] topology.stub_paths 指向不存在的路徑: {stub_rel}")
        elif status in ("stub_ready", "verified") and stub_rel.endswith(".py") and stub_target.is_file():
            compile_proc = subprocess.run([sys.executable, "-m", "py_compile", str(stub_target)], cwd=str(project_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
            if compile_proc.returncode != 0:
                errors.append(f"[AS-03 Stub Syntax Failed] 空殼或測試檔 `{stub_rel}` 語法編譯失敗: {(compile_proc.stderr or compile_proc.stdout or '').strip()}")

    if topo.get("supersedes") or topo.get("conflicts_with"):
        lookup_nodes = dict(all_nodes) if all_nodes is not None else load_all_memory_nodes(project_root)
        node_id = fm.get("node_id", md_path.stem)
        lookup_nodes[node_id] = fm
        errors.extend(check_as06_node_exclusivity(node_id, fm, lookup_nodes))

    if run_oracle:
        oracle = fm.get("verification_oracle")
        if isinstance(oracle, dict) and oracle.get("command"):
            cmd, expected_code = oracle.get("command", ""), oracle.get("expected_exit_code", 0)
            if cmd and status != "stub_ready":
                safe_cmd = re.sub(r"\s+--run-oracle\b", "", cmd) if "schema_validator.py" in cmd else cmd
                proc = subprocess.run(safe_cmd, shell=True, cwd=str(project_root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
                if proc.returncode != expected_code:
                    errors.append(f"[AS-03 Oracle Failed] 指令 `{cmd}` 回傳碼 {proc.returncode} != 預期 {expected_code}。輸出: {proc.stderr.strip() or proc.stdout.strip()}")
        elif is_official:
            errors.append("[AS-03 Oracle] 公文軌文件缺少 verification_oracle 執行命令！")

    return fm, errors


def _emit_post_pass_warnings(
    md_file: Path, project_root: Path, node_id: str, fm: Dict[str, Any], existing_nodes: Dict[str, Dict[str, Any]]
) -> None:
    if fm.get("status") == "draft" and fm.get("artifact_type") in ("blueprint", "spec"):
        topo_aff = (fm.get("topology", {}) or {}).get("affected_paths", []) or []
        for aff_rel in topo_aff:
            if not isinstance(aff_rel, str) or not (aff_rel.endswith(".ts") or aff_rel.endswith(".py")) or Path(aff_rel).name.startswith("test_"):
                continue
            aff_target = (project_root / aff_rel).resolve()
            if aff_target.is_file() and len(aff_target.read_text(encoding="utf-8", errors="ignore").splitlines()) > 500:
                aff_lines = len(aff_target.read_text(encoding="utf-8", errors="ignore").splitlines())
                print(f"   ⚠️ [Modularity Warning] 目標檔案 `{aff_rel}` 已達 {aff_lines} 行 (> 500 行)：請優先規劃為獨立模組或 `.netark/extensions/` 插件，避免繼續堆疊上帝腳本！")
    try:
        _, body_text = parse_markdown_frontmatter(md_file)
        lookup_for_notice = {**existing_nodes, node_id: fm}
        for n in detect_unlinked_topology_references(node_id, fm, body_text, lookup_for_notice):
            print(f"   ⚠️ {n}")
    except Exception:  # noqa: silent-except
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate NetArk Agentic Harness Memory Nodes.")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--file", help="Validate a single Markdown file")
    parser.add_argument("--all", action="store_true", help="Validate all documents across memory/ (default)")
    parser.add_argument("--run-oracle", action="store_true", help="Execute verification_oracle commands")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    schemas_dir = project_root / "schemas"
    header_schema = json.loads((schemas_dir / "artifact_header.schema.json").read_text(encoding="utf-8"))
    node_schema = json.loads((schemas_dir / "context_node.schema.json").read_text(encoding="utf-8"))

    md_files = (
        [Path(args.file).resolve()]
        if args.file
        else sorted(p for p in (project_root / "memory").rglob("*.md") if p.name != "CONTEXT_MAP.md")
    )
    if not md_files:
        print("⚠️ No governed Markdown memory nodes found in memory/.")
        return 0

    existing_nodes = load_all_memory_nodes(project_root)
    all_nodes: Dict[str, Dict[str, Any]] = {}
    total_errors = 0

    for md_file in md_files:
        rel = md_file.relative_to(project_root) if md_file.is_relative_to(project_root) else md_file
        fm, errs = validate_document(md_file, project_root, header_schema, node_schema, args.run_oracle, all_nodes=existing_nodes)
        if fm and "node_id" in fm:
            all_nodes[fm["node_id"]] = fm
        if errs:
            total_errors += len(errs)
            print(f"❌ {rel}: FAILED ({len(errs)} errors)")
            for e in errs:
                print(f"   - {e}")
            print(generate_prescription_skeleton(md_file, project_root, fm))
        else:
            node_id = fm.get("node_id", "UNKNOWN") if fm else "UNKNOWN"
            node_key = fm.get("context_index", {}).get("node_key", "") if fm else ""
            status = fm.get("status", "") if fm else ""
            print(f"✅ {rel} [{node_id} | {node_key} | {status}]: PASSED")
            if fm:
                _emit_post_pass_warnings(md_file, project_root, node_id, fm, existing_nodes)

    if not args.file and all_nodes:
        topo_errors = check_topology_graph(all_nodes)
        if topo_errors:
            total_errors += len(topo_errors)
            print("❌ Topology Graph Check: FAILED")
            for e in topo_errors:
                print(f"   - {e}")
        else:
            print(f"✅ Causal Topology Graph ({len(all_nodes)} nodes): PASSED (0 broken links, 0 cycles)")

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
