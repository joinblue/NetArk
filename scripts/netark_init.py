#!/usr/bin/env python3
"""
NetArk (N.E.T.A.R.K.) Multi-Host CLI Installer & Bilingual Memory Bootstrapper
==============================================================================
Single-trunk adapter installer supporting:
  python3 scripts/netark_init.py --target [pi|agy|claude|all] --lang [zh-TW|en] [--cwd PATH] [--brain-dir .netark]

Responsibilities:
  1. Generate/merge `.netark/enterprise-policy.json` zero-code custom DLP policy template.
  2. Configure host-specific PreToolUse / PostToolUse / SessionStart / Stop hooks:
     - `pi`    : Provision `.netark/` brain configs, extensions, subagents, skills & prompts
     - `agy`   : Create `.agents/hooks.json` (`../scripts/netark_guard_daemon.py --cwd ..`), root `AGENTS.md` (`invoke_subagent`), `.agents/skills/`, `.agents/workflows/`
     - `claude`: Create `.claude/settings.json`, root `CLAUDE.md`, `.claude/commands/`
  3. Bootstrap bilingual (`zh-TW` or `en`) 5-node clean memory core (`000_SOUL.md`, `100_ARCH_RULES.md`,
     `200_DECISIONS.md`, `LEDGER.md`, `HANDOVER.md`) from `templates/memory/<lang>/` and compile `@D/@M/@C/@G` map.
"""

from __future__ import annotations

import argparse
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

NETARK_SOURCE_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ENTERPRISE_POLICY: Dict[str, Any] = {
    "schema_version": "1.0",
    "tier1_onnx_scope": "untrusted_and_network",
    "prewrite_secret_lint": True,
    "session_vault_disabled": True,
    "custom_redact_literals": [],
    "custom_secret_patterns": [],
    "protected_paths": [".netark/", ".agents/", ".claude/", ".github/workflows/", "schemas/"],
}

CORE_MEMORY_MAP = (
    ("000_SOUL.md", "memory/codex/000_SOUL.md"),
    ("100_ARCH_RULES.md", "memory/codex/100_ARCH_RULES.md"),
    ("200_DECISIONS.md", "memory/codex/200_DECISIONS.md"),
    ("LEDGER.md", "memory/LEDGER.md"),
    ("HANDOVER.md", "memory/episodic/HANDOVER.md"),
)


def ensure_enterprise_policy(root: Path, brain_dir: str = ".netark") -> Path:
    policy_path = root / brain_dir / "enterprise-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if policy_path.exists():
        try:
            existing = json.loads(policy_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    merged = {**DEFAULT_ENTERPRISE_POLICY, **existing}
    policy_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return policy_path


def _sync_workflow_commands(root: Path, dest_dir: Path, brain_dir: str = ".netark") -> None:
    prompts_dir = (root / brain_dir / "prompts") if (root / brain_dir / "prompts").exists() else (NETARK_SOURCE_ROOT / ".netark" / "prompts")
    if not prompts_dir.exists():
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    for cmd_file in ("handover.md", "dream.md", "team.md"):
        src = prompts_dir / cmd_file
        dst = dest_dir / cmd_file
        if src.exists() and not dst.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _sync_skills(dest_skills_dir: Path) -> None:
    src_skills = NETARK_SOURCE_ROOT / "templates" / "skills"
    if not src_skills.exists():
        src_skills = NETARK_SOURCE_ROOT / ".netark" / "skills"
    if not src_skills.exists():
        return
    for skill_md in src_skills.rglob("SKILL.md"):
        rel = skill_md.relative_to(src_skills)
        dst = dest_skills_dir / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill_md, dst)


