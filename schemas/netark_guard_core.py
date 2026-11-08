#!/usr/bin/env python3
"""
NetArk Guard Core — Tier 0 Structural AST/Lexer Engine, Deobfuscation, Pre-Write Secret Lint & Outbound DLP
===========================================================================================================
Governing Rules: 100.ARCH-RULES.v1 (SEC-CRED, SEC-PREWRITE-SECRET, SEC-CONTROL-PLANE, G-01..G-05)
Zero third-party dependencies; pure Python standard library (ast, shlex) (< 360 lines).
"""

from __future__ import annotations

import argparse, ast, base64, binascii, json, math, os, re, shlex, sys, urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

INVISIBLE_UNICODE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\U000e0000-\U000e007f]")
BASE64_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9+/=])([A-Za-z0-9+/]{16,}={0,2})(?![A-Za-z0-9+/=])")
HEX_CANDIDATE_RE = re.compile(r"\b(?:0x)?([0-9a-fA-F]{24,})\b")

# G-03 Fix: Deterministic 12 explicit secret formats (no blind full-text high-entropy token replacement)
SECRET_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("AWS_ACCESS_KEY", re.compile(r"\b((?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16})\b")),
    ("GCP_API_KEY", re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b")),
    ("GITHUB_PAT", re.compile(r"\b((?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36,255}|github_pat_[0-9A-Za-z_]{50,255})\b")),
    ("OPENAI_KEY", re.compile(r"\b(sk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,})\b")),
    ("ANTHROPIC_KEY", re.compile(r"\b(sk-ant-api03-[A-Za-z0-9\-_]{20,})\b")),
    ("NVIDIA_NIM_KEY", re.compile(r"\b(nvapi-[A-Za-z0-9\-_]{24,})\b")),
    ("SLACK_TOKEN", re.compile(r"\b(xox[baprs]-[0-9A-Za-z\-]{10,48})\b")),
    ("STRIPE_OR_HF_TOKEN", re.compile(r"\b((?:sk|rk)_live_[0-9a-zA-Z]{24,}|hf_[A-Za-z0-9]{34,})\b")),
    ("JWT_TOKEN", re.compile(r"\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b")),
    ("DB_CONN_URI", re.compile(r"\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s\"'<>]+:[^\s\"'<>@]+@[^\s\"'<>]+)\b")),
    ("GENERIC_SECRET_ASSIGN", re.compile(r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|private[_-]?key)\s*[:=]\s*[\"']([A-Za-z0-9/+_\-=]{16,})[\"']")),
]

PROTECTED_CONTROL_PATHS = (".netark/", ".agents/", ".claude/", ".github/workflows/", "schemas/")
# G-01 Fix: Explicitly block any *vault*.json alongside .env, auth.json, and SSH/GCP private keys
SECRET_FILENAME_RE = re.compile(
    r"^(?:\.env(?!(?:\.example|\.sample|\.template)$)(?:\.[A-Za-z0-9._-]+)?|auth\.json|.*vault.*\.json|id_rsa|id_ed25519|id_ecdsa|application_default_credentials\.json)$",
    re.I,
)
ENV_SECRET_REF_RE = re.compile(r"\$\{?[A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASS|CRED|ENV)[A-Za-z0-9_]*\}?", re.I)
NETWORK_CMDS = {"curl", "wget", "nc", "netcat", "socat", "nslookup", "dig", "scp", "rsync", "ssh"}
SHELL_INTERPRETERS = {"sh", "bash", "zsh", "dash", "ksh"}
GREP_VALUE_FLAGS = {"-e", "--regexp", "-f", "--file", "-m", "--max-count", "-A", "-B", "-C", "--include", "--exclude", "--exclude-dir"}


