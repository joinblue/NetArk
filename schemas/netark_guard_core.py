#!/usr/bin/env python3
"""NetArk Guard Core — Tier 0 Structural AST/Lexer Engine, Deobfuscation, Pre-Write Secret Lint & Outbound DLP.
Governing Rules: 100.ARCH-RULES.v1 (SEC-CRED, SEC-PREWRITE-SECRET, SEC-CONTROL-PLANE, G-01..G-05) & 100.SHARD-AST-DLP-GUARD.v1."""

from __future__ import annotations

import argparse, ast, base64, json, os, re, shlex, sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from schemas.netark_dlp_core import (  # noqa: E402,F401
    ASSIGN_RHS_RE, BASE64_CANDIDATE_RE, HEX_CANDIDATE_RE, INVISIBLE_UNICODE_RE, PATH_EXT_RE, SECRET_PATTERNS,
    _decode_encoded_blobs, _is_benign_entropy_token, _is_printable_text, _scan_layer_secrets,
    calculate_shannon_entropy, check_enterprise_feature, check_prewrite_secret_lint, load_enterprise_policy,
    normalize_and_deobfuscate, redact_sensitive_payload, scan_plaintext_secrets, scan_secrets_and_entropy,
)
from schemas.workspace_placement_guard import check_code_placement, check_direct_read_guard, check_web_and_ssrf_guard  # noqa: E402

PROTECTED_CONTROL_PATHS = (".netark/", ".agents/", ".claude/", ".github/workflows/", "schemas/", "scripts/")
WRITE_TOOLS = {"write", "edit", "write_file", "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content", "multiedit", "replace"}
SECRET_FILENAME_RE = re.compile(r"^(?:\.env(?!(?:\.example|\.sample|\.template)$)(?:\.[A-Za-z0-9._-]+)?|auth\.json|models-store\.json|.*vault.*\.json|id_rsa|id_ed25519|id_ecdsa|application_default_credentials\.json|\.npmrc|\.pypirc|\.netrc|\.git-credentials|.*\.(?:pem|key|p12|pfx))$", re.I)
ENV_SECRET_REF_RE = re.compile(r"\$\{?[A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASS|CRED|ENV)[A-Za-z0-9_]*\}?", re.I)
NETWORK_CMDS = {"curl", "wget", "nc", "netcat", "socat", "nslookup", "dig", "scp", "rsync", "ssh"}
SHELL_INTERPRETERS = {"sh", "bash", "zsh", "dash", "ksh"}
GREP_VALUE_FLAGS = {"-e", "--regexp", "-f", "--file", "-m", "--max-count", "-A", "-B", "-C", "--include", "--exclude", "--exclude-dir"}


def _is_secret_path(candidate: str) -> bool:
    for part in (candidate.split("=", 1) if "=" in candidate else [candidate]):
        cleaned = part.strip().lstrip("@").strip("\"'")
        if cleaned and not cleaned.startswith("-") and SECRET_FILENAME_RE.match(Path(cleaned.replace("\\", "/")).name):
            return True
    return False