def install_agy_adapter(root: Path, brain_dir: str = ".netark", update: bool = False) -> Path:
    hooks_path = root / ".agents" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if hooks_path.exists():
        try:
            existing = json.loads(hooks_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing["netark-enterprise-guard"] = {
        "enabled": True,
        "SessionStart": [
            {"type": "command", "command": "python3 ../scripts/netark_guard_daemon.py --session-start-mode agy --cwd ..", "timeout": 5}
        ],
        "PreToolUse": [
            {
                "matcher": "read_file|view_file|write_file|edit_file|write_to_file|replace_file_content|run_command|bash",
                "hooks": [{"type": "command", "command": "python3 ../scripts/netark_guard_daemon.py --hook-mode agy --cwd ..", "timeout": 5}],
            }
        ],
        "PostToolUse": [
            {
                "matcher": "write_file|edit_file|write_to_file|replace_file_content",
                "hooks": [{"type": "command", "command": "python3 ../scripts/netark_guard_daemon.py --post-hook-mode agy --cwd ..", "timeout": 10}],
            }
        ],
        "Stop": [
            {"type": "command", "command": "python3 ../scripts/netark_guard_daemon.py --stop-mode agy --cwd ..", "timeout": 10}
        ],
    }
    hooks_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    root_agents = root / "AGENTS.md"
    tmpl_agy_agents = NETARK_SOURCE_ROOT / "templates" / "hosts" / "agy" / "AGENTS.md.tpl"
    if not tmpl_agy_agents.exists():
        tmpl_agy_agents = NETARK_SOURCE_ROOT / "templates" / "hosts" / "agy" / "AGENTS.md"
    if (update or not root_agents.exists()) and tmpl_agy_agents.exists():
        shutil.copy2(tmpl_agy_agents, root_agents)
    _sync_workflow_commands(root, root / ".agents" / "workflows", brain_dir=brain_dir)
    _sync_skills(root / ".agents" / "skills")
    return hooks_path


def install_claude_adapter(root: Path, brain_dir: str = ".netark", update: bool = False) -> Path:
    settings_path = root / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    hooks = existing.setdefault("hooks", {})
    hooks["SessionStart"] = [
        {
            "matcher": "",
            "hooks": [{"type": "command", "command": "python3 scripts/netark_guard_daemon.py --session-start-mode claude --cwd ."}],
        }
    ]
    hooks["PreToolUse"] = [
        {
            "matcher": "Bash|Write|Edit|MultiEdit|Read|WebFetch",
            "hooks": [{"type": "command", "command": "python3 scripts/netark_guard_daemon.py --hook-mode claude --cwd ."}],
        }
    ]
    hooks["PostToolUse"] = [
        {
            "matcher": "Write|Edit|MultiEdit",
            "hooks": [{"type": "command", "command": "python3 scripts/netark_guard_daemon.py --post-hook-mode claude --cwd ."}],
        }
    ]
    hooks["Stop"] = [
        {
            "matcher": "",
            "hooks": [{"type": "command", "command": "python3 scripts/netark_guard_daemon.py --stop-mode claude --cwd ."}],
        }
    ]
    settings_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    claude_md = root / "CLAUDE.md"
    tmpl_claude = NETARK_SOURCE_ROOT / "templates" / "hosts" / "claude" / "CLAUDE.md.tpl"
    if not tmpl_claude.exists():
        tmpl_claude = NETARK_SOURCE_ROOT / "templates" / "hosts" / "claude" / "CLAUDE.md"
    if (update or not claude_md.exists()) and tmpl_claude.exists():
        shutil.copy2(tmpl_claude, claude_md)
    _sync_workflow_commands(root, root / ".claude" / "commands", brain_dir=brain_dir)
    return settings_path


def install_pi_adapter(root: Path, brain_dir: str = ".netark", update: bool = False) -> Path:
    bdir = root / brain_dir
    bdir.mkdir(parents=True, exist_ok=True)
    tmpl_pi_dir = NETARK_SOURCE_ROOT / "templates" / "hosts" / "pi"
    src_brain = NETARK_SOURCE_ROOT / ".netark"
    for item in ("settings.json", "role-models.json", "auth.example.json", "AGENTS.md", "models.json", "custom-models.json"):
        tpl_s = tmpl_pi_dir / f"{item}.tpl"
        s = tpl_s if tpl_s.exists() else (src_brain / item)
        d = bdir / item
        if s.exists() and (not d.exists() or (update and item in {"AGENTS.md", "models.json", "auth.example.json"})):
            shutil.copy2(s, d)
    for subdir in ("agents", "prompts", "skills", "extensions"):
        sdir, ddir = src_brain / subdir, bdir / subdir
        if not sdir.exists():
            continue
        for sf in sdir.rglob("*"):
            if sf.is_file() and (update or not (df := ddir / sf.relative_to(sdir)).exists()):
                df = ddir / sf.relative_to(sdir)
                df.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sf, df)
    pi_settings = bdir / "settings.json"
    if not pi_settings.exists():
        default_pi = {
            "lastChangelogVersion": "1.0.0",
            "defaultProvider": "pi-router",
            "defaultModel": "auto",
            "defaultThinkingLevel": "low",
            "defaultTools": ["+grep", "+find", "+ls"],
        }
        pi_settings.write_text(json.dumps(default_pi, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return pi_settings


def _sync_python_core_if_external(root: Path, update: bool = False) -> None:
    if root.resolve() == NETARK_SOURCE_ROOT.resolve():
        return
    for rel_file in (
        ".gitignore",
        "schemas/artifact_header.schema.json",
        "schemas/context_node.schema.json",
        "schemas/code_hygiene_ast.py",
        "schemas/codebook_compiler.py",
        "schemas/topology_graph.py",
        "schemas/doc_initializer.py",
        "schemas/schema_validator.py",
        "schemas/netark_guard_core.py",
        "scripts/netark_guard_daemon.py",
        "scripts/netark_init.py",
        "scripts/auto_update_map.py",
        "scripts/sync_doc_metadata.py",
        "memory/index/TAXONOMY.json",
        "dashboard/README.md",
        "dashboard/backend/graph_scanner.py",
        "dashboard/backend/server.py",
        "dashboard/frontend/index.html",
        "dashboard/frontend/styles.css",
        "dashboard/frontend/graph_canvas.js",
        "dashboard/frontend/app.js",
        "dashboard/tests/test_dashboard_shards.py",
    ):
        src = NETARK_SOURCE_ROOT / rel_file
        dst = root / rel_file
        if src.exists() and (not dst.exists() or (update and rel_file != ".gitignore")):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def bootstrap_bilingual_memory(root: Path, lang: str) -> List[str]:
    today = datetime.date.today().isoformat()
    created: List[str] = []
    for std_dir in ("memory/wiki", "memory/specs", "memory/audits", "scratch"):
        (root / std_dir).mkdir(parents=True, exist_ok=True)
    tmpl_dir = NETARK_SOURCE_ROOT / "templates" / "memory" / lang
    for tmpl_name, dest_rel in CORE_MEMORY_MAP:
        dst = root / dest_rel
        src = tmpl_dir / tmpl_name
        if not dst.exists() and src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            raw = src.read_text(encoding="utf-8")
            raw = raw.replace("2026-11-08", today)
            dst.write_text(raw, encoding="utf-8")
            created.append(dest_rel)
    if (root / "scripts" / "auto_update_map.py").exists():
        subprocess.run([sys.executable, str(root / "scripts" / "auto_update_map.py")], cwd=str(root), capture_output=True, check=False)
    return created


def initialize_workspace(cwd: str = ".", target: str = "pi", lang: str = "zh-TW", brain_dir: str = ".netark", update: bool = False) -> Dict[str, Any]:
    root = Path(cwd).resolve()
    _sync_python_core_if_external(root, update=update)
    policy_path = ensure_enterprise_policy(root, brain_dir=brain_dir)
    configured_hosts: List[str] = []
    adapter_files: List[str] = []
    targets = ["pi", "agy", "claude"] if target == "all" else [target]
    for t in targets:
        if t == "pi":
            p = install_pi_adapter(root, brain_dir=brain_dir, update=update)
        elif t == "agy":
            p = install_agy_adapter(root, brain_dir=brain_dir, update=update)
        elif t == "claude":
            p = install_claude_adapter(root, brain_dir=brain_dir, update=update)
        else:
            continue
        configured_hosts.append(t)
        adapter_files.append(str(p.relative_to(root)))
    bootstrapped_nodes = bootstrap_bilingual_memory(root, lang)
    return {
        "status": "ok",
        "workspace": str(root),
        "brain_dir": brain_dir,
        "targets": configured_hosts,
        "lang": lang,
        "updated": update,
        "enterprise_policy": str(policy_path.relative_to(root)),
        "adapter_files": adapter_files,
        "bootstrapped_memory_nodes": bootstrapped_nodes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetArk Multi-Host CLI Installer & Bilingual Memory Bootstrapper")
    parser.add_argument("--target", choices=["pi", "agy", "claude", "all"], default="pi", help="Target Agent CLI host")
    parser.add_argument("--lang", choices=["zh-TW", "en"], default="zh-TW", help="Language for fresh memory templates")
    parser.add_argument("--cwd", default=".", help="Target workspace root directory")
    parser.add_argument("--brain-dir", default=".netark", help="Portable brain directory name (default: .netark)")
    parser.add_argument("--update", action="store_true", help="Update engine scripts, schemas, extensions & host rules in-place while preserving memory & auth")
    parser.add_argument("--self-test", action="store_true", help="Run built-in multi-host & bilingual installer verification")
    args = parser.parse_args()

    if args.self_test:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_en, tempfile.TemporaryDirectory() as tmp_zh:
            res_en = initialize_workspace(cwd=tmp_en, target="all", lang="en", brain_dir=args.brain_dir)
            assert set(res_en["targets"]) == {"pi", "agy", "claude"}
            assert (Path(tmp_en) / args.brain_dir / "enterprise-policy.json").exists()
            assert (Path(tmp_en) / ".agents" / "hooks.json").exists()
            assert (Path(tmp_en) / "AGENTS.md").exists() and "invoke_subagent" in (Path(tmp_en) / "AGENTS.md").read_text(encoding="utf-8")
            assert (Path(tmp_en) / ".claude" / "settings.json").exists()
            assert len(res_en["bootstrapped_memory_nodes"]) == 5
            assert (Path(tmp_en) / "memory" / "index" / "CONTEXT_INDEX.json").exists()

            res_zh = initialize_workspace(cwd=tmp_zh, target="agy", lang="zh-TW", brain_dir=args.brain_dir)
            assert "核心憲法" in (Path(tmp_zh) / "memory" / "codex" / "000_SOUL.md").read_text(encoding="utf-8")
            assert len(res_zh["bootstrapped_memory_nodes"]) == 5
        print(json.dumps({"status": "ok", "self_test": "passed", "targets_verified": ["pi", "agy", "claude"], "langs_verified": ["zh-TW", "en"]}))
        sys.exit(0)

    print(json.dumps(initialize_workspace(cwd=args.cwd, target=args.target, lang=args.lang, brain_dir=args.brain_dir, update=args.update), indent=2, ensure_ascii=False))