def _is_printable_text(raw: bytes) -> Optional[str]:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return decoded if len(decoded) >= 6 and (sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t") / len(decoded)) >= 0.85 else None


def normalize_and_deobfuscate(text: str, max_passes: int = 2) -> Dict[str, Any]:
    """Strip zero-width invisible characters and decode embedded Base64/Hex/URL-encoded payloads."""
    text = text if isinstance(text, str) else str(text)
    invisible_matches = INVISIBLE_UNICODE_RE.findall(text)
    cleaned = INVISIBLE_UNICODE_RE.sub("", text)
    decoded_segments: List[Dict[str, str]] = []
    current = cleaned
    for pass_idx in range(max_passes):
        next_fragments: List[str] = []
        if "%" in current:
            unquoted = urllib.parse.unquote(current)
            if unquoted != current:
                decoded_segments.append({"encoding": f"url_pass_{pass_idx + 1}", "source": current, "decoded": unquoted})
                next_fragments.append(unquoted)
        for match in BASE64_CANDIDATE_RE.finditer(current):
            blob = match.group(1)
            if len(blob) % 4 == 0:
                try:
                    decoded = _is_printable_text(base64.b64decode(blob, validate=True))
                    if decoded and decoded != blob:
                        decoded_segments.append({"encoding": f"base64_pass_{pass_idx + 1}", "source": blob, "decoded": decoded})
                        next_fragments.append(decoded)
                except (binascii.Error, ValueError):
                    pass
        for match in HEX_CANDIDATE_RE.finditer(current):
            hex_blob = match.group(1)
            if len(hex_blob) % 2 == 0:
                try:
                    decoded = _is_printable_text(bytes.fromhex(hex_blob))
                    if decoded:
                        decoded_segments.append({"encoding": f"hex_pass_{pass_idx + 1}", "source": hex_blob, "decoded": decoded})
                        next_fragments.append(decoded)
                except ValueError:
                    pass
        if not next_fragments:
            break
        current = "\n".join(next_fragments)
    return {
        "cleaned_text": cleaned,
        "flattened_text": "\n".join([cleaned] + [seg["decoded"] for seg in decoded_segments]),
        "invisible_char_count": len(invisible_matches),
        "decoded_segments": decoded_segments,
    }


def calculate_shannon_entropy(token: str) -> float:
    if not token:
        return 0.0
    length = len(token)
    counts: Dict[str, int] = {}
    for ch in token:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def load_enterprise_policy(cwd: str = ".") -> Dict[str, Any]:
    brain_dir = os.environ.get("PI_CODING_AGENT_DIR") or str(Path(cwd) / ".netark")
    for p in (Path(brain_dir) / "enterprise-policy.json", Path(cwd) / ".netark" / "enterprise-policy.json", Path(cwd) / "enterprise-policy.json"):
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return {}


def scan_plaintext_secrets(text: str, cwd: str = ".") -> List[Dict[str, Any]]:
    """Deterministic multi-layer secret scanner across 12 explicit credential patterns and enterprise policy rules (G-03, G-05)."""
    if not text:
        return []
    deob = normalize_and_deobfuscate(text)
    policy = load_enterprise_policy(cwd)
    findings, seen_values = [], set()
    active_patterns = list(SECRET_PATTERNS)
    for item in policy.get("custom_secret_patterns", []):
        if isinstance(item, dict) and item.get("name") and item.get("pattern"):
            try:
                active_patterns.append((str(item["name"]), re.compile(str(item["pattern"]))))
            except re.error:
                pass
    layers: List[Tuple[str, str, str]] = [("raw", deob["cleaned_text"], "")] + [(s["encoding"], s["decoded"], s.get("source", "")) for s in deob["decoded_segments"]]
    for layer_name, content, source_blob in layers:
        for literal in policy.get("custom_redact_literals", []):
            lit_str = str(literal).strip()
            if len(lit_str) >= 4 and lit_str not in seen_values and re.search(rf"(?<![A-Za-z0-9_]){re.escape(lit_str)}(?![A-Za-z0-9_])", content):
                seen_values.add(lit_str)
                findings.append({"type": "CORP_LITERAL", "value": lit_str, "layer": layer_name, "source_blob": source_blob, "entropy": round(calculate_shannon_entropy(lit_str), 3)})
        for secret_type, pattern in active_patterns:
            for match in pattern.finditer(content):
                val = match.group(1) if match.lastindex else match.group(0)
                if val not in seen_values and not val.startswith("<NETARK_REDACTED:") and not val.startswith("<REDACTED"):
                    seen_values.add(val)
                    findings.append({"type": secret_type, "value": val, "layer": layer_name, "source_blob": source_blob, "entropy": round(calculate_shannon_entropy(val), 3)})
    return findings


scan_secrets_and_entropy = scan_plaintext_secrets


def redact_sensitive_payload(text: str, cwd: str = ".") -> Dict[str, Any]:
    """One-way deterministic redaction for stdout/log sanitization (G-01/G-02/G-04: no persistent or reversible session_vault)."""
    findings = scan_plaintext_secrets(text, cwd=cwd)
    redacted_text, redactions = text, []
    type_counters: Dict[str, int] = {}
    for item in findings:
        secret_val, s_type, source_blob = item["value"], item["type"], item.get("source_blob") or ""
        target_in_text = secret_val if secret_val in redacted_text else (source_blob if source_blob in redacted_text else "")
        if not target_in_text:
            continue
        next_idx = type_counters.get(s_type, 0) + 1
        type_counters[s_type] = next_idx
        placeholder = f"<NETARK_REDACTED:{s_type}_{next_idx}>"
        if s_type == "CORP_LITERAL" and target_in_text == secret_val:
            redacted_text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(target_in_text)}(?![A-Za-z0-9_])", placeholder, redacted_text)
        else:
            redacted_text = redacted_text.replace(target_in_text, placeholder)
        redactions.append({"placeholder": placeholder, "type": s_type, "layer": item["layer"]})
    return {"redacted_text": redacted_text, "redaction_count": len(redactions), "redactions": redactions}