def _extract_subshells_and_segments(src: str, depth: int = 0) -> List[str]:
    if depth > 6 or not src.strip(): return []
    subshells, segments, cur, i, n, mode = [], [], [], 0, len(src), "none"
    while i < n:
        ch = src[i]
        if mode == "single":
            cur.append(ch); mode = "none" if ch == "'" else mode; i += 1
        elif ch == "\\" and i + 1 < n:
            cur.append(src[i : i + 2]); i += 2
        elif ch == "$" and i + 1 < n and src[i + 1] == "(":
            p_depth, j, sub_m = 1, i + 2, "none"
            while j < n and p_depth > 0:
                c = src[j]
                if sub_m == "single" and c == "'": sub_m = "none"
                elif sub_m != "single" and c == "\\" and j + 1 < n: j += 1
                elif sub_m == "double" and c == '"': sub_m = "none"
                elif sub_m == "double" and c == "(" and src[j - 1] == "$": p_depth += 1
                elif sub_m == "none" and c in ("'", '"'): sub_m = "single" if c == "'" else "double"
                elif sub_m == "none" and c in ("(", ")"): p_depth += 1 if c == "(" else -1
                j += 1
            subshells.extend(_extract_subshells_and_segments(src[i + 2 : max(i + 2, j - 1)], depth + 1))
            cur.append("__SUBSHELL__"); i = j
        elif ch == "`":
            j = i + 1
            while j < n and src[j] != "`": j += 2 if src[j] == "\\" else 1
            subshells.extend(_extract_subshells_and_segments(src[i + 1 : j], depth + 1))
            cur.append("__SUBSHELL__"); i = j + 1
        elif mode == "double":
            cur.append(ch); mode = "none" if ch == '"' else mode; i += 1
        elif ch in ("'", '"'):
            mode = "single" if ch == "'" else "double"; cur.append(ch); i += 1
        elif ch == "#" and (i == 0 or src[i - 1].isspace()):
            while i < n and src[i] != "\n": i += 1
        elif ch in (";", "\n") or (ch in ("|", "&") and i + 1 < n and src[i + 1] == ch) or ch == "|":
            if "".join(cur).strip(): segments.append("".join(cur).strip())
            cur = []; i += 2 if (i + 1 < n and src[i + 1] == ch and ch in ("|", "&")) else 1
        else:
            cur.append(ch); i += 1
    if "".join(cur).strip(): segments.append("".join(cur).strip())
    return segments + subshells


