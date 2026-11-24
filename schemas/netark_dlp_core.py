#!/usr/bin/env python3
"""NetArk DLP, Deobfuscation, Entropy & Enterprise Policy Core (schemas/netark_dlp_core.py)."""

from __future__ import annotations

import base64, binascii, json, math, os, re, urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

INVISIBLE_UNICODE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\U000e0000-\U000e007f]")
BASE64_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9+/=])([A-Za-z0-9+/]{16,}={0,2})(?![A-Za-z0-9+/=])")
HEX_CANDIDATE_RE = re.compile(r"\b(?:0x)?([0-9a-fA-F]{24,})\b")
ASSIGN_RHS_RE = re.compile(r"(?:(?<=[\s,(;{])|^)[\"']?([A-Za-z0-9_.\-]+)[\"']?\s*[:=](?!//)\s*([\"']?)([A-Za-z0-9+/=_\-.$!@#%^&*~]+)\2")
PATH_EXT_RE = re.compile(r"\.(?:md|py|json|jsonl|ts|tsx|js|mjs|yml|yaml|txt|sh|toml|html|css|onnx|csv|lock)$", re.I)

SECRET_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("AWS_ACCESS_KEY", re.compile(r"\b((?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16})\b")),
    ("GCP_API_KEY", re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b")),
    ("GITHUB_PAT", re.compile(r"\b((?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36,255}|github_pat_[0-9A-Za-z_]{50,255})\b")),
    ("OPENAI_KEY", re.compile(r"\b(sk-(?:proj-|svcacct-|ant-)?[A-Za-z0-9_\-]{20,})\b")),
    ("ANTHROPIC_KEY", re.compile(r"\b(sk-ant-api03-[A-Za-z0-9\-_]{20,})\b")),
    ("NVIDIA_NIM_KEY", re.compile(r"\b(nvapi-[A-Za-z0-9\-_]{24,})\b")),
    ("SLACK_TOKEN", re.compile(r"\b(xox[baprs]-[0-9A-Za-z\-]{10,48})\b")),
    ("STRIPE_OR_HF_TOKEN", re.compile(r"\b((?:sk|rk)_live_[0-9a-zA-Z]{24,}|hf_[A-Za-z0-9]{34,})\b")),
    ("JWT_TOKEN", re.compile(r"\b(eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b")),
    ("DB_CONN_URI", re.compile(r"\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s\"'<>]+:[^\s\"'<>@]+@[^\s\"'<>]+)\b")),
    ("GENERIC_SECRET_ASSIGN", re.compile(r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|private[_-]?key)\s*[:=]\s*[\"']([A-Za-z0-9/+_\-=]{16,})[\"']")),
]