def check_prewrite_secret_lint(content: str, target_path: str = "", cwd: str = ".") -> Optional[Dict[str, Any]]:
    """G-02 / G-04 Fix: Pre-Write Secret Lint blocks writing hardcoded keys to disk and instructs using os.environ.get('KEY_NAME')."""
    if not content or os.environ.get("NETARK_ALLOW_SECRET_FIXTURE") == "1":
        return None
    if (findings := scan_plaintext_secrets(content, cwd=cwd)):
        first = findings[0]
        return {
            "allowed": False, "code": "SEC-PREWRITE-SECRET", "findings": findings,
            "reason": (
                f"Pre-Write Secret Lint blocked hardcoded credential ({first['type']}) in '{target_path or 'payload'}'. "
                "Do NOT hardcode API keys or secrets in files. Refactor code to use os.environ.get('KEY_NAME') "
                "(or process.env.KEY_NAME) and ask the human user to configure '.env' manually (Agent access to '.env' is strictly prohibited)."
            ),
        }
    return None


def _is_secret_path(candidate: str) -> bool:
    for part in (candidate.split("=", 1) if "=" in candidate else [candidate]):
        cleaned = part.strip().lstrip("@").strip("\"'")
        if cleaned and not cleaned.startswith("-") and SECRET_FILENAME_RE.match(Path(cleaned.replace("\\", "/")).name):
            return True
    return False


def _extract_subshells_and_segments(src: str, depth: int = 0) -> List[str]:
    """Stage A: Quote-aware lexer extracting $(...), `...`, and top-level pipeline segments."""
    if depth > 6 or not src.strip():
        return []
    subshells, segments, cur = [], [], []
    i, n, mode = 0, len(src), "none"
    while i < n:
        ch = src[i]
        if mode == "single":
            cur.append(ch)
            mode = "none" if ch == "'" else mode
            i += 1
        elif ch == "\\" and i + 1 < n:
            cur.append(src[i : i + 2])
            i += 2
        elif ch == "$" and i + 1 < n and src[i + 1] == "(":
            p_depth, j, sub_m = 1, i + 2, "none"
            while j < n and p_depth > 0:
                c = src[j]
                if sub_m == "single" and c == "'":
                    sub_m = "none"
                elif sub_m != "single" and c == "\\" and j + 1 < n:
                    j += 1
                elif sub_m == "double":
                    if c == '"':
                        sub_m = "none"
                    elif c == "(" and src[j - 1] == "$":
                        p_depth += 1
                elif sub_m == "none":
                    if c in ("'", '"'):
                        sub_m = "single" if c == "'" else "double"
                    elif c in ("(", ")"):
                        p_depth += 1 if c == "(" else -1
                j += 1
            subshells.extend(_extract_subshells_and_segments(src[i + 2 : max(i + 2, j - 1)], depth + 1))
            cur.append("__SUBSHELL__")
            i = j
        elif ch == "`":
            j = i + 1
            while j < n and src[j] != "`":
                j += 2 if src[j] == "\\" else 1
            subshells.extend(_extract_subshells_and_segments(src[i + 1 : j], depth + 1))
            cur.append("__SUBSHELL__")
            i = j + 1
        elif mode == "double":
            cur.append(ch)
            mode = "none" if ch == '"' else mode
            i += 1
        elif ch in ("'", '"'):
            mode = "single" if ch == "'" else "double"
            cur.append(ch)
            i += 1
        elif ch == "#" and (i == 0 or src[i - 1].isspace()):
            while i < n and src[i] != "\n":
                i += 1
        elif ch in (";", "\n") or (ch in ("|", "&") and i + 1 < n and src[i + 1] == ch) or ch == "|":
            if "".join(cur).strip():
                segments.append("".join(cur).strip())
            cur = []
            i += 2 if (i + 1 < n and src[i + 1] == ch and ch in ("|", "&")) else 1
        else:
            cur.append(ch)
            i += 1
    if "".join(cur).strip():
        segments.append("".join(cur).strip())
    return segments + subshells