def _inspect_inline_python_ast(code: str, cwd: str = ".", depth: int = 0) -> Optional[Dict[str, Any]]:
    try: tree = ast.parse(code)
    except SyntaxError: return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _is_secret_path(node.value):
            return {"allowed": False, "code": "SEC-CRED", "reason": f"Inline Python AST accesses protected secret file '{node.value}'."}
        if not isinstance(node, ast.Call): continue
        fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None) or ""
        for arg in node.args:
            if fn in {"system", "popen", "run", "call", "check_output", "Popen"}:
                cmd_val = arg.value if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)) else (
                    " ".join(shlex.quote(e.value) for e in arg.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
                    if isinstance(arg, (ast.List, ast.Tuple)) else ""
                )
                if cmd_val and (sub := _analyze_shell_ast(cmd_val, cwd, depth + 1)): return sub
            elif fn == "rmtree" and isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.strip() in {"/", "~", ".."}:
                return {"allowed": False, "code": "SEC-CMD-01", "reason": "Inline Python AST attempts destructive root/home deletion."}
    return None


def _analyze_shell_segment(seg: str, cmd_str: str, cwd: str, depth: int) -> Optional[Dict[str, Any]]:
    try: tokens = shlex.split(seg, posix=True)
    except ValueError: tokens = seg.split()
    while tokens and (("." not in tokens[0] and "=" in tokens[0] and not tokens[0].startswith("-")) or tokens[0] in {"sudo", "env", "command", "nohup"}):
        tokens.pop(0)
    if not tokens: return None
    cmd, args = Path(tokens[0]).name.lower(), tokens[1:]
    if cmd in SHELL_INTERPRETERS and "-c" in args and args.index("-c") + 1 < len(args):
        if (sub_res := _analyze_shell_ast(args[args.index("-c") + 1], cwd, depth + 1)): return sub_res
    elif cmd in SHELL_INTERPRETERS and not args and re.search(r"\b(?:curl|wget)\b", cmd_str, re.I):
        return {"allowed": False, "code": "SEC-CMD-04", "reason": "Piping remote script into shell (curl|sh) is forbidden."}
    elif cmd in SHELL_INTERPRETERS and not args and re.search(r"\b(?:echo|printf)\b", cmd_str, re.I):
        for m in re.finditer(r"\b(?:echo|printf)\b(?:\s+-[a-zA-Z]+)*\s+(\"[^\"]*\"|'[^']*')", cmd_str):
            if (sub_res := _analyze_shell_ast(m.group(1)[1:-1], cwd, depth + 1)): return sub_res
    elif cmd == "eval" and args and (sub_res := _analyze_shell_ast(" ".join(args), cwd, depth + 1)): return sub_res
    elif cmd in {"python", "python3"} and "-c" in args and args.index("-c") + 1 < len(args):
        if (ast_res := _inspect_inline_python_ast(args[args.index("-c") + 1], cwd, depth + 1)): return ast_res
    if cmd == "rm" and any(a == "--recursive" or (a.startswith("-") and "r" in a.lower()) for a in args):
        if any(not a.startswith("-") and (a in {"/", "~", "..", "../", "$HOME", "${HOME}"} or a.startswith("/dev")) for a in args):
            return {"allowed": False, "code": "SEC-CMD-01", "reason": "Recursive deletion of root, parent, or home is forbidden."}
    elif cmd.startswith("mkfs") or cmd in {"fdisk", "parted", "wipefs"} or (cmd == "dd" and any(a.startswith("of=/dev/") for a in args)):
        return {"allowed": False, "code": "SEC-CMD-02", "reason": "Raw disk formatting or block device overwrite is forbidden."}
    elif cmd in {"chmod", "chown"} and "-R" in args and "777" in args and "/" in args:
        return {"allowed": False, "code": "SEC-CMD-05", "reason": "Global permission destruction (chmod -R 777 /) is forbidden."}
    if cmd in {"echo", "printf"} or (cmd == "git" and args and args[0] == "commit"): return None
    if cmd in {"grep", "egrep", "fgrep", "rg"}:
        skip_next, pattern_seen = False, False
        for a in args:
            if skip_next or a in GREP_VALUE_FLAGS: skip_next = not skip_next
            elif not a.startswith("-") and not pattern_seen: pattern_seen = True
            elif not a.startswith("-") and _is_secret_path(a): return {"allowed": False, "code": "SEC-CRED", "reason": f"Search target '{a}' is a protected credential file."}
        return None
    if any(_is_secret_path(a) for a in args):
        return {"allowed": False, "code": "SEC-CRED", "reason": f"Command '{cmd}' accesses protected credential file."}
    if cmd in NETWORK_CMDS or (cmd == "git" and args and args[0] == "push"):
        if ENV_SECRET_REF_RE.search(seg) or "__SUBSHELL__" in seg:
            return {"allowed": False, "code": "SEC-EXFIL-01", "reason": "Outbound network command attempts to exfiltrate environment or subshell data."}
        if (secrets := scan_plaintext_secrets(" ".join(tokens), cwd=cwd)):
            return {"allowed": False, "code": "SEC-DLP-EGRESS", "reason": f"Outbound command blocked: embedded secret ({secrets[0]['type']} in {secrets[0]['layer']}).", "findings": secrets}
    return None


def _analyze_shell_ast(cmd_str: str, cwd: str = ".", depth: int = 0) -> Optional[Dict[str, Any]]:
    if depth > 6 or not cmd_str: return None
    if re.search(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", cmd_str):
        return {"allowed": False, "code": "SEC-CMD-06", "reason": "Fork bomb execution is forbidden."}
    for seg in _extract_subshells_and_segments(cmd_str, depth):
        for redir_match in re.finditer(r"(?:<|1?>+)\s*([^\s;|&><]+)", seg):
            if _is_secret_path(redir_match.group(1)):
                return {"allowed": False, "code": "SEC-CRED", "reason": f"Shell redirection accesses secret file '{redir_match.group(1)}'."}
        if (seg_res := _analyze_shell_segment(seg, cmd_str, cwd, depth)):
            return seg_res
    return None


def _extract_write_payload(args: Dict[str, Any]) -> str:
    parts = [str(args.get(k) or "") for k in ("content", "Content", "CodeContent", "newText", "new_str", "Replacement", "replacement", "ReplacementContent") if args.get(k)]
    for chunk in args.get("ReplacementChunks") or []:
        if isinstance(chunk, dict):
            for k in ("ReplacementContent", "replacement", "new_str"):
                if chunk.get(k): parts.append(str(chunk[k]))
    return "\n".join(parts)


def evaluate_command_and_path(tool_name: str, args: Dict[str, Any], cwd: str = ".") -> Dict[str, Any]:
    tool, safe_args, cwd_str = (tool_name or "").lower(), (args if isinstance(args, dict) else {}), (cwd or ".")
    cmd_str = str(safe_args.get("command") or safe_args.get("CommandLine") or "")
    target_path = str(safe_args.get("path") or safe_args.get("Path") or safe_args.get("file_path") or safe_args.get("TargetFile") or "")
    policy = load_enterprise_policy(cwd_str)
    rel, in_workspace = "", False
    if target_path:
        if _is_secret_path(target_path):
            return {"allowed": False, "code": "SEC-CRED", "reason": f"Access to secret file '{target_path}' is blocked."}
        root_p, cand_p = Path(cwd_str).expanduser().resolve(), Path(target_path).expanduser()
        resolved_p = (root_p / cand_p).resolve() if not cand_p.is_absolute() else cand_p.resolve()
        try:
            rel, in_workspace = str(resolved_p.relative_to(root_p)).replace("\\", "/"), True
        except (ValueError, OSError):
            rel = str(resolved_p).replace("\\", "/")
    if rel and in_workspace and tool in WRITE_TOOLS:
        allow_cp = os.environ.get("NETARK_ALLOW_CONTROL_PLANE") == "1" or os.environ.get("PRISM_ALLOW_CONTROL_PLANE") == "1"
        raw_prot = policy.get("protected_paths")
        cp_prefixes = () if allow_cp else PROTECTED_CONTROL_PATHS + tuple(str(p) for p in (raw_prot if isinstance(raw_prot, list) else []) if p)
        for prefix in cp_prefixes:
            if rel == prefix.rstrip("/") or rel.startswith(prefix):
                return {"allowed": False, "code": "SEC-CONTROL-PLANE", "ask_confirmation": True, "reason": f"Mutation of protected control-plane path '{rel}' is blocked."}
        if (place_err := check_code_placement(rel, cwd_str, policy)): return place_err
    if tool in WRITE_TOOLS:
        write_payload = _extract_write_payload(safe_args)
        if write_payload and (lint_verdict := check_prewrite_secret_lint(write_payload, target_path=target_path, cwd=cwd_str)):
            return lint_verdict
    if (web_err := check_web_and_ssrf_guard(tool, safe_args, policy)): return web_err
    if cmd_str and (ast_verdict := _analyze_shell_ast(normalize_and_deobfuscate(cmd_str)["cleaned_text"], cwd=cwd_str)):
        return ast_verdict
    if (read_err := check_direct_read_guard(tool, safe_args, cwd_str, policy)): return read_err
    return {"allowed": True, "code": "PASS", "reason": "Passed Tier 0 structural AST & DLP guard."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetArk Guard Core Tier 0 CLI")
    parser.add_argument("--self-test", action="store_true", help="Run built-in Tier 0 AST, G-01..G-05 & DLP assertions")
    if parser.parse_args().self_test:
        b64_aws = base64.b64encode(b"export AWS_KEY=AKIA" + b"IOSFODNN7EXAMPLE").decode("ascii")
        res = redact_sensitive_payload(f"normal\u200btext with hidden: {b64_aws} and ghp_" + "1234567890abcdefghijklmnopqrstuvwxyzABCD")
        assert any(r["type"] == "AWS_ACCESS_KEY" and r["layer"].startswith("base64") for r in res["redactions"])
        assert not evaluate_command_and_path("read_file", {"Path": ".netark/audit/.session_vault.json"})["allowed"]
        assert not evaluate_command_and_path("bash", {"command": "cat .session_vault.json"})["allowed"]
        prewrite = evaluate_command_and_path("write_file", {"Path": "src/app.py", "Content": 'API_KEY = "sk-proj-' + '1234567890abcdefghijklmnop"'})
        assert not prewrite["allowed"] and prewrite["code"] == "SEC-PREWRITE-SECRET"
        assert scan_plaintext_secrets("https://example.com/assets/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789") == []
        assert not evaluate_command_and_path("bash", {"command": 'cat .e"n"v'})["allowed"]
        assert not evaluate_command_and_path("bash", {"command": 'python3 -c "print(open(\'.env\').read())"'})["allowed"]
        print(json.dumps({"status": "ok", "patterns": len(SECRET_PATTERNS), "redactions": res["redactions"]}))
        sys.exit(0)
