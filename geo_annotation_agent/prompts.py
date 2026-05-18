from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from docx import Document


def read_docx_prompt(docx_path: str) -> str:
    """
    Read prompt text from a .docx file by concatenating non-empty paragraphs.
    """
    doc = Document(docx_path)
    paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n".join(paras).strip()


def resolve_latest_prompt(prompt_dir: str, include_regex: str, exclude_regex: Optional[str] = None) -> str:
    """
    Resolve the most recently modified .docx prompt file in prompt_dir
    matching include_regex and not matching exclude_regex.
    """
    pdir = Path(prompt_dir)
    if not pdir.exists():
        raise FileNotFoundError(f"Prompt directory not found: {pdir}")

    inc = re.compile(include_regex, flags=re.IGNORECASE)
    exc = re.compile(exclude_regex, flags=re.IGNORECASE) if exclude_regex else None

    candidates = []
    for fp in pdir.iterdir():
        if not fp.is_file():
            continue
        if fp.suffix.lower() != ".docx":
            continue
        name = fp.name
        if not inc.search(name):
            continue
        if exc and exc.search(name):
            continue
        candidates.append(fp)

    if not candidates:
        raise FileNotFoundError(
            f"No prompt matched include='{include_regex}' exclude='{exclude_regex}' in {prompt_dir}"
        )

    candidates = sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True)
    return str(candidates[0])