def _inspect_inline_python_ast(code: str, cwd: str = ".", depth: int = 0) -> Optional[Dict[str, Any]]:
    """Stage C: Native Python ast.parse() static analyzer for `python -c` inline code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _is_secret_path(node.value):
            return {"allowed": False, "code": "SEC-CRED", "reason": f"Inline Python AST accesses protected secret file '{node.value}'."}
        if isinstance(node, ast.Call):
            fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None) or ""
            for arg in node.args:
                if fn in {"system", "popen", "run", "call", "check_output", "Popen"}:
                    cmd_val = arg.value if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)) else (
                        " ".join(shlex.quote(e.value) for e in arg.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
                        if isinstance(arg, (ast.List, ast.Tuple)) else ""
                    )
                    if cmd_val and (sub := _analyze_shell_ast(cmd_val, cwd, depth + 1)):
                        return sub
                elif fn == "rmtree" and isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.strip() in {"/", "~", ".."}:
                    return {"allowed": False, "code": "SEC-CMD-01", "reason": "Inline Python AST attempts destructive root/home deletion."}
    return None


def _analyze_shell_ast(cmd_str: str, cwd: str = ".", depth: int = 0) -> Optional[Dict[str, Any]]:
    """Stage B: POSIX shlex tokenizer with quote coalescing, recursive -c unwrapping, and role-bound operand checks."""
    if depth > 6:
        return None
    if re.search(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", cmd_str):
        return {"allowed": False, "code": "SEC-CMD-06", "reason": "Fork bomb execution is forbidden."}
    for seg in _extract_subshells_and_segments(cmd_str, depth):
        for redir_match in re.finditer(r"(?:<|1?>+)\s*([^\s;|&><]+)", seg):
            if _is_secret_path(redir_match.group(1)):
                return {"allowed": False, "code": "SEC-CRED", "reason": f"Shell redirection accesses secret file '{redir_match.group(1)}'."}
        try:
            tokens = shlex.split(seg, posix=True)
        except ValueError:
            tokens = seg.split()
        while tokens and (("." not in tokens[0] and "=" in tokens[0] and not tokens[0].startswith("-")) or tokens[0] in {"sudo", "env", "command", "nohup"}):
            tokens.pop(0)
        if not tokens:
            continue
        cmd, args = Path(tokens[0]).name.lower(), tokens[1:]
        if cmd in SHELL_INTERPRETERS:
            if "-c" in args and args.index("-c") + 1 < len(args) and (sub_res := _analyze_shell_ast(args[args.index("-c") + 1], cwd, depth + 1)):
                return sub_res
            elif not args and re.search(r"\b(?:curl|wget)\b", cmd_str, re.I):
                return {"allowed": False, "code": "SEC-CMD-04", "reason": "Piping remote script into shell (curl|sh) is forbidden."}
            elif not args and re.search(r"\b(?:echo|printf)\b", cmd_str, re.I):
                for m in re.finditer(r"\b(?:echo|printf)\b(?:\s+-[a-zA-Z]+)*\s+(\"[^\"]*\"|'[^']*')", cmd_str):
                    if (sub_res := _analyze_shell_ast(m.group(1)[1:-1], cwd, depth + 1)):
                        return sub_res
        elif cmd == "eval" and args and (sub_res := _analyze_shell_ast(" ".join(args), cwd, depth + 1)):
            return sub_res
        elif cmd in {"python", "python3"} and "-c" in args and args.index("-c") + 1 < len(args):
            if (ast_res := _inspect_inline_python_ast(args[args.index("-c") + 1], cwd, depth + 1)):
                return ast_res
        if cmd == "rm" and any(a == "--recursive" or (a.startswith("-") and "r" in a.lower()) for a in args):
            if any(not a.startswith("-") and (a in {"/", "~", "..", "../", "$HOME", "${HOME}"} or a.startswith("/dev")) for a in args):
                return {"allowed": False, "code": "SEC-CMD-01", "reason": "Recursive deletion of root, parent, or home is forbidden."}
        elif cmd in {"mkfs", "fdisk", "parted", "wipefs"} or (cmd == "dd" and any(a.startswith("of=/dev/") for a in args)):
            return {"allowed": False, "code": "SEC-CMD-02", "reason": "Raw disk formatting or block device overwrite is forbidden."}
        elif cmd in {"chmod", "chown"} and "-R" in args and "777" in args and "/" in args:
            return {"allowed": False, "code": "SEC-CMD-05", "reason": "Global permission destruction (chmod -R 777 /) is forbidden."}
        if cmd in {"echo", "printf"} or (cmd == "git" and args and args[0] == "commit"):
            continue
        if cmd in {"grep", "egrep", "fgrep", "rg"}:
            skip_next, pattern_seen = False, False
            for a in args:
                if skip_next or a in GREP_VALUE_FLAGS:
                    skip_next = not skip_next
                elif not a.startswith("-"):
                    if not pattern_seen:
                        pattern_seen = True
                    elif _is_secret_path(a):
                        return {"allowed": False, "code": "SEC-CRED", "reason": f"Search target '{a}' is a protected credential file."}
            continue
        if any(_is_secret_path(a) for a in args):
            return {"allowed": False, "code": "SEC-CRED", "reason": f"Command '{cmd}' accesses protected credential file."}
        if cmd in NETWORK_CMDS or (cmd == "git" and args and args[0] == "push"):
            if ENV_SECRET_REF_RE.search(seg) or "__SUBSHELL__" in seg:
                return {"allowed": False, "code": "SEC-EXFIL-01", "reason": "Outbound network command attempts to exfiltrate environment or subshell data."}
            if (secrets := scan_plaintext_secrets(" ".join(tokens), cwd=cwd)):
                return {"allowed": False, "code": "SEC-DLP-EGRESS", "reason": f"Outbound command blocked: embedded secret ({secrets[0]['type']} in {secrets[0]['layer']}).", "findings": secrets}
    return None


def evaluate_command_and_path(tool_name: str, args: Dict[str, Any], cwd: str = ".") -> Dict[str, Any]:
    tool = (tool_name or "").lower()
    cmd_str = str(args.get("command") or args.get("CommandLine") or "")
    target_path = str(args.get("path") or args.get("Path") or args.get("file_path") or "")
    policy = load_enterprise_policy(cwd)
    if target_path:
        if _is_secret_path(target_path):
            return {"allowed": False, "code": "SEC-CRED", "reason": f"Access to secret file '{target_path}' is blocked."}
        try:
            rel = str(Path(target_path).resolve().relative_to(Path(cwd).resolve())).replace("\\", "/")
        except Exception:
            rel = target_path.replace("\\", "/")
        allow_cp = os.environ.get("NETARK_ALLOW_CONTROL_PLANE") == "1" or os.environ.get("PRISM_ALLOW_CONTROL_PLANE") == "1"
        if tool in {"write", "edit", "write_file", "edit_file", "replace"} and not allow_cp:
            for prefix in PROTECTED_CONTROL_PATHS + tuple(str(p) for p in policy.get("protected_paths", [])):
                if rel == prefix.rstrip("/") or rel.startswith(prefix):
                    return {"allowed": False, "code": "SEC-CONTROL-PLANE", "reason": f"Mutation of protected control-plane path '{rel}' is blocked."}
    if tool in {"write", "edit", "write_file", "edit_file", "replace"}:
        write_payload = "\n".join(str(args.get(k) or "") for k in ("content", "Content", "newText", "new_str", "Replacement", "replacement") if args.get(k))
        if write_payload and (lint_verdict := check_prewrite_secret_lint(write_payload, target_path=target_path, cwd=cwd)):
            return lint_verdict
    if cmd_str and (ast_verdict := _analyze_shell_ast(normalize_and_deobfuscate(cmd_str)["cleaned_text"], cwd=cwd)):
        return ast_verdict
    return {"allowed": True, "code": "PASS", "reason": "Passed Tier 0 structural AST & DLP guard."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetArk Guard Core Tier 0 CLI")
    parser.add_argument("--self-test", action="store_true", help="Run built-in Tier 0 AST, G-01..G-05 & DLP assertions")
    if parser.parse_args().self_test:
        b64_aws = base64.b64encode(b"export AWS_KEY=AKIAIOSFODNN7EXAMPLE").decode("ascii")
        sample = f"normal\u200btext with hidden payload: {b64_aws} and raw ghp_1234567890abcdefghijklmnopqrstuvwxyzABCD"
        res = redact_sensitive_payload(sample)
        assert any(r["type"] == "AWS_ACCESS_KEY" and r["layer"].startswith("base64") for r in res["redactions"])
        assert not evaluate_command_and_path("read_file", {"Path": ".netark/audit/.session_vault.json"})["allowed"]
        assert not evaluate_command_and_path("bash", {"command": "cat .session_vault.json"})["allowed"]
        prewrite = evaluate_command_and_path("write_file", {"Path": "src/app.py", "Content": 'API_KEY = "sk-proj-1234567890abcdefghijklmnop"'})
        assert not prewrite["allowed"] and prewrite["code"] == "SEC-PREWRITE-SECRET"
        assert scan_plaintext_secrets("https://example.com/assets/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789") == []
        assert not evaluate_command_and_path("bash", {"command": 'cat .e"n"v'})["allowed"]
        assert not evaluate_command_and_path("bash", {"command": 'python3 -c "print(open(\'.env\').read())"'})["allowed"]
        print(json.dumps({"status": "ok", "patterns": len(SECRET_PATTERNS), "redactions": res["redactions"]}))
        sys.exit(0)
