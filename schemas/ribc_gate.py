#!/usr/bin/env python3
"""NetArk v3.2 SPEC-RIBC-GATE — Pure Python 4D Task Dispatch Validator.

Enforces Role/Path [R], Invariants [I], Boundaries [B], and Contracts [C]
before allowing Google Antigravity (`invoke_subagent`) or Claude Code (`Agent` /
`Task`) to spawn construction subagents. Zero third-party dependencies.
"""

from __future__ import annotations

import argparse, hashlib, json, re, sys, time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Only explicitly read-only / planning / review subagent roles bypass RIBC construction checks.
RE_READONLY_ROLE = re.compile(
    r"\b(?:research(?:er)?|explor(?:e|er)|search(?:er)?|review(?:er)?|audit(?:or)?|"
    r"scout|challenger|architect|plan(?:ner)?|"
    r"read[-_ ]?only|doc[-_ ]?reader|調查|檢索|搜尋|唯讀|審查|稽核)\b",
    re.IGNORECASE,
)

# Trivial single-line or typo fixes bypass RIBC only when not creating a new module.
RE_MICRO_FIX = re.compile(
    r"(?:\btypo\b|\brename\b|移除未使用|單行修正|修正錯字|調整縮排|行號)",
    re.IGNORECASE,
)
RE_NEW_MODULE = re.compile(
    r"(?:新建|新增模組|建立新檔|新模組|撰寫新|create\s+(?:a\s+)?new\s+(?:file|module|script)|"
    r"new\s+(?:module|file|service)|implement\s+from\s+scratch)",
    re.IGNORECASE,
)

# 4D R-I-B-C structural dimension patterns:
RE_DIM_R_ROLE_PATH = re.compile(
    r"(?:\[\s*R(?:\s*[-:：]|\]|\b)|目標路徑|模組路徑|檔案路徑|職責邊界|"
    r"[a-zA-Z0-9_./-]+\.(?:py|ts|tsx|js|jsx|rs|go|sh|sql|json|yaml|yml|md|toml)\b)",
    re.IGNORECASE,
)
RE_DIM_I_INVARIANT = re.compile(
    r"(?:\[\s*I(?:\s*[-:：]|\]|\b)|不變量|行數|上限|約束|預算|"
    r"<=\s*\d+\s*(?:行|lines?)|\bmax[_-]?lines\b|\bline\s+budget\b|\binvariant)",
    re.IGNORECASE,
)
RE_DIM_B_BOUNDARY = re.compile(
    r"(?:\[\s*B(?:\s*[-:：]|\]|\b)|邊界|防護|異常|例外|空值|負數|越界|"
    r"early[-_ ]?return|嵌套|巢狀|\bguard\b|\bexception\b|\berror\b|"
    r"\bvalueerror\b|\btypeerror\b|\bnone\b)",
    re.IGNORECASE,
)
RE_DIM_C_CONTRACT = re.compile(
    r"(?:\[\s*C(?:\s*[-:：]|\]|\b)|型別|契約|精度|回傳|簽章|介面|"
    r"\btype\b|\bdecimal\b|\bint\b|\bstr\b|\bfloat\b|\bbool\b|"
    r"\bdict\b|\blist\b|\btuple\b|\binterface\b|\breturn\b|\bschema\b)",
    re.IGNORECASE,
)

MIN_SPEC_LENGTH = 60
SUBAGENT_TOOL_NAMES = ("invoke_subagent", "Agent", "Task", "subagent", "dispatch_specialist")