def _is_printable_text(raw: bytes) -> Optional[str]:
    try: decoded = raw.decode("utf-8")
    except UnicodeDecodeError: return None
    return decoded if len(decoded) >= 6 and (sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t") / len(decoded)) >= 0.85 else None


def _decode_encoded_blobs(current: str, pass_idx: int, decoded_segments: List[Dict[str, str]]) -> List[str]:
    frags: List[str] = []
    if "%" in current:
        unquoted = urllib.parse.unquote(current)
        if unquoted != current:
            decoded_segments.append({"encoding": f"url_pass_{pass_idx + 1}", "source": current, "decoded": unquoted})
            frags.append(unquoted)
    for match in BASE64_CANDIDATE_RE.finditer(current):
        blob = match.group(1)
        if len(blob) % 4 != 0: continue
        try: decoded = _is_printable_text(base64.b64decode(blob, validate=True))
        except (binascii.Error, ValueError): decoded = None
        if decoded and decoded != blob:
            decoded_segments.append({"encoding": f"base64_pass_{pass_idx + 1}", "source": blob, "decoded": decoded})
            frags.append(decoded)
    for match in HEX_CANDIDATE_RE.finditer(current):
        hex_blob = match.group(1)
        if len(hex_blob) % 2 != 0: continue
        try: decoded = _is_printable_text(bytes.fromhex(hex_blob))
        except ValueError: decoded = None
        if decoded:
            decoded_segments.append({"encoding": f"hex_pass_{pass_idx + 1}", "source": hex_blob, "decoded": decoded})
            frags.append(decoded)
    return frags


def normalize_and_deobfuscate(text: str, max_passes: int = 2) -> Dict[str, Any]:
    text = text if isinstance(text, str) else str(text)
    invisible_matches, cleaned = INVISIBLE_UNICODE_RE.findall(text), INVISIBLE_UNICODE_RE.sub("", text)
    decoded_segments, current = [], cleaned
    try: passes = max(0, int(2 if max_passes is None else max_passes))
    except (TypeError, ValueError): passes = 2
    for pass_idx in range(passes):
        next_fragments = _decode_encoded_blobs(current, pass_idx, decoded_segments)
        if not next_fragments: break
        current = "\n".join(next_fragments)
    return {"cleaned_text": cleaned, "flattened_text": "\n".join([cleaned] + [s["decoded"] for s in decoded_segments]), "invisible_char_count": len(invisible_matches), "decoded_segments": decoded_segments}


def calculate_shannon_entropy(token: str) -> float:
    if not token: return 0.0
    length, counts = len(token), {}
    for ch in token: counts[ch] = counts.get(ch, 0) + 1
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def load_enterprise_policy(cwd: str = ".") -> Dict[str, Any]:
    base = Path(cwd or ".")
    brain_dir = os.environ.get("PI_CODING_AGENT_DIR") or str(base / (".agents" if (base / ".agents").exists() and not (base / ".netark").exists() else ".netark"))
    policy: Dict[str, Any] = {}
    raw_vault_false = False
    for p in (Path(brain_dir) / "enterprise-policy.json", base / ".agents" / "enterprise-policy.json", base / ".netark" / "enterprise-policy.json", base / "enterprise-policy.json", base / ".netarkrc.json"):
        if not p.exists(): continue
        try: data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError): continue
        if isinstance(data, dict):
            if data.get("session_vault_disabled") is False: raw_vault_false = True
            policy.update(data)
    policy["session_vault_disabled"] = True
    if raw_vault_false: policy["_vault_override_warning"] = "G-01: session_vault_disabled is immutable and forced to True."
    return policy


def check_enterprise_feature(feature: str, policy: Optional[Dict[str, Any]] = None, license_info: Optional[Dict[str, Any]] = None) -> bool:
    pol = policy if isinstance(policy, dict) else {}
    if not pol.get("enforce_license_gate", False): return True
    lic = license_info if isinstance(license_info, dict) else {}
    return bool(lic.get("tier") == "enterprise" and lic.get("valid"))


