from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence

try:
    import tiktoken
except Exception:  # pragma: no cover - optional dependency fallback
    tiktoken = None


@dataclass
class TokenBudget:
    """Configuration for conservative LLM input-token checks."""

    model_input_limit: int = 272_000
    safe_input_limit: int = 240_000
    warning_input_limit: int = 180_000
    encoding_name: str = "o200k_base"

    @classmethod
    def from_config(cls, cfg: Any | None = None) -> "TokenBudget":
        if cfg is None:
            return cls()
        return cls(
            model_input_limit=int(getattr(cfg, "llm_model_input_token_limit", 272_000)),
            safe_input_limit=int(getattr(cfg, "llm_safe_input_token_limit", 240_000)),
            warning_input_limit=int(getattr(cfg, "llm_warning_input_token_limit", 180_000)),
            encoding_name=str(getattr(cfg, "llm_token_encoding", "o200k_base")),
        )


def get_encoding(encoding_name: str = "o200k_base"):
    if tiktoken is None:
        return None
    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception:
        # cl100k_base is widely available in older tiktoken installations.
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None


def estimate_tokens(text: Any, encoding_name: str = "o200k_base") -> int:
    """Estimate tokens for a text string with a conservative fallback."""
    text = "" if text is None else str(text)
    enc = get_encoding(encoding_name)
    if enc is None:
        # Biomedical metadata often has punctuation/IDs; 3.5 chars/token is conservative.
        return max(1, int(len(text) / 3.5))
    return len(enc.encode(text))


def estimate_messages_tokens(messages: Sequence[dict[str, Any]], encoding_name: str = "o200k_base") -> int:
    """
    Approximate chat-message input tokens.

    API-side accounting can differ slightly by model/provider, so GEOMeta uses this
    estimate with a safety margin rather than pushing to the exact model limit.
    """
    total = 0
    for msg in messages:
        total += 4  # chat wrapper overhead approximation
        total += estimate_tokens(msg.get("role", ""), encoding_name)
        total += estimate_tokens(msg.get("content", ""), encoding_name)
        # Count any additional fields conservatively.
        for k, v in msg.items():
            if k not in {"role", "content"}:
                total += estimate_tokens(k, encoding_name)
                total += estimate_tokens(json.dumps(v, ensure_ascii=False), encoding_name)
    total += 4
    return total


def split_gsm_info_blocks(gsm_info: Any) -> list[str]:
    """
    Split GSM_Info into complete GSM blocks.

    Supports GEOMeta Stage0 blocks starting with:
      ### GSM_START: GSM...
    and older/simple blocks starting with:
      GSM ID: GSM...
    """
    text = "" if gsm_info is None else str(gsm_info)
    if not text.strip():
        return []

    blocks = re.split(r"(?=###\s*GSM_START:\s*GSM\d+)", text, flags=re.IGNORECASE)
    blocks = [b.strip() for b in blocks if b and b.strip()]
    if len(blocks) > 1:
        return blocks

    blocks = re.split(r"(?=GSM ID:\s*GSM\d+)", text, flags=re.IGNORECASE)
    blocks = [b.strip() for b in blocks if b and b.strip()]
    return blocks if blocks else [text]


def extract_gsm_ids_from_text(text: Any) -> list[str]:
    text = "" if text is None else str(text)
    starts = re.findall(r"###\s*GSM_START:\s*(GSM\d+)", text, flags=re.IGNORECASE)
    if starts:
        return list(dict.fromkeys(starts))
    ids = re.findall(r"\bGSM\d+\b", text)
    return list(dict.fromkeys(ids))


def max_estimated_role_tokens(
    *,
    role_messages: Iterable[Sequence[dict[str, Any]]],
    budget: TokenBudget,
) -> int:
    vals = [estimate_messages_tokens(messages, budget.encoding_name) for messages in role_messages]
    return max(vals) if vals else 0


def check_messages_token_budget(
    messages: Sequence[dict[str, Any]],
    *,
    budget: TokenBudget,
    context_label: str = "LLM call",
    action: str = "raise",
) -> dict[str, Any]:
    """
    Check a message list against the configured token budget.

    action:
      - "raise": raise if estimated input exceeds model_input_limit
      - "warn": never raise, only report
    """
    est = estimate_messages_tokens(messages, budget.encoding_name)
    row = {
        "Context": context_label,
        "Estimated_Input_Tokens": int(est),
        "Warning_Input_Token_Limit": int(budget.warning_input_limit),
        "Safe_Input_Token_Limit": int(budget.safe_input_limit),
        "Model_Input_Token_Limit": int(budget.model_input_limit),
        "Within_Warning_Limit": bool(est <= budget.warning_input_limit),
        "Within_Safe_Limit": bool(est <= budget.safe_input_limit),
        "Within_Model_Limit": bool(est <= budget.model_input_limit),
    }
    if est > budget.model_input_limit and action == "raise":
        raise ValueError(
            f"{context_label} exceeds model input token limit: "
            f"estimated {est:,} > {budget.model_input_limit:,}. "
            "Split the GSM_Info chunk before calling the model."
        )
    return row


def pack_gsm_blocks_by_token_budget(
    *,
    gsm_info: Any,
    budget: TokenBudget,
    token_counter_for_candidate,
) -> list[dict[str, Any]]:
    """
    Pack complete GSM blocks into chunks using a caller-provided token counter.

    token_counter_for_candidate(candidate_gsm_info: str) -> int should estimate the
    actual LLM input tokens for the candidate text, including role prompts and GSE_Info.
    """
    blocks = split_gsm_info_blocks(gsm_info)
    if not blocks:
        return []

    chunks: list[dict[str, Any]] = []
    current: list[str] = []

    def flush_current() -> None:
        nonlocal current
        if current:
            text = "\n\n".join(current)
            chunks.append(
                {
                    "GSM_Info": text,
                    "GSM_IDs": extract_gsm_ids_from_text(text),
                    "Estimated_Max_Input_Tokens": int(token_counter_for_candidate(text)),
                    "Single_GSM_Block_Over_Safe_Limit": False,
                }
            )
            current = []

    for block in blocks:
        if not current:
            block_tokens = token_counter_for_candidate(block)
            if block_tokens > budget.safe_input_limit:
                chunks.append(
                    {
                        "GSM_Info": block,
                        "GSM_IDs": extract_gsm_ids_from_text(block),
                        "Estimated_Max_Input_Tokens": int(block_tokens),
                        "Single_GSM_Block_Over_Safe_Limit": True,
                    }
                )
            else:
                current = [block]
            continue

        candidate_blocks = current + [block]
        candidate_text = "\n\n".join(candidate_blocks)
        candidate_tokens = token_counter_for_candidate(candidate_text)
        if candidate_tokens <= budget.safe_input_limit:
            current = candidate_blocks
        else:
            flush_current()
            block_tokens = token_counter_for_candidate(block)
            if block_tokens > budget.safe_input_limit:
                chunks.append(
                    {
                        "GSM_Info": block,
                        "GSM_IDs": extract_gsm_ids_from_text(block),
                        "Estimated_Max_Input_Tokens": int(block_tokens),
                        "Single_GSM_Block_Over_Safe_Limit": True,
                    }
                )
            else:
                current = [block]

    flush_current()
    return chunks