def validate_ribc_construction_task(
    task_text: str,
    role_or_type: str = "",
) -> Tuple[bool, str]:
    """Validate a single subagent task prompt against R-I-B-C 4D criteria."""
    clean_role = (role_or_type or "").strip()
    if clean_role and RE_READONLY_ROLE.search(clean_role):
        return True, ""

    text = (task_text or "").strip()
    if not text:
        return False, _format_prescription(
            clean_role or "unspecified",
            ["派工指令為空（Empty task prompt）"],
        )

    if RE_MICRO_FIX.search(text) and not RE_NEW_MODULE.search(text):
        return True, ""

    missing: List[str] = []
    if not RE_DIM_R_ROLE_PATH.search(text):
        missing.append("1. [R - Role & Path]: 缺少目標模組/檔案路徑（如 xxx.py）與單一職責定義")
    if not RE_DIM_I_INVARIANT.search(text):
        missing.append("2. [I - Invariants]: 缺少業務不變量與單檔行數上限約束（如 <=350行）")
    if not RE_DIM_B_BOUNDARY.search(text):
        missing.append("3. [B - Boundaries]: 缺少空值/負數/越界防護、Early-Return（巢狀<=4層）與具名例外處理")
    if not RE_DIM_C_CONTRACT.search(text):
        missing.append("4. [C - Contracts]: 缺少輸入輸出型別簽章、回傳結構或驗收基準（若涉及數值請註明精度）")
    if len(text) < MIN_SPEC_LENGTH:
        missing.append(f"5. [Length]: 任務描述過於簡略（目前 {len(text)} 字元，需至少 {MIN_SPEC_LENGTH} 字元）")

    if missing:
        return False, _format_prescription(clean_role or "construction-subagent", missing)
    return True, ""


def _extract_role_label(payload: Dict[str, Any], fallback: str) -> str:
    """Combine Role and TypeName/subagent_type so sandbox type is never shadowed by Role."""
    role_val = str(payload.get("Role") or payload.get("role") or "").strip()
    type_val = str(
        payload.get("TypeName") or payload.get("subagent_type")
        or payload.get("agent") or payload.get("specialist") or ""
    ).strip()
    if role_val and type_val and role_val.lower() != type_val.lower():
        return f"{role_val} [{type_val}]"
    return role_val or type_val or fallback


