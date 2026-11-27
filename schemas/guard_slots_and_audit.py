#!/usr/bin/env python3
"""NetArk Guard Model Slots, Offline License & Signed SOC2 Audit (schemas/guard_slots_and_audit.py)."""

from __future__ import annotations

import base64, hashlib, hmac, json, math, os, re, sys, time, urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from schemas.netark_dlp_core import normalize_and_deobfuscate  # noqa: E402

XPIA_HEURISTIC_RE = re.compile(
    r"(?i)(?:ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|"
    r"system\s+override\s*:|you\s+are\s+now\s+in\s+developer\s+mode|"
    r"<\s*(?:system|admin_override|tool_injection)\s*>|exfiltrate\s+all\s+credentials)"
)
LICENSE_SIGNING_DOMAIN = b"NETARK-ENTERPRISE-LICENSE-V1"
DEFAULT_ONNX_CACHE_DIR = Path.home() / ".cache" / "netark" / "models" / "Llama-Prompt-Guard-2-22M-onnx"


class GuardModelSlot:
    """Abstract base interface for pluggable local/intranet AI security model slots."""
    slot_name, tier, active_backend = "base", 0, "noop"
    def is_loaded(self) -> bool: return False
    def inspect(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"allowed": True, "tier": self.tier, "backend": self.active_backend, "score": 0.0}


