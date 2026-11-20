#!/usr/bin/env python3
"""NetArk Unified MCP Server, Closed Hook Bridge & Zero-.py Initializer (netark_mcp_server.py)."""

from __future__ import annotations

import argparse, json, os, re, shutil, sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from schemas import schema_validator as sv  # noqa: E402
from schemas.hook_lifecycle import _run_pre_invocation_mode, _run_session_start_mode, queue_agy_post_alert  # noqa: E402
from schemas.mcp_tools_core import (  # noqa: E402
    MCP_TOOLS_SCHEMA, compile_and_write_indices, get_embedded_asset_text, handle_mcp_tool_call, run_closed_mcp_init,
)
from schemas.topology_graph import check_code_to_spec_drift, query_codebook_entry  # noqa: E402
from schemas.yaml_lite import _parse_simple_yaml  # noqa: E402, F401
from scripts.netark_guard_daemon import (  # noqa: E402
    _parse_stdin_json, _resolve_cwd_and_tool, _run_hook_mode, _run_post_hook_mode, _run_stop_mode,
)

MCP_SERVER_INSTRUCTIONS = (
    "NetArk is a Hook-first governance & memory harness: security, AST, RIBC, and handover checks run automatically via `netark-mcp hook`. "
    "Use these 3 MCP tools for memory & verification: "
    "(1) `netark_query(query)` BEFORE reading/editing to resolve @D/@C/@G codes, specs, topics, or 1-hop AST impact; "
    "(2) `netark_record(intent, title, body, mode='preflight'|'write')` for ALL `memory/**/*.md` writes (never raw file writes); "
    "(3) `netark_guard(action)` for full-repo schema+DAG validation (`oracle`), handover/policy status (`handover`|`status`), "
    "or the universal Hook CLI contract (`setup`) to wire hooks on any host (AGY, Claude, Pi .ts, Cursor, etc.)."
)