def _collect_subagent_tasks(tool_name: str, tool_args: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Extract (prompt, role) pairs from batch arrays or single subagent tool payloads."""
    tasks_to_check: List[Tuple[str, str]] = []
    for key in ("Subagents", "subagents", "tasks", "chain"):
        items = tool_args.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            prompt = str(item.get("Prompt") or item.get("prompt") or item.get("description") or item.get("task") or "")
            tasks_to_check.append((prompt, _extract_role_label(item, tool_name or "subagent")))
        if tasks_to_check:
            return tasks_to_check

    prompt = str(
        tool_args.get("Prompt") or tool_args.get("prompt")
        or tool_args.get("description") or tool_args.get("task") or ""
    )
    if ctx := str(tool_args.get("context") or "").strip():
        prompt = f"{prompt}\n{ctx}" if prompt else ctx
    if prompt or tool_name in SUBAGENT_TOOL_NAMES:
        tasks_to_check.append((prompt, _extract_role_label(tool_args, tool_name)))
    return tasks_to_check


def _read_guard_state_file(cwd: str = ".") -> Path:
    digest = hashlib.md5(str(Path(cwd).resolve()).encode("utf-8")).hexdigest()[:12]
    return Path("/tmp") / f"netark_read_guard_{digest}.json"


def load_read_guard_state(cwd: str = ".") -> Dict[str, Any]:
    path = _read_guard_state_file(cwd)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict): return data
        except Exception:  # noqa: silent-except
            pass
    return {"lease_until": 0.0, "lease_quota": 0, "slices": {}}


def save_read_guard_state(cwd: str, state: Dict[str, Any]) -> None:
    try: _read_guard_state_file(cwd).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: silent-except
        pass


def grant_readonly_subagent_lease(cwd: str = ".", ttl_sec: int = 180, quota: int = 15) -> None:
    """Grant a temporary read-guard lease so readonly subagents can digest large files."""
    state = load_read_guard_state(cwd)
    state["lease_until"] = time.time() + ttl_sec
    state["lease_quota"] = quota
    state.setdefault("slices", {})
    save_read_guard_state(cwd, state)


def consume_readonly_subagent_lease(cwd: str = ".") -> bool:
    """Consume one read unit if a valid, unexpired readonly subagent lease exists."""
    state = load_read_guard_state(cwd)
    if time.time() < float(state.get("lease_until", 0) or 0) and int(state.get("lease_quota", 0) or 0) > 0:
        state["lease_quota"] = int(state.get("lease_quota", 0)) - 1
        save_read_guard_state(cwd, state)
        return True
    return False


def evaluate_subagent_invocation(tool_name: str, tool_args: Dict[str, Any], cwd: str = ".") -> Tuple[bool, str]:
    """Validate AGY (`invoke_subagent`), Claude (`Agent`/`Task`), or Pi subagent invocations."""
    if not isinstance(tool_args, dict):
        return True, ""
    has_readonly = False
    for prompt_text, role_name in _collect_subagent_tasks(tool_name, tool_args):
        if role_name.strip() and RE_READONLY_ROLE.search(role_name.strip()):
            has_readonly = True
        ok, prescription = validate_ribc_construction_task(prompt_text, role_name)
        if not ok:
            return False, prescription
    if has_readonly:
        grant_readonly_subagent_lease(cwd)
    return True, ""


REMEDIATION_REGISTRY: Dict[str, Tuple[str, str]] = {
    "SIDECAR-GATE": ("memory/specs/500_04_SHARD_NEXUS_HOOK_ENHANCEMENTS.md", "Delegate large-file digestion to invoke_subagent(TypeName='research') / Task(subagent_type='Explore') or nexus-sidecar."),
    "SPEC-RIBC-GATE": ("memory/specs/500_02_SHARD_RIBC_GATE.md", "Path A (Readonly): set Role/TypeName to a readonly whitelist role (research, Explore, Plan, scout, auditor, reviewer, challenger, architect). Path B (Construction): provide [R] path, [I] line cap, [B] bounds/errors, [C] contracts (>=60 chars)."),
    "SEC-CRED": ("memory/codex/100_ARCH_RULES.md", "Never read/write .env*, auth.json, or key files; use os.environ.get('KEY_NAME') or *.example templates."),
    "SEC-CONTROL-PLANE": ("memory/codex/100_ARCH_RULES.md", "Control-plane updates require explicit human confirmation or authorized governance mode."),
    "SEC-CODE-PLACEMENT": ("memory/codex/100_ARCH_RULES.md", "Place business code under projects/<project_id>/{src,scripts,tests,configs}/ or tests under scratch/test_<name>.py."),
    "SEC-PREWRITE-SECRET": ("memory/codex/100_ARCH_RULES.md", "Remove hardcoded secrets and read via os.environ.get('KEY_NAME') or process.env.KEY_NAME."),
    "SEC-SSRF": ("memory/specs/100_01_SHARD_AST_DLP_GUARD.md", "Use public https:// URLs only; localhost, RFC1918 private IPs, and metadata endpoints are blocked."),
    "SEC-XPIA-WEB": ("memory/specs/100_01_SHARD_AST_DLP_GUARD.md", "Sanitize untrusted web parameters and strip prompt-override or shell-pipe injection text."),
    "SEC-DLP-EGRESS": ("memory/codex/100_ARCH_RULES.md", "Strip plaintext tokens/keys from outbound commands or replace them with redacted placeholders."),
    "SEC-EXFIL-01": ("memory/codex/100_ARCH_RULES.md", "Remove secret environment variable expansions and command substitutions from outbound network commands."),
    "MODULARITY-GATE": ("memory/codex/100_ARCH_RULES.md", "First explain your module-splitting plan vs reason for keeping a single file to the human, and only proceed after human confirmation (Allow or adding the path to modularity_exempt_paths)."),
    "SCHEMA-403-PREFILL": ("memory/specs/500_01_SHARD_HOOK_LIFECYCLE.md", "Prepend the full YAML frontmatter skeleton, write notes to memory/wiki/, or run sync_doc_metadata.py --init."),
    "SPEC-FILENAME-FORMAT": ("memory/specs/500_01_SHARD_HOOK_LIFECYCLE.md", "Rename the node to <domain>_<2-digit-seq>_<UPPER_SLUG>.md using the suggested next sequence."),
    "MCP-PROB-01-REDIRECT": ("memory/specs/500_03_SHARD_CLOSED_MCP_PACKAGE.md", "Use MCP netark_record(intent=..., title=..., body=..., mode='preflight'|'write') instead of direct writes."),
    "SPEC-AST-SYNC-GATE": ("memory/specs/500_04_SHARD_NEXUS_HOOK_ENHANCEMENTS.md", "Cite real AST public symbols from affected_paths or tag planned/new files with stub/new intent."),
    "SPEC-BLUEPRINT-REQUIRED": ("memory/specs/500_05_SHARD_LIFECYCLE_AND_STEP_GATE.md", "Create a Master Blueprint (netark_record intent='blueprint') first, then bind this shard spec via topology.parent_blueprint."),
    "STUB-FIRST-GATE": ("memory/specs/500_05_SHARD_LIFECYCLE_AND_STEP_GATE.md", "Create/update a Shard Spec (status: stub_ready) binding this module in stub_paths/affected_paths before writing module code."),
    "CODE-ARROW-NESTING": ("memory/specs/100_01_SHARD_AST_DLP_GUARD.md", "Flatten control-flow nesting to <=4 layers using Early-Return guard clauses or helper functions."),
    "CODE-SILENT-EXCEPT": ("memory/specs/100_01_SHARD_AST_DLP_GUARD.md", "Handle or log exceptions explicitly, or annotate intentional fallbacks with '# noqa: silent-except'."),
    "CODE-NESTED-LOOPS": ("memory/specs/100_01_SHARD_AST_DLP_GUARD.md", "Flatten loop nesting to <=2 layers via helper extraction or dict/set lookups."),
    "CODE-GOD-FUNCTION": ("memory/specs/100_01_SHARD_AST_DLP_GUARD.md", "Refactor functions exceeding 70 effective lines into smaller single-purpose helpers."),
}
_CMD_REM = ("memory/specs/100_01_SHARD_AST_DLP_GUARD.md", "Avoid destructive rm/disk-format/chmod-root or remote curl|sh execution patterns.")
_DEF_REM = ("memory/codex/100_ARCH_RULES.md", "Review the policy reason above and choose a compliant workspace-safe alternative.")


def format_guard_remediation(code: str, reason: str) -> str:
    """Append standardized [RuleDoc] and [SuggestedAlternative] pointers unless already present."""
    base = (reason or "Blocked by policy.").rstrip()
    if "[RuleDoc]" in base:
        return base
    doc, alt = REMEDIATION_REGISTRY.get(code) or (_CMD_REM if code.startswith("SEC-CMD-") else _DEF_REM)
    return f"{base}\n  [RuleDoc]: {doc}\n  [SuggestedAlternative]: {alt}"


def _format_prescription(role_label: str, missing_items: List[str]) -> str:
    """Format actionable two-path (Readonly vs. Construction) remediation guidance."""
    joined_missing = "\n".join(f"  - {item}" for item in missing_items)
    return (
        f"🏗️ [NetArk Construction Gate | SPEC-RIBC-GATE] "
        f"攔截到子代理派工（角色: {role_label}）規格不完整！\n"
        f"未通過審查項目：\n{joined_missing}\n\n"
        f"RemediationPointer: 請先判斷此子代理任務性質，擇一修正後重試：\n"
        f"  ▸ 路徑 A【純唯讀調查 / 搜尋 / 審閱】（嚴禁硬塞 R-I-B-C 關鍵字湊數）\n"
        f"    直接將子代理角色（Role / subagent_type / TypeName）改為系統認可的唯讀白名單：\n"
        f"    `research`、`Explore`、`Plan`、`scout`、`auditor`、`reviewer`、`challenger`、`architect`、`readonly`，即可免審放行。\n"
        f"  ▸ 路徑 B【修改 / 新增程式碼（Construction）】\n"
        f"    請補齊以下四維規格（總長 >= 60 字元）：\n"
        f"    [R - Role & Path] 目標檔案路徑（如 path/to/module.py）與單一職責\n"
        f"    [I - Invariants] 業務不變量與單檔行數上限（如 <= 350 行）\n"
        f"    [B - Boundaries] 空值/越界防護、巢狀 <= 4 層（Early-Return）與具名例外處理\n"
        f"    [C - Contracts] 輸入輸出型別簽章、回傳結構或驗收基準（若涉及數值請註明精度）"
    )


def _run_self_tests() -> None:
    """Run deterministic self-test suite for RIBC 4D validation and AGY/Claude payload parsing."""
    assert validate_ribc_construction_task("檢查目錄", "scout")[0] is True
    assert validate_ribc_construction_task("檢索規格", "research")[0] is True
    assert validate_ribc_construction_task("稽核 Oracle", "auditor")[0] is True
    assert validate_ribc_construction_task("對抗審查", "challenger")[0] is True
    assert validate_ribc_construction_task("修正 foo.py 行號 L12 的 typo", "worker")[0] is True

    assert validate_ribc_construction_task("新建模組 wallet.py 並避免 typo", "worker")[0] is False
    ok_missing, msg_missing = validate_ribc_construction_task("實作這個功能，字數已經夠長了，但我完全沒有加上防呆，也沒有任何資料格式相關的字眼，純粹來亂的", "code")
    assert ok_missing is False and "SPEC-RIBC-GATE" in msg_missing
    full_spec = "[R] 目標模組 projects/demo/src/wallet.py 負責餘額計算；[I] 單檔 <=350行 且餘額不得為負；[B] 遇到空值或負數使用 Early-Return 並拋出 ValueError 防護；[C] 採用 Decimal 精度與強型別 dict 回傳介面契約。"
    assert validate_ribc_construction_task(full_spec, "worker")[0] is True

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        assert evaluate_subagent_invocation("invoke_subagent", {"Subagents": [{"Prompt": "快速搜尋", "Role": "scout"}, {"Prompt": full_spec, "Role": "Worker"}]}, cwd=tmp)[0] is True
        assert consume_readonly_subagent_lease(tmp) is True
        assert evaluate_subagent_invocation("invoke_subagent", {"Subagents": [{"Prompt": "檢查", "Role": "research"}, {"Prompt": "隨便寫個程式", "Role": "Backend Builder"}]}, cwd=tmp)[0] is False
        assert evaluate_subagent_invocation("invoke_subagent", {"TypeName": "research", "Role": "Validator & Dashboard Code Inspector", "Prompt": "唯讀調查"}, cwd=tmp)[0] is True
        assert evaluate_subagent_invocation("invoke_subagent", {"TypeName": "self", "Role": "Module Implementer", "Prompt": "幫我寫好這個模組"})[0] is False
        grant_readonly_subagent_lease(tmp, ttl_sec=60, quota=1)
        assert consume_readonly_subagent_lease(tmp) is True and consume_readonly_subagent_lease(tmp) is False
    assert "[RuleDoc]:" in format_guard_remediation("SIDECAR-GATE", "blocked") and "[SuggestedAlternative]:" in format_guard_remediation("SEC-CMD-01", "rm")
    print(json.dumps({"status": "ok", "module": "schemas/ribc_gate.py", "tests_passed": 12}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetArk SPEC-RIBC-GATE Validator")
    parser.add_argument("--self-test", action="store_true", help="Run built-in RIBC 4D validation tests")
    if parser.parse_args().self_test:
        _run_self_tests()
        sys.exit(0)