class Tier1ClassifierSlot(GuardModelSlot):
    """Tier 1 (Llama-Prompt-Guard-2-22M ONNX) slot with automatic cache discovery & 0-VRAM fallback."""
    slot_name, tier = "tier1_classifier", 1

    def __init__(self, onnx_path: Optional[str] = None) -> None:
        env_path = onnx_path if onnx_path is not None else os.environ.get("NETARK_TIER1_ONNX_PATH", "").strip()
        if not env_path:
            for candidate in ("model.onnx", "model.quant.onnx"):
                if (DEFAULT_ONNX_CACHE_DIR / candidate).exists():
                    env_path = str(DEFAULT_ONNX_CACHE_DIR / candidate)
                    break
        self.onnx_path, self._session, self._tokenizer, self.active_backend = env_path, None, None, "noop_heuristic_slot"
        if self.onnx_path and Path(self.onnx_path).exists():
            try:
                import onnxruntime as ort  # type: ignore
                from tokenizers import Tokenizer  # type: ignore
                model_file = Path(self.onnx_path)
                tok_file = model_file.parent / "tokenizer.json"
                if tok_file.exists():
                    self._tokenizer = Tokenizer.from_file(str(tok_file))
                    self._tokenizer.no_padding()
                    self._tokenizer.enable_truncation(max_length=512)
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 4
                self._session = ort.InferenceSession(str(model_file), sess_options=opts, providers=["CPUExecutionProvider"])
                self.active_backend = "onnx_cpu_runtime"
            except Exception:
                self._session, self._tokenizer = None, None

    def is_loaded(self) -> bool: return self._session is not None

    def _run_onnx_score(self, text: str) -> Optional[float]:
        if self._session is None or self._tokenizer is None: return None
        try:
            import numpy as np  # type: ignore
            enc = self._tokenizer.encode(text[:2048])
            input_ids, attention_mask = np.array([enc.ids], dtype=np.int64), np.array([enc.attention_mask], dtype=np.int64)
            in_names = {inp.name for inp in self._session.get_inputs()}
            feed: Dict[str, Any] = {"input_ids": input_ids}
            if "attention_mask" in in_names: feed["attention_mask"] = attention_mask
            if "token_type_ids" in in_names: feed["token_type_ids"] = np.zeros_like(input_ids)
            logits = self._session.run(None, feed)[0][0]
            max_l = float(max(logits))
            exps = [math.exp(float(x) - max_l) for x in logits]
            return exps[-1] / sum(exps)
        except Exception:
            return None

    def inspect(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        t_start = time.perf_counter()
        deob = normalize_and_deobfuscate(text)
        flat = deob["flattened_text"]
        match = XPIA_HEURISTIC_RE.search(flat)
        if match:
            return {"allowed": False, "tier": 1, "backend": self.active_backend, "code": "SEC-XPIA-TIER1", "score": 0.99, "latency_ms": round((time.perf_counter() - t_start) * 1000, 2), "reason": f"Tier 1 blocked XPIA signature: '{match.group(0)[:48]}'"}
        onnx_score = self._run_onnx_score(flat)
        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
        if onnx_score is not None:
            if onnx_score >= 0.85:
                return {"allowed": False, "tier": 1, "backend": self.active_backend, "code": "SEC-ONNX-PROMPT-GUARD", "score": round(onnx_score, 4), "latency_ms": latency_ms, "reason": f"Llama-Prompt-Guard-2-22M flagged semantic injection (score={onnx_score:.4f})."}
            return {"allowed": True, "tier": 1, "backend": self.active_backend, "code": "PASS", "score": round(onnx_score, 4), "latency_ms": latency_ms}
        return {"allowed": True, "tier": 1, "backend": self.active_backend, "code": "PASS", "score": 0.01, "latency_ms": latency_ms}


class Tier2SemanticSlot(GuardModelSlot):
    """Tier 2 (Granite-Guardian / Llama-Guard) slot with 0-VRAM EmptyPassThroughSlot default."""
    slot_name, tier = "tier2_semantic_guardian", 2

    def __init__(self, endpoint: Optional[str] = None, model_name: Optional[str] = None) -> None:
        self.endpoint = (endpoint if endpoint is not None else os.environ.get("NETARK_TIER2_ENDPOINT", "")).strip()
        self.model_name = model_name or os.environ.get("NETARK_TIER2_MODEL", "ibm-granite/granite-guardian-3.2-3b-a800m")
        self.active_backend = "openai_compatible_endpoint" if self.endpoint else "empty_passthrough_slot"

    def is_loaded(self) -> bool:
        return bool(self.endpoint)

    def inspect(self, text: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.endpoint:
            return {"allowed": True, "tier": 2, "backend": self.active_backend, "code": "PASS_EMPTY_SLOT", "score": 0.0}
        try:
            payload = json.dumps({"model": self.model_name, "messages": [{"role": "user", "content": text[:2000]}], "max_tokens": 16, "temperature": 0.0}).encode("utf-8")
            req = urllib.request.Request(self.endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                reply = str(json.loads(resp.read().decode("utf-8")).get("choices", [{}])[0].get("message", {}).get("content", "")).strip().lower()
                if reply.startswith("unsafe") or "yes" in reply[:8]:
                    return {"allowed": False, "tier": 2, "backend": self.active_backend, "code": "SEC-SEMANTIC-TIER2", "score": 0.95, "reason": "Tier 2 flagged unsafe tool intent."}
        except Exception as exc:
            return {"allowed": True, "tier": 2, "backend": f"{self.active_backend}_fallback", "code": "PASS_FALLBACK", "note": str(exc)}
        return {"allowed": True, "tier": 2, "backend": self.active_backend, "code": "PASS", "score": 0.05}


def generate_offline_license_token(org: str, exp: str = "2099-12-31", secret: str = "") -> str:
    payload_bytes = json.dumps({"org": org, "tier": "enterprise", "exp": exp}, separators=(",", ":")).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signing_key = (secret or os.environ.get("NETARK_LICENSE_VERIFY_KEY", "")).encode("utf-8") or LICENSE_SIGNING_DOMAIN
    sig = hmac.new(signing_key, b64_payload.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return f"NETARK-ENT-V1.{b64_payload}.{sig}"


def verify_enterprise_license(license_key: Optional[str] = None) -> Dict[str, Any]:
    raw = license_key if license_key is not None else os.environ.get("NETARK_LICENSE_KEY", "")
    key = raw.strip() if isinstance(raw, str) else ""
    if not key or "${" in key:
        return {"tier": "community", "valid": True, "org": "community_user", "dlp_redaction": False, "signed_audit": False}
    invalid = {"tier": "community", "valid": False, "org": "invalid_key_fallback", "dlp_redaction": False, "signed_audit": False}
    parts = key.split(".")
    if len(parts) != 3 or parts[0] not in {"NETARK-ENT-V1", "PRISM-ENT-V1"}: return invalid
    b64_payload, provided_sig = parts[1], parts[2]
    signing_key = os.environ.get("NETARK_LICENSE_VERIFY_KEY", "").encode("utf-8") or LICENSE_SIGNING_DOMAIN
    try:
        expected_sig = hmac.new(signing_key, b64_payload.encode("ascii"), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(provided_sig, expected_sig): return invalid
        meta = json.loads(base64.urlsafe_b64decode((b64_payload + "=" * (-len(b64_payload) % 4)).encode("ascii")).decode("utf-8"))
        if not isinstance(meta, dict): return invalid
        raw_exp = meta.get("exp")
        exp = "2099-12-31" if raw_exp is None else str(raw_exp).strip()
        time.strptime(exp, "%Y-%m-%d")
    except (ValueError, TypeError, UnicodeError):
        return invalid
    org = str(meta.get("org") or "enterprise_org")
    if exp < time.strftime("%Y-%m-%d", time.gmtime()):
        return {"tier": "community", "valid": False, "expired": True, "exp": exp, "org": org, "dlp_redaction": False, "signed_audit": False}
    return {"tier": "enterprise", "valid": True, "org": org, "exp": exp, "dlp_redaction": True, "signed_audit": True}


def _resolve_audit_path(cwd: Optional[str] = None) -> Path:
    if (env_dir := os.environ.get("PI_CODING_AGENT_DIR")):
        return Path(env_dir) / "audit" / "soc2_audit.jsonl"
    base = Path(cwd).resolve() if cwd else ROOT_DIR
    brain_sub = ".agents" if (base / ".agents").exists() and not (base / ".netark" / "enterprise-policy.json").is_file() else (".pi" if (base / ".pi").exists() and not (base / ".netark" / "enterprise-policy.json").is_file() else ".netark")
    return base / brain_sub / "audit" / "soc2_audit.jsonl"


def append_signed_audit_log(event: Dict[str, Any], audit_path: Optional[str] = None, signing_secret: Optional[str] = None, cwd: Optional[str] = None) -> Dict[str, Any]:
    target = Path(audit_path) if audit_path else _resolve_audit_path(cwd)
    target.parent.mkdir(parents=True, exist_ok=True)
    prev_hash = "0" * 64
    if target.exists():
        try:
            lines = [ln.strip() for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if lines:
                prev_hash = json.loads(lines[-1]).get("entry_signature", prev_hash)
        except Exception:  # noqa: silent-except
            pass
    record: Dict[str, Any] = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, "prev_hash": prev_hash}
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    secret_bytes = (signing_secret or os.environ.get("NETARK_AUDIT_SIGNING_KEY", "netark-soc2-local-key")).encode("utf-8")
    record["entry_signature"] = hmac.new(secret_bytes, canonical, hashlib.sha256).hexdigest()
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