def _write_rpc(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle_rpc_request(msg: Dict[str, Any], cwd: str) -> Optional[Dict[str, Any]]:
    method = str(msg.get("method") or "")
    req_id = msg.get("id")
    if method == "notifications/initialized" or (req_id is None and method.startswith("notifications/")):
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "netark-mcp", "version": "3.2.0"},
                "instructions": MCP_SERVER_INSTRUCTIONS,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS_SCHEMA}}
    if method == "tools/call":
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        tname = str(params.get("name") or "")
        targs = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        try:
            res = handle_mcp_tool_call(tname, targs, cwd)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}], "isError": False}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)}], "isError": True}}
    if req_id is not None:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def _run_serve(cwd: str) -> int:
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue
        try:
            msg = json.loads(stripped)
        except Exception:
            _write_rpc({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        if not isinstance(msg, dict):
            _write_rpc({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}})
            continue
        if (resp := _handle_rpc_request(msg, cwd)) is not None:
            _write_rpc(resp)
    return 0


def _run_closed_post_hook(host: str, default_cwd: str) -> int:
    payload = _parse_stdin_json()
    cwd, _, tool_args = _resolve_cwd_and_tool(payload, default_cwd)
    raw_path = str(tool_args.get("path") or tool_args.get("Path") or tool_args.get("file_path") or tool_args.get("TargetFile") or "")
    root = Path(cwd).resolve()
    target = ((root / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()) if raw_path else None
    rel = ""
    if target and target.exists():
        try:
            rel = str(target.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = ""
    drift_msg: Optional[str] = None
    if rel.startswith("memory/") and rel.endswith(".md") and not rel.endswith("CONTEXT_MAP.md"):
        hdr_sch = json.loads(get_embedded_asset_text("schemas/artifact_header.schema.json"))
        nod_sch = json.loads(get_embedded_asset_text("schemas/context_node.schema.json"))
        _, errs = sv.validate_document(target, root, hdr_sch, nod_sch, run_oracle=False)
        try:
            compile_and_write_indices(root)
        except Exception as exc:
            print(f"⚠️ PostToolUse index compile warning: {exc}", file=sys.stderr)
        if errs:
            drift_msg = f"⚠️ [PostToolUse Schema Failure | {rel}]\n" + "\n".join(errs)[:1200]
    elif rel and not rel.startswith("memory/"):
        drift_msg = check_code_to_spec_drift(root, rel)
    if host == "agy":
        if drift_msg:
            queue_agy_post_alert(cwd, drift_msg)
        print("{}")
    elif drift_msg:
        print(drift_msg, file=sys.stderr)
    return 0


def _run_closed_stop_hook(host: str, default_cwd: str) -> int:
    payload = _parse_stdin_json()
    cwd, _, _ = _resolve_cwd_and_tool(payload, default_cwd)
    root = Path(cwd).resolve()
    if (root / "memory").is_dir():
        try:
            compile_and_write_indices(root)
        except Exception as exc:
            print(f"⚠️ Stop hook index warning: {exc}", file=sys.stderr)
    if host == "agy":
        print(json.dumps({"decision": "stop"}, ensure_ascii=False))
    return 0


def _run_hook_subcommand(argv: List[str]) -> int:
    os.environ["NETARK_MCP_HOOK_MODE"] = "1"
    p = argparse.ArgumentParser(prog="netark-mcp hook", description="NetArk Closed MCP Hook Bridge")
    p.add_argument("--hook-mode", choices=["pi", "agy", "claude"])
    p.add_argument("--post-hook-mode", choices=["pi", "agy", "claude"])
    p.add_argument("--session-start-mode", choices=["pi", "agy", "claude"])
    p.add_argument("--pre-invocation-mode", choices=["pi", "agy", "claude"])
    p.add_argument("--stop-mode", choices=["pi", "agy", "claude"])
    p.add_argument("--cwd", default=".")
    p.add_argument("--query", default=None)
    args = p.parse_args(argv)
    if args.query is not None:
        print(json.dumps(query_codebook_entry(Path(args.cwd).resolve(), args.query), ensure_ascii=False, indent=2))
        return 0
    if args.hook_mode:
        return _run_hook_mode(args.hook_mode, args.cwd)
    if args.session_start_mode:
        return _run_session_start_mode(args.session_start_mode, args.cwd)
    if args.pre_invocation_mode:
        return _run_pre_invocation_mode(args.pre_invocation_mode, args.cwd)
    has_disk_scripts = (Path(args.cwd).resolve() / "scripts" / "auto_update_map.py").exists()
    if args.post_hook_mode:
        return _run_post_hook_mode(args.post_hook_mode, args.cwd) if has_disk_scripts else _run_closed_post_hook(args.post_hook_mode, args.cwd)
    if args.stop_mode:
        return _run_stop_mode(args.stop_mode, args.cwd) if has_disk_scripts else _run_closed_stop_hook(args.stop_mode, args.cwd)
    p.print_help(sys.stderr)
    return 2


def _run_init_subcommand(argv: List[str]) -> int:
    p = argparse.ArgumentParser(prog="netark-mcp init", description="NetArk Closed Zero-.py Project Initializer")
    p.add_argument("--target", choices=["memory", "agy", "claude", "all"], default="memory")
    p.add_argument("--lang", choices=["zh-TW", "en"], default="zh-TW")
    p.add_argument("--cwd", default=".")
    p.add_argument("--bin-path", default="")
    p.add_argument("--write-rules", action="store_true", help="Also write AGENTS.md/CLAUDE.md to repo root (default: off)")
    p.add_argument("--update", action="store_true")
    args = p.parse_args(argv)
    bin_cmd = (args.bin_path or "").strip()
    if not bin_cmd:
        argv0_raw = sys.argv[0] if sys.argv else ""
        argv0_path = Path(argv0_raw) if argv0_raw else Path("")
        cand = shutil.which(argv0_raw) or (str(argv0_path.absolute()) if argv0_raw and argv0_path.is_file() else "")
        bin_cmd = cand if (cand and not cand.lower().endswith(".py")) else (shutil.which("netark-mcp") or "netark-mcp")
    res = run_closed_mcp_init(cwd=args.cwd, target=args.target, lang=args.lang, bin_cmd=bin_cmd, update_rules=args.update, write_rules=(args.write_rules or args.update))
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def _prune_json_file(path: Path, root: Path, pruner: Any, cleaned: List[str]) -> None:
    if not path.is_file(): return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(data, dict): return
    pruner(data)
    rel = str(path.relative_to(root))
    if not data:
        path.unlink()
        cleaned.append(f"{rel} (deleted)")
    else:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        cleaned.append(f"{rel} (pruned)")


def _prune_claude_hooks(data: Dict[str, Any]) -> None:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict): return
    for ev in ("SessionStart", "PreToolUse", "PostToolUse", "Stop"):
        if not isinstance(hooks.get(ev), list): continue
        kept = [item for item in hooks[ev] if "netark-mcp hook" not in json.dumps(item) and "netark_guard_daemon.py" not in json.dumps(item)]
        if kept: hooks[ev] = kept
        else: hooks.pop(ev, None)
    if not hooks: data.pop("hooks", None)


def _prune_mcp_netark(data: Dict[str, Any]) -> None:
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        servers.pop("netark", None)
        if not servers: data.pop("mcpServers", None)


def _run_closed_mcp_uninstall(cwd: str, target: str = "all", purge_memory: bool = False) -> Dict[str, Any]:
    import shutil
    root, targets, cleaned = Path(cwd).resolve(), (["agy", "claude"] if target == "all" else [target]), []
    if "agy" in targets:
        _prune_json_file(root / ".agents" / "hooks.json", root, lambda d: [d.pop(k, None) for k in ("netark-enterprise-guard", "netark-v3-session-init", "netark-v3-guard")] and None, cleaned)
        plg = root / ".agents" / "plugins" / "netark"
        if plg.exists():
            shutil.rmtree(plg, ignore_errors=True)
            cleaned.append(".agents/plugins/netark (deleted)")
    if "memory" in targets or "claude" in targets:
        _prune_json_file(root / ".mcp.json", root, _prune_mcp_netark, cleaned)
    if "claude" in targets:
        _prune_json_file(root / ".claude" / "settings.json", root, _prune_claude_hooks, cleaned)
    if purge_memory and (root / "memory").exists():
        shutil.rmtree(root / "memory", ignore_errors=True)
        cleaned.append("memory/ (purged)")
    return {"status": "ok", "workspace": str(root), "targets": targets, "purge_memory": purge_memory, "cleaned": cleaned}


def _run_uninstall_subcommand(argv: List[str]) -> int:
    p = argparse.ArgumentParser(prog="netark-mcp uninstall", description="NetArk Closed MCP Wiring Uninstaller")
    p.add_argument("--target", choices=["memory", "agy", "claude", "all"], default="all")
    p.add_argument("--cwd", default=".")
    p.add_argument("--purge-memory", action="store_true", help="Also delete memory/ directory (default preserves memory/)")
    args = p.parse_args(argv)
    print(json.dumps(_run_closed_mcp_uninstall(cwd=args.cwd, target=args.target, purge_memory=args.purge_memory), indent=2, ensure_ascii=False))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Unified entrypoint for serve, hook, init, and uninstall subcommands."""
    for _stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw or raw[0] in {"-h", "--help"}:
        print("Usage: netark-mcp {serve|hook|init|uninstall} [options]", file=sys.stderr)
        return 0 if raw else 2
    sub, rest = raw[0], raw[1:]
    if sub == "serve":
        sp = argparse.ArgumentParser(prog="netark-mcp serve")
        sp.add_argument("--cwd", default=".")
        return _run_serve(sp.parse_args(rest).cwd)
    if sub == "hook":
        return _run_hook_subcommand(rest)
    if sub == "init":
        return _run_init_subcommand(rest)
    if sub == "uninstall":
        return _run_uninstall_subcommand(rest)
    print(f"Unknown subcommand: {sub}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