def _is_benign_entropy_token(lhs: str, tok: str) -> bool:
    if "://" in tok or tok.startswith(("/", "./", "../", "~/")) or "<NETARK_REDACTED:" in tok or "<REDACTED" in tok:
        return True
    if PATH_EXT_RE.search(tok) or re.fullmatch(r"[a-z0-9_.-]+(?:/[a-z0-9_.-]+)+", tok):
        return True
    if re.fullmatch(r"[0-9a-fA-F]{24,}", tok) or re.fullmatch(r"\d{3}\.[A-Z0-9_.-]+\.v\d+", tok) or re.fullmatch(r"[0-9a-f]{16}_\d{3}_[A-Za-z0-9_]+", tok) or re.fullmatch(r"(?:\d{3}(?:\.\d+)?=)?\d+_[A-Z0-9]+(?:_[A-Z0-9]+)+", tok) or (not tok.startswith("eyJ") and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", tok)):
        return True
    return lhs.lower() in {"sha256_16", "sha256", "sha1", "md5", "checksum", "content_checksum", "commit", "node_key", "node_id"} and "_" in tok


def _scan_layer_secrets(
    layer_name: str, content: str, source_blob: str, active_patterns: List[Tuple[str, re.Pattern[str]]],
    literals: List[str], seen_values: Set[str], source_blobs: Set[str],
) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for lit_str in literals:
        if lit_str not in seen_values and re.search(rf"(?<![A-Za-z0-9_]){re.escape(lit_str)}(?![A-Za-z0-9_])", content):
            seen_values.add(lit_str)
            if source_blob: source_blobs.add(source_blob)
            found.append({"type": "CORP_LITERAL", "value": lit_str, "layer": layer_name, "source_blob": source_blob, "entropy": round(calculate_shannon_entropy(lit_str), 3)})
    for secret_type, pattern in active_patterns:
        for match in pattern.finditer(content):
            val = match.group(1) if match.lastindex else match.group(0)
            if val not in seen_values and not val.startswith(("<NETARK_REDACTED:", "<REDACTED")):
                seen_values.add(val)
                if source_blob: source_blobs.add(source_blob)
                found.append({"type": secret_type, "value": val, "layer": layer_name, "source_blob": source_blob, "entropy": round(calculate_shannon_entropy(val), 3)})
    return found


def scan_plaintext_secrets(text: str, cwd: str = ".") -> List[Dict[str, Any]]:
    if not text: return []
    deob, policy = normalize_and_deobfuscate(text), load_enterprise_policy(cwd)
    findings, seen_values, source_blobs = [], set(), set()
    active_patterns = list(SECRET_PATTERNS)
    raw_pats = policy.get("custom_secret_patterns")
    for item in (raw_pats if isinstance(raw_pats, list) else []):
        if isinstance(item, dict) and item.get("name") and item.get("pattern"):
            try: active_patterns.append((str(item["name"]), re.compile(str(item["pattern"]))))
            except re.error: continue
    raw_lits = policy.get("custom_redact_literals")
    literals = [str(lit).strip() for lit in (raw_lits if isinstance(raw_lits, list) else []) if len(str(lit).strip()) >= 4]
    try: threshold = float(0 if policy.get("entropy_threshold") is None else policy.get("entropy_threshold", 0))
    except (TypeError, ValueError): threshold = 0.0
    try: min_len = int(24 if policy.get("entropy_min_token_len") is None else policy.get("entropy_min_token_len", 24))
    except (TypeError, ValueError): min_len = 24
    if min_len <= 0: min_len = 24
    layers: List[Tuple[str, str, str]] = [("raw", deob["cleaned_text"], "")] + [(s["encoding"], s["decoded"], s.get("source", "")) for s in deob["decoded_segments"]]
    for layer_name, content, source_blob in layers:
        findings.extend(_scan_layer_secrets(layer_name, content, source_blob, active_patterns, literals, seen_values, source_blobs))
    if threshold <= 0: return findings
    for layer_name, content, source_blob in reversed(layers):
        for m in ASSIGN_RHS_RE.finditer(content):
            lhs, tok = m.group(1), m.group(3)
            if len(tok) < min_len or tok in seen_values or tok in source_blobs or _is_benign_entropy_token(lhs, tok): continue
            ent = calculate_shannon_entropy(tok)
            if ent < threshold: continue
            seen_values.add(tok)
            if source_blob: source_blobs.add(source_blob)
            findings.append({"type": "HIGH_ENTROPY_SECRET", "value": tok, "raw": tok, "match": tok[:8] + "...", "layer": layer_name, "source_blob": source_blob, "entropy": round(ent, 3)})
    return findings


scan_secrets_and_entropy = scan_plaintext_secrets


def redact_sensitive_payload(text: str, cwd: str = ".") -> Dict[str, Any]:
    findings = scan_plaintext_secrets(text, cwd=cwd)
    redacted_text, redactions, type_counters = text, [], {}
    for item in findings:
        secret_val, s_type, source_blob = item["value"], item["type"], item.get("source_blob") or ""
        target_in_text = secret_val if secret_val in redacted_text else (source_blob if source_blob in redacted_text else "")
        if not target_in_text: continue
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
    if not content or os.environ.get("NETARK_ALLOW_SECRET_FIXTURE") == "1": return None
    if load_enterprise_policy(cwd).get("prewrite_secret_lint") is False: return None
    if (findings := scan_plaintext_secrets(content, cwd=cwd)):
        first = findings[0]
        return {
            "allowed": False, "code": "SEC-PREWRITE-SECRET", "findings": findings,
            "reason": f"Pre-Write Secret Lint blocked hardcoded credential ({first['type']}) in '{target_path or 'payload'}'. Do NOT hardcode API keys or secrets in files. Refactor code to use os.environ.get('KEY_NAME') (or process.env.KEY_NAME) and ask the human user to configure '.env' manually (Agent access to '.env' is strictly prohibited).",
        }
    return None
