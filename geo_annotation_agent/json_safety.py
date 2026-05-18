from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _extract_json_candidate(text: str) -> str:
    """
    Extract the largest plausible JSON object/array from model output.
    """
    if text is None:
        raise ValueError("Model returned None, expected JSON text.")

    s = str(text).strip()
    if not s:
        raise ValueError("Empty model output, expected JSON text.")

    # Remove fenced code blocks if present
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)

    # Prefer object
    obj_match = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if obj_match:
        return obj_match.group(0).strip()

    # Fallback to array
    arr_match = re.search(r"\[.*\]", s, flags=re.DOTALL)
    if arr_match:
        return arr_match.group(0).strip()

    return s


def _simple_repair_json_string(s: str) -> str:
    """
    Lightweight JSON cleanup only. Avoid over-aggressive rewriting.
    """
    repaired = s.strip()

    # Normalize smart quotes
    repaired = repaired.replace("“", '"').replace("”", '"')
    repaired = repaired.replace("‘", "'").replace("’", "'")

    # Remove trailing commas before } or ]
    repaired = re.sub(r",\s*}", "}", repaired)
    repaired = re.sub(r",\s*]", "]", repaired)

    # Remove leading junk before first { or [
    repaired = re.sub(r"^[^\{\[]*", "", repaired, flags=re.DOTALL)

    # Remove trailing junk after last } or ]
    repaired = re.sub(r"[^\}\]]*$", "", repaired, flags=re.DOTALL)

    return repaired


def _write_debug(debug_dir: Optional[str], debug_tag: str, raw_text: str, repaired_text: str) -> None:
    if not debug_dir:
        return

    p = Path(debug_dir)
    p.mkdir(parents=True, exist_ok=True)

    raw_fp = p / f"{debug_tag}_raw.txt"
    repaired_fp = p / f"{debug_tag}_repaired.json"

    raw_fp.write_text(str(raw_text), encoding="utf-8")
    repaired_fp.write_text(str(repaired_text), encoding="utf-8")


def _make_repair_messages(bad_text: str) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a strict JSON repair utility. "
                "Repair the user's malformed JSON into valid JSON only. "
                "Return JSON only. No markdown. No explanation."
            ),
        },
        {
            "role": "user",
            "content": bad_text,
        },
    ]


def safe_json_loads_with_repair(
    text: str,
    debug_dir: Optional[str] = None,
    debug_tag: str = "json_debug",
    llm_chat_fn: Optional[Callable[..., str]] = None,
) -> Any:
    """
    Parse model output as JSON with:
      1) direct parse
      2) lightweight local repair
      3) optional LLM repair fallback

    Returns parsed Python object.
    Raises ValueError if still not parseable.
    """
    raw_candidate = _extract_json_candidate(text)

    # Attempt 1: direct parse
    try:
        return json.loads(raw_candidate)
    except Exception:
        pass

    # Attempt 2: local repair
    repaired = _simple_repair_json_string(raw_candidate)
    try:
        obj = json.loads(repaired)
        _write_debug(debug_dir, debug_tag, text, repaired)
        return obj
    except Exception as e_local:
        local_err = e_local

    # Attempt 3: LLM repair fallback
    if llm_chat_fn is not None:
        try:
            repaired_text = llm_chat_fn(_make_repair_messages(raw_candidate), temperature=0.0)
            repaired_text = _extract_json_candidate(repaired_text)
            repaired_text = _simple_repair_json_string(repaired_text)
            obj = json.loads(repaired_text)
            _write_debug(debug_dir, debug_tag, text, repaired_text)
            return obj
        except Exception as e_llm:
            _write_debug(debug_dir, debug_tag, text, repaired)
            raise ValueError(
                f"Failed to parse JSON after local and LLM repair. "
                f"Local error: {repr(local_err)} | LLM repair error: {repr(e_llm)}"
            ) from e_llm

    _write_debug(debug_dir, debug_tag, text, repaired)
    raise ValueError(f"Failed to parse JSON after repair. Error: {repr(local_err)}")