"""Pure-stdlib lightweight YAML frontmatter parser for NetArk schemas."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


def _yaml_val(raw: str) -> Any:
    """Parse a single YAML scalar or inline collection value."""
    v = raw.strip()
    if not v or v in ("null", "Null", "NULL", "~"): return None
    if v in ("true", "True", "TRUE"): return True
    if v in ("false", "False", "FALSE"): return False
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1].replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n") if v[0] == '"' else v[1:-1].replace("''", "'")
    if (v.startswith("[") and v.endswith("]")) or (v.startswith("{") and v.endswith("}")):
        try: return json.loads(v)
        except ValueError: return [_yaml_val(x) for x in v[1:-1].split(",") if x.strip()] if v[0] == "[" else v
    if re.fullmatch(r"-?\d+", v): return int(v)
    return float(v) if re.fullmatch(r"-?\d+\.\d+", v) else v


def _yaml_kv(text: str) -> Optional[Tuple[str, str]]:
    """Split a YAML key: value line respecting single and double quotes."""
    sq, dq = False, False
    for i, c in enumerate(text):
        if c == "'" and not dq: sq = not sq
        elif c == '"' and not sq and (i == 0 or text[i - 1] != "\\"): dq = not dq
        elif c == ":" and not sq and not dq and (i + 1 == len(text) or text[i + 1] == " "):
            return text[:i].strip().strip('"').strip("'"), text[i + 1 :].strip()
    return None


def _parse_simple_yaml(raw_fm: str) -> Any:
    """Parse lightweight YAML frontmatter into Python dicts, lists, and scalars."""
    if raw_fm.lstrip().startswith("{"): return json.loads(raw_fm)
    lines = [(len(ln) - len(ln.lstrip(" ")), ln.strip()) for ln in raw_fm.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    root: Dict[str, Any] = {}
    stack: List[Tuple[int, Any]] = [(-1, root)]
    for idx, (ind, s) in enumerate(lines):
        is_li = s.startswith("- ") or s == "-"
        while len(stack) > 1 and (ind < stack[-1][0] or (ind == stack[-1][0] and not (is_li and isinstance(stack[-1][1], list)))):
            stack.pop()
        cur = stack[-1][1]
        if is_li and isinstance(cur, list):
            rest = s[1:].strip()
            kv = _yaml_kv(rest) if rest else None
            if kv:
                item: Dict[str, Any] = {kv[0]: _yaml_val(kv[1]) if kv[1] else None}
                cur.append(item)
                stack.append((ind, item))
            else:
                cur.append(_yaml_val(rest) if rest else {})
                if not rest: stack.append((ind, cur[-1]))
        elif (kv := _yaml_kv(s)) and isinstance(cur, dict):
            if kv[1]: cur[kv[0]] = _yaml_val(kv[1])
            elif idx + 1 < len(lines) and (lines[idx + 1][0] > ind or (lines[idx + 1][0] == ind and lines[idx + 1][1].startswith("- "))):
                child: Any = [] if (lines[idx + 1][1].startswith("- ") or lines[idx + 1][1] == "-") else {}
                cur[kv[0]] = child
                stack.append((ind, child))
            else: cur[kv[0]] = None
    return root
