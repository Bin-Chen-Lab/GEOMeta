from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from .json_safety import safe_json_loads_with_repair
from .token_budget import TokenBudget, check_messages_token_budget
from .llm_client import BaseLLM, make_llm_from_config


# -------------------------
# Small helpers
# -------------------------
def _s(x) -> str:
    """Safe stringify + strip for pandas values."""
    if x is None:
        return "NA"
    try:
        if isinstance(x, float) and x != x:
            return "NA"
    except Exception:
        pass
    v = str(x).strip()
    return "NA" if v.lower() in {"", "nan", "none"} else v


def _chunk(xs: List[str], n: int) -> List[List[str]]:
    return [xs[i:i + n] for i in range(0, len(xs), n)]


def _load_json(path: Path) -> Dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_parquet_kv(path: Path, mapping: Dict[str, Any]) -> None:
    rows = []
    for k, v in mapping.items():
        if isinstance(v, dict):
            row = {"raw": k}
            row.update(v)
            rows.append(row)
        else:
            rows.append({"raw": k, "mapped": v})
    pd.DataFrame(rows).to_parquet(path, index=False)


# -------------------------
# Prompt loading / resolution
# -------------------------
def read_prompt_file(prompt_path: str | Path) -> str:
    """Read prompt text from .md, .txt, or .docx files.

    Stage 2 prompts are distributed as Markdown files in the public repository,
    but .docx support is retained for backward compatibility with older runs.
    """
    path = Path(prompt_path)
    suffix = path.suffix.lower()

    if suffix in {".md", ".txt"}:
        return path.read_text(encoding="utf-8").strip()

    if suffix == ".docx":
        from docx import Document

        doc = Document(str(path))
        paras = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(paras).strip()

    raise ValueError(f"Unsupported prompt file type: {path}")


# Backward-compatible alias used by older helper code.
read_docx_prompt = read_prompt_file


def resolve_latest_prompt(prompt_dir: str, include_regex: str, exclude_regex: Optional[str] = None) -> str:
    pdir = Path(prompt_dir)
    if not pdir.exists():
        raise FileNotFoundError(f"Prompt directory not found: {pdir}")

    inc = re.compile(include_regex, flags=re.IGNORECASE)
    exc = re.compile(exclude_regex, flags=re.IGNORECASE) if exclude_regex else None

    candidates = []
    for fp in pdir.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in {".md", ".txt", ".docx"}:
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

    # Choose most recently modified among matches
    candidates = sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True)
    return str(candidates[0])


POST_PATTERNS = {
    "Seq_Type": (r"post[_\-]?sequencetype", None),
    "Organism": (r"post[_\-]?organism", None),
    "Strain": (r"post[_\-]?strain", None),
    "Genotype": (r"post[_\-]?genotype", None),
    "RNA_Source": (r"post[_\-]?rnasource", None),
    "Tissue": (r"post[_\-]?tissue", None),
    "Experimental_Setting": (r"post[_\-]?experimentsetting", None),
    "Model_Type": (r"post[_\-]?modeltype", None),
    "Disease": (r"post[_\-]?disease", None),
    "Pert": (r"post[_\-]?pert(?:\.md|\.txt|\.docx)?$", r"pertdose|pertfreq|pertduration"),
    "Pert_Dose": (r"post[_\-]?pertdose", None),
    "Pert_Freq": (r"post[_\-]?pertfreq", None),
    "Pert_Duration": (r"post[_\-]?pertduration", None),
    "Route_Admin": (r"post[_\-]?(routeadmin|roa)", None),
    "Specimen_Type": (r"post[_\-]?specimentype", None),
    "Race": (r"post[_\-]?race", None),
    "Ethnicity": (r"post[_\-]?ethnicity", None),
    "Age": (r"post[_\-]?age", None),
    "Sex": (r"post[_\-]?sex", None),
    "Timepoint": (r"post[_\-]?timepoint", None),
    "Outcome": (r"post[_\-]?outcome", None),
}

INFER_PATTERNS = {
    "Sex_from_Tissue": (r"infer[_\-]?sex[_\-]?from[_\-]?tissue", None),
    "Pert_Type_from_Pert": (
        r"infer[_\-]?(perturbation[_\-]?type|pert[_\-]?type)",
        None,
    ),
    "AgeGroup_from_Age": (
        r"derive[_\-]?agegroup[_\-]?from[_\-]?age",
        None,
    ),
}

def _resolve_post_prompt(post_prompt_dir: Path, field: str) -> str:
    inc, exc = POST_PATTERNS[field]
    return resolve_latest_prompt(str(post_prompt_dir), inc, exc)


def _resolve_infer_prompt(post_prompt_dir: Path, task: str) -> str:
    inc, exc = INFER_PATTERNS[task]
    return resolve_latest_prompt(str(post_prompt_dir), inc, exc)


# -------------------------
# Stage2 schema
# -------------------------
PAIR_FIELDS = [
    "Seq_Type",
    "Organism",
    "Strain",
    "Genotype",
    "RNA_Library",
    "RNA_Source",
    "Tissue",
    "Experimental_Setting",
    "Model_Type",
    "Disease",
    "GSE_Pert",
    "GSM_Pert",
    "Pert",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
    "Specimen_Type",
    "Race",
    "Ethnicity",
    "Age",
    "Sex",
    "Timepoint",
    "Outcome",
]

POSTPROCESS_FIELDS = [
    "Seq_Type",
    "Organism",
    "Strain",
    "Genotype",
    "RNA_Source",
    "Tissue",
    "Experimental_Setting",
    "Model_Type",
    "Disease",
    "Pert",
    "Pert_Dose",
    "Pert_Freq",
    "Pert_Duration",
    "Route_Admin",
    "Specimen_Type",
    "Race",
    "Ethnicity",
    "Age",
    "Timepoint",
    "Outcome",
]


STRICT_POSTPROCESS_SYSTEM_WRAPPER = (
    "You are a strict post-processing normalizer.\n"
    "Return STRICT JSON ONLY. No markdown. No commentary.\n"
    'INPUT JSON: {"field_name": <str>, "values": [<str>, ...]}\n'
    'OUTPUT JSON: {"field_name": <str>, "mappings": [{"raw":<str>,"post":<str>}, ...]}\n'
    "CRITICAL RULES:\n"
    "- The mappings array MUST have exactly the same length as values.\n"
    "- Include EVERY input value exactly once.\n"
    "- Preserve the same order as input values.\n"
    "- If no change is needed, set post=raw.\n"
)

STRICT_INFER_SYSTEM_WRAPPER = (
    "You are a strict inference utility.\n"
    "Return STRICT JSON ONLY. No markdown. No commentary.\n"
    'INPUT JSON: {"task": <str>, "values": [<str>, ...]}\n'
    'OUTPUT JSON: {"task": <str>, "mappings": [{"raw":<str>,"inferred":<str>}, ...]}\n'
    "CRITICAL RULES:\n"
    "- The mappings array MUST have exactly the same length as values.\n"
    "- Include EVERY input value exactly once.\n"
    "- Preserve the same order as input values.\n"
)


# -------------------------
# LLM mapping builders
# -------------------------
def _build_mapping_post(
    llm: BaseLLM,
    values: List[str],
    field: str,
    prompt_path: str,
    cache_json_path: Path,
    cache_parquet_path: Path,
    debug_dir: Path,
    batch_size: int,
    cfg=None,
) -> Dict[str, str]:
    cache: Dict[str, str] = _load_json(cache_json_path)
    need = [v for v in values if v not in cache]
    if not need:
        return cache

    prompt_text = read_docx_prompt(prompt_path)
    field_batch = batch_size
    if field in {"RNA_Source", "Tissue", "Disease", "Pert"}:
        field_batch = min(field_batch, 15)

    def call_once(chunk_vals: List[str], tag: str) -> Dict[str, str]:
        payload = {"field_name": field, "values": chunk_vals}
        messages = [
            {"role": "system", "content": STRICT_POSTPROCESS_SYSTEM_WRAPPER + "\n\n" + prompt_text},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        check_messages_token_budget(
            messages,
            budget=TokenBudget.from_config(cfg),
            context_label=f"Stage2 postprocess field={field} tag={tag}",
            action=str(getattr(cfg, "llm_token_budget_action", "raise")) if cfg is not None else "raise",
        )
        
        txt = llm.chat(messages, temperature=0.0)
        out = safe_json_loads_with_repair(
            txt,
            debug_dir=str(debug_dir),
            debug_tag=f"POST_{field}_{tag}",
            llm_chat_fn=lambda msgs, temperature=0.0: llm.chat(msgs, temperature=temperature),
        )
        rows = out.get("mappings", [])
        out_map: Dict[str, str] = {}
        for r in rows:
            raw = _s(r.get("raw"))
            post = _s(r.get("post"))
            if raw not in {"NA", ""}:
                out_map[raw] = post if post not in {"NA", ""} else raw
        return out_map

    for bi, chunk_vals in enumerate(_chunk(need, field_batch)):
        out_map = call_once(chunk_vals, f"{bi}_A")
        missing = [v for v in chunk_vals if v not in out_map]

        if missing:
            for ri, miss_chunk in enumerate(_chunk(missing, min(10, field_batch))):
                out_map.update(call_once(miss_chunk, f"{bi}_R{ri}"))

            still_missing = [v for v in chunk_vals if v not in out_map]
            for v in still_missing:
                out_map[v] = v

        cache.update(out_map)
        _save_json(cache_json_path, cache)
        _save_parquet_kv(cache_parquet_path, cache)

    return cache


def _build_mapping_infer(
    llm: BaseLLM,
    values: List[str],
    task: str,
    prompt_path: str,
    cache_json_path: Path,
    cache_parquet_path: Path,
    debug_dir: Path,
    batch_size: int,
    cfg=None,
) -> Dict[str, str]:
    cache: Dict[str, str] = _load_json(cache_json_path)
    need = [v for v in values if v not in cache]
    if not need:
        return cache

    prompt_text = read_docx_prompt(prompt_path)

    def call_once(chunk_vals: List[str], tag: str) -> Dict[str, str]:
        payload = {"task": task, "values": chunk_vals}
        messages = [
            {"role": "system", "content": STRICT_INFER_SYSTEM_WRAPPER + "\n\n" + prompt_text},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        check_messages_token_budget(
            messages,
            budget=TokenBudget.from_config(cfg),
            context_label=f"Stage2 inference task={task} tag={tag}",
            action=str(getattr(cfg, "llm_token_budget_action", "raise")) if cfg is not None else "raise",
        )

        txt = llm.chat(messages, temperature=0.0)
        out = safe_json_loads_with_repair(
            txt,
            debug_dir=str(debug_dir),
            debug_tag=f"INFER_{task}_{tag}",
            llm_chat_fn=lambda msgs, temperature=0.0: llm.chat(msgs, temperature=temperature),
        )
        rows = out.get("mappings", [])
        out_map: Dict[str, str] = {}
        for r in rows:
            raw = _s(r.get("raw"))
            inf = _s(r.get("inferred"))
            if raw not in {"NA", ""}:
                out_map[raw] = inf if inf not in {"", "NA"} else "NA"
        return out_map

    for bi, chunk_vals in enumerate(_chunk(need, batch_size)):
        out_map = call_once(chunk_vals, f"{bi}_A")
        missing = [v for v in chunk_vals if v not in out_map]

        if missing:
            for ri, miss_chunk in enumerate(_chunk(missing, min(10, batch_size))):
                out_map.update(call_once(miss_chunk, f"{bi}_R{ri}"))

            still_missing = [v for v in chunk_vals if v not in out_map]
            for v in still_missing:
                out_map[v] = "NA"

        cache.update(out_map)
        _save_json(cache_json_path, cache)
        _save_parquet_kv(cache_parquet_path, cache)

    return cache


# -------------------------
# Core Stage2 helpers
# -------------------------


def _norm_stage2_text(x) -> str:
    return "" if x is None else str(x).strip()


def _normalize_disease_no_disease_state(x) -> str | None:
    """
    Canonical GEOMeta disease labels for non-disease states.

    Returns canonical label when x is a recognized non-disease state;
    otherwise returns None.
    """
    v = _norm_stage2_text(x)
    key = v.casefold()

    normal_like = {
        "normal",
        "healthy",
        "healthy control",
        "control healthy",
        "disease-free",
        "non-diseased",
        "non diseased",
        "no disease",
    }

    adjacent_normal_like = {
        "adjacent normal",
        "adjacent non-tumor",
        "adjacent non tumor",
        "adjacent nontumor",
        "paracancerous",
        "paired normal",
        "matched normal",
    }

    no_disease_mentioned_like = {
        "no disease mentioned",
        "no disease information",
        "not mentioned",
    }

    if key in normal_like:
        return "Normal"

    if key in adjacent_normal_like:
        return "Adjacent Normal"

    if key in no_disease_mentioned_like:
        return "No Disease Mentioned"

    return None


def enforce_stage2_disease_no_disease_states(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stage 2 safeguard:
    preserve GEOMeta canonical non-disease labels in Disease_Post.

    Critical rule:
      Disease_Pre == Normal must remain Disease_Post == Normal.
    """
    df = df.copy()

    if "Disease_Pre" not in df.columns or "Disease_Post" not in df.columns:
        return df

    for idx in df.index:
        pre_val = _norm_stage2_text(df.at[idx, "Disease_Pre"])
        post_val = _norm_stage2_text(df.at[idx, "Disease_Post"])

        pre_canon = _normalize_disease_no_disease_state(pre_val)
        post_canon = _normalize_disease_no_disease_state(post_val)

        # Prefer Disease_Pre when it is already one of the canonical labels.
        if pre_canon is not None:
            df.at[idx, "Disease_Post"] = pre_canon

        # Also clean post-processing outputs such as Healthy -> Normal.
        elif post_canon is not None:
            df.at[idx, "Disease_Post"] = post_canon

    return df


def _apply_standard_postprocessing(
    cfg,
    llm: BaseLLM,
    df: pd.DataFrame,
    fields_to_process: Optional[Set[str]] = None,
) -> pd.DataFrame:
    """
    Applies field-specific postprocessing to df in place.
    fields_to_process:
      - None => run full pass
      - set([...]) => rerun only these fields
    """
    post_dir = Path(cfg.post_prompt_dir)
    map_dir = Path(cfg.mapping_cache_dir)
    debug_dir = Path(cfg.debug_dir)
    map_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    if fields_to_process is None:
        process_fields = list(POSTPROCESS_FIELDS)
    else:
        process_fields = [f for f in POSTPROCESS_FIELDS if f in fields_to_process]

    for field in process_fields:
        pre_col = f"{field}_Pre"
        post_col = f"{field}_Post"

        vals = df[pre_col].map(_s).tolist()
        uniq = sorted({v for v in vals if v not in {"NA", "Unknown"}})

        if len(uniq) == 0:
            df[post_col] = df[pre_col]
            print(f"[Stage2 POST] {field}: uniq=0 (copy Pre->Post)")
            continue

        prompt_path = _resolve_post_prompt(post_dir, field)
        print(f"[Stage2 POST] {field}: uniq={len(uniq)} prompt={Path(prompt_path).name}")

        mapping = _build_mapping_post(
            llm=llm,
            values=uniq,
            field=field,
            prompt_path=prompt_path,
            cache_json_path=map_dir / f"{field}_Pre_to_Post.json",
            cache_parquet_path=map_dir / f"{field}_Pre_to_Post.parquet",
            debug_dir=debug_dir,
            batch_size=cfg.term_batch_size,
            cfg=cfg,
        )

        def apply_map(x: str) -> str:
            x = _s(x)
            if x in {"NA", "Unknown"}:
                return x
            return mapping.get(x, x)

        df[post_col] = df[pre_col].map(apply_map)
        if field == "Disease":
            df = enforce_stage2_disease_no_disease_states(df)

    return df


def _apply_sex_logic(cfg, llm: BaseLLM, df: pd.DataFrame) -> pd.DataFrame:
    """
    Infer sex from Tissue_Post only when Sex_Pre is missing/NA/Unknown.
    Then postprocess Sex_Base into Sex_Post.
    """
    post_dir = Path(cfg.post_prompt_dir)
    map_dir = Path(cfg.mapping_cache_dir)
    debug_dir = Path(cfg.debug_dir)
    map_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    infer_prompt = _resolve_infer_prompt(post_dir, "Sex_from_Tissue")

    missing_sex_mask = df["Sex_Pre"].map(_s).isin({"NA", "Unknown", ""})
    org_vals = df.loc[missing_sex_mask, "Tissue_Post"].map(_s).tolist()
    org_uniq = sorted({v for v in org_vals if v not in {"NA", "Unknown"}})

    print(f"[Stage2 INFER] Sex_from_Tissue: uniq_org={len(org_uniq)} prompt={Path(infer_prompt).name}")

    org_to_sex = _build_mapping_infer(
        llm=llm,
        values=org_uniq,
        task="Sex_from_Tissue",
        prompt_path=infer_prompt,
        cache_json_path=map_dir / "Sex_from_TissuePost.json",
        cache_parquet_path=map_dir / "Sex_from_TissuePost.parquet",
        debug_dir=debug_dir,
        batch_size=max(cfg.term_batch_size, 50),
        cfg=cfg,
    )

    # Only infer for rows where Sex_Pre is missing
    df["Sex_Inferred_from_Tissue"] = "NA"
    df.loc[missing_sex_mask, "Sex_Inferred_from_Tissue"] = df.loc[missing_sex_mask, "Tissue_Post"].map(
        lambda x: org_to_sex.get(_s(x), "NA")
    )

    def sex_base(row) -> str:
        pre = _s(row.get("Sex_Pre"))
        inf = _s(row.get("Sex_Inferred_from_Tissue"))
        if pre in {"NA", "Unknown", ""} and inf in {"Male", "Female"}:
            return inf
        return pre if pre else "NA"

    df["Sex_Base"] = df.apply(sex_base, axis=1)

    sex_post_prompt = _resolve_post_prompt(post_dir, "Sex")
    sex_vals = df["Sex_Base"].map(_s).tolist()
    sex_uniq = sorted({v for v in sex_vals if v not in {"NA", "Unknown"}})

    print(f"[Stage2 POST] Sex: uniq={len(sex_uniq)} prompt={Path(sex_post_prompt).name}")

    sex_map = _build_mapping_post(
        llm=llm,
        values=sex_uniq,
        field="Sex",
        prompt_path=sex_post_prompt,
        cache_json_path=map_dir / "Sex_Base_to_Post.json",
        cache_parquet_path=map_dir / "Sex_Base_to_Post.parquet",
        debug_dir=debug_dir,
        batch_size=cfg.term_batch_size,
        cfg=cfg,
    )

    def sex_post(x: str) -> str:
        x = _s(x)
        if x in {"NA", "Unknown"}:
            return "NA"
        out = sex_map.get(x, x)
        if out in {"Others", "Other", "Both"}:
            return "Mixed"
        if out in {"Neutral", "Embryo"}:
            return "NA"
        return out

    df["Sex_Post"] = df["Sex_Base"].map(sex_post)
    return df


def _apply_pert_type_logic(cfg, llm: BaseLLM, df: pd.DataFrame) -> pd.DataFrame:
    post_dir = Path(cfg.post_prompt_dir)
    map_dir = Path(cfg.mapping_cache_dir)
    debug_dir = Path(cfg.debug_dir)
    map_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    pert_type_prompt = _resolve_infer_prompt(post_dir, "Pert_Type_from_Pert")
    pert_vals = df["Pert_Post"].map(_s).tolist()
    pert_uniq = sorted({v for v in pert_vals if v not in {"NA", "Unknown"}})

    print(f"[Stage2 INFER] Pert_Type_from_Pert: uniq={len(pert_uniq)} prompt={Path(pert_type_prompt).name}")

    pert_to_type = _build_mapping_infer(
        llm=llm,
        values=pert_uniq,
        task="Pert_Type_from_Pert",
        prompt_path=pert_type_prompt,
        cache_json_path=map_dir / "PertPost_to_PertType.json",
        cache_parquet_path=map_dir / "PertPost_to_PertType.parquet",
        debug_dir=debug_dir,
        batch_size=max(cfg.term_batch_size, 50),
        cfg=cfg,
    )

    df["Pert_Type"] = df["Pert_Post"].map(lambda x: pert_to_type.get(_s(x), "NA"))
    return df

def _apply_age_group_logic(
    cfg,
    llm: BaseLLM,
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Derive Age_Group_Post from standardized Age_Post using the
    controlled-inference prompt derive_agegroup_from_age.md.

    Age_Group is derived only from Age_Post. The inference is performed on
    unique standardized age terms and propagated back to all matching rows.
    """
    post_dir = Path(cfg.post_prompt_dir)
    map_dir = Path(cfg.mapping_cache_dir)
    debug_dir = Path(cfg.debug_dir)

    map_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    if "Age_Post" not in df.columns:
        df["Age_Group_Post"] = "NA"
        return df

    infer_prompt = _resolve_infer_prompt(
        post_dir,
        "AgeGroup_from_Age",
    )

    age_vals = df["Age_Post"].map(_s).tolist()
    age_uniq = sorted(
        {
            v
            for v in age_vals
            if v not in {"NA", "Unknown", ""}
        }
    )

    print(
        f"[Stage2 INFER] AgeGroup_from_Age: "
        f"uniq={len(age_uniq)} "
        f"prompt={Path(infer_prompt).name}"
    )

    if not age_uniq:
        df["Age_Group_Post"] = "NA"
        return df

    age_to_group = _build_mapping_infer(
        llm=llm,
        values=age_uniq,
        task="AgeGroup_from_Age",
        prompt_path=infer_prompt,
        cache_json_path=map_dir / "AgePost_to_AgeGroup.json",
        cache_parquet_path=map_dir / "AgePost_to_AgeGroup.parquet",
        debug_dir=debug_dir,
        batch_size=max(cfg.term_batch_size, 50),
        cfg=cfg,
    )

    def derive_age_group(x: str) -> str:
        x = _s(x)

        if x in {"NA", "Unknown", ""}:
            return "NA"

        return age_to_group.get(x, "NA")

    df["Age_Group_Post"] = df["Age_Post"].map(derive_age_group)

    return df

def _normalize_disease_label_for_rule(x: Any) -> str:
    """Normalize disease labels for hard-coded post-processing safeguards."""
    v = _s(x)
    v = re.sub(r"\s*\((Extracted|Inferred)\)\s*$", "", v, flags=re.IGNORECASE).strip()
    v = re.sub(r"\s+", " ", v).strip().lower()
    return v


def _preserve_adjacent_normal_disease(df: pd.DataFrame) -> pd.DataFrame:
    """
    Disease safeguard:
    Adjacent Normal is not Healthy/Normal.

    If Stage 1 identified a sample as Adjacent Normal, Stage 2 should not
    standardize it to Healthy or Normal.
    """
    df = df.copy()

    if {"Disease_Pre", "Disease_Post"}.issubset(df.columns):
        adj_mask = df["Disease_Pre"].map(_normalize_disease_label_for_rule).eq("adjacent normal")
        df.loc[adj_mask, "Disease_Post"] = "Adjacent Normal"

    return df


def _build_stage2_output(df: pd.DataFrame) -> pd.DataFrame:
    out_cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Pre", "Seq_Type_Post",
        "Organism_Pre", "Organism_Post",
        "Strain_Pre", "Strain_Post",
        "Genotype_Pre", "Genotype_Post",
        "RNA_Library_Pre", "RNA_Library_Post",
        "RNA_Source_Pre", "RNA_Source_Post",
        "Tissue_Pre", "Tissue_Post",
        "Experimental_Setting_Pre", "Experimental_Setting_Post",
        "Model_Type_Pre", "Model_Type_Post",
        "Disease_Pre", "Disease_Post",
        "GSE_Pert_Pre", "GSE_Pert_Post",
        "GSM_Pert_Pre", "GSM_Pert_Post",
        "Pert_Pre", "Pert_Post",
        "Pert_Type",
        "Pert_Dose_Pre", "Pert_Dose_Post",
        "Pert_Freq_Pre", "Pert_Freq_Post",
        "Pert_Duration_Pre", "Pert_Duration_Post",
        "Route_Admin_Pre", "Route_Admin_Post",
        "SampleType",
        "Specimen_Type_Pre", "Specimen_Type_Post",
        "Race_Pre", "Race_Post",
        "Ethnicity_Pre", "Ethnicity_Post",
        "Age_Pre", "Age_Post",
        "Age_Group_Post",
        "Sex_Pre", "Sex_Inferred_from_Tissue", "Sex_Post",
        "Timepoint_Pre", "Timepoint_Post",
        "Outcome_Pre", "Outcome_Post",
    ]

    for c in out_cols:
        if c not in df.columns:
            df[c] = "NA"

    return df.loc[:, out_cols].copy()

def _normalize_queue_field_name(raw_field: str) -> Optional[str]:
    rf = _s(raw_field)
    if rf in {"NA", ""}:
        return None

    # normalize common variants
    rf = rf.replace(" ", "")
    rf = rf.replace("_Post", "").replace("_Pre", "")

    aliases = {
        "SeqType": "Seq_Type",
        "Organism": "Organism",
        "Strain": "Strain",
        "Genotype": "Genotype",
        "RNALibrary": "RNA_Library",
        "RNASource": "RNA_Source",
        "Tissue": "Tissue",
        "ExperimentalSetting": "Experimental_Setting",
        "ModelType": "Model_Type",
        "Disease": "Disease",
        "GSEPert": "GSE_Pert",
        "GSMPert": "GSM_Pert",
        "Pert": "Pert",
        "PertDose": "Pert_Dose",
        "PertFreq": "Pert_Freq",
        "PertDuration": "Pert_Duration",
        "RouteAdmin": "Route_Admin",
        "SampleType": "SampleType",
        "SpecimenType": "Specimen_Type",
        "Race": "Race",
        "Ethnicity": "Ethnicity",
        "Age": "Age",
        "Age_Group": "Age_Group",
        "AgeGroup": "Age_Group",
        "Sex": "Sex",
        "Timepoint": "Timepoint",
        "Outcome": "Outcome",
        "PertTypefromPert": "Pert_Type",
        "PertType": "Pert_Type",
    }
    return aliases.get(rf, None)


# -------------------------
# Public Stage2 APIs
# -------------------------
def run_stage2_postprocessing(cfg, df_stage1: pd.DataFrame) -> pd.DataFrame:
    """
    Stage 2 pass 1:
      - creates paired Pre/Post columns
      - standardizes selected fields
      - derives Age_Group_Post from standardized Age_Post
      - infers Sex from Tissue_Post only when Sex_Pre is missing
      - infers Pert_Type from Pert_Post
      - keeps SampleType as a single column
      - saves paired Excel/Parquet outputs
    """
    cfg.validate_env()

    llm = make_llm_from_config(cfg)

    df = df_stage1.copy()

    # Create Pre/Post columns
    for f in PAIR_FIELDS:
        if f not in df.columns:
            df[f] = "NA"
        df[f"{f}_Pre"] = df[f].map(_s)
        df[f"{f}_Post"] = df[f"{f}_Pre"]

    # SampleType kept as single final field
    if "SampleType" not in df.columns:
        df["SampleType"] = "NA"
    else:
        df["SampleType"] = df["SampleType"].map(_s)

    # Fields copied only, not actively postprocessed
    for f in ["RNA_Library", "GSE_Pert", "GSM_Pert"]:
        df[f"{f}_Post"] = df[f"{f}_Pre"]

    df = _apply_standard_postprocessing(
        cfg,
        llm,
        df,
        fields_to_process=None,
    )

    df = _preserve_adjacent_normal_disease(df)

    df = _apply_age_group_logic(
        cfg,
        llm,
        df,
    )

    df = _apply_sex_logic(
        cfg,
        llm,
        df,
    )

    df = _apply_pert_type_logic(
        cfg,
        llm,
        df,
    )

    df_out = _build_stage2_output(df)

    out_xlsx = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_post.xlsx"
    out_parq = Path(cfg.outputs_dir) / f"{cfg.run_version}_stage2_post.parquet"
    df_out.to_excel(out_xlsx, index=False)
    df_out.to_parquet(out_parq, index=False)

    print("[SAVED] Stage2 post Excel:", out_xlsx)
    print("[SAVED] Stage2 post Parquet:", out_parq)
    print("Stage2 DONE rows:", df_out.shape)

    return df_out


def run_stage2_postprocessing_v2(
    cfg,
    df_stage1: pd.DataFrame,
    df_queue: Optional[pd.DataFrame] = None,
    run_pass1: bool = False,
    df_stage2_pass1: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Selective rerun executor for Stage2 review loop.

    Behavior:
      - If run_pass1=True or df_stage2_pass1 is None, first run full Stage2 pass1.
      - If queue is empty, return pass1 output unchanged.
      - Otherwise rerun only flagged fields on the affected GSM rows.

    For simplicity and stability, rerun is applied by:
      - reconstructing a working frame from df_stage1
      - applying the pass1 standardized values as baseline
      - recomputing only flagged fields
    """
    cfg.validate_env()

    llm = make_llm_from_config(cfg)

    if run_pass1 or df_stage2_pass1 is None:
        df_stage2_pass1 = run_stage2_postprocessing(cfg, df_stage1)

    if df_queue is None or df_queue.empty:
        return df_stage2_pass1.copy()

    # Figure out queue columns
    gsm_col = None
    for c in ["GSM_ID", "gsm_id", "Gsm_ID"]:
        if c in df_queue.columns:
            gsm_col = c
            break

    field_col = None
    for c in ["field_name", "Field", "field", "target_field", "Field_Name"]:
        if c in df_queue.columns:
            field_col = c
            break

    if gsm_col is None or field_col is None:
        print("[Stage2 RERUN] Queue missing GSM_ID/field columns; returning pass1 output unchanged.")
        return df_stage2_pass1.copy()

    affected_gsms = set(df_queue[gsm_col].astype(str).tolist())
    normalized_fields = {_normalize_queue_field_name(v) for v in df_queue[field_col].astype(str).tolist()}
    normalized_fields.discard(None)

    if not affected_gsms or not normalized_fields:
        print("[Stage2 RERUN] Queue empty after normalization; returning pass1 output unchanged.")
        return df_stage2_pass1.copy()

    # Rebuild a working df from Stage1
    df_work = df_stage1.copy()
    for f in PAIR_FIELDS:
        if f not in df_work.columns:
            df_work[f] = "NA"
        df_work[f"{f}_Pre"] = df_work[f].map(_s)
        df_work[f"{f}_Post"] = df_work[f"{f}_Pre"]

    if "SampleType" not in df_work.columns:
        df_work["SampleType"] = "NA"
    else:
        df_work["SampleType"] = df_work["SampleType"].map(_s)

    
    # Use pass1 output as the baseline for all Stage 2 output columns.
    # This preserves derived fields such as Pert_Type,
    # Age_Group_Post, and Sex_Inferred_from_Tissue.
    pass1_unique = (
        df_stage2_pass1
        .drop_duplicates(subset=["GSM_ID"])
        .set_index("GSM_ID", drop=False)
    )

    for c in df_stage2_pass1.columns:
        if c == "GSM_ID":
            continue

        lookup = pass1_unique[c].to_dict()
        baseline = df_work["GSM_ID"].map(lookup)

        if c not in df_work.columns:
            df_work[c] = baseline
        else:
            df_work[c] = baseline.where(
                baseline.notna(),
                df_work[c],
            )

    # Determine rows to rerun
    rerun_mask = df_work["GSM_ID"].astype(str).isin(affected_gsms)

    # Recompute flagged standard fields only on affected rows by rebuilding mappings globally
    standard_fields = {f for f in normalized_fields if f in POSTPROCESS_FIELDS}
    if standard_fields:
        df_subset = df_work.loc[rerun_mask].copy()
        for f in standard_fields:
            pre_col = f"{f}_Pre"
            post_col = f"{f}_Post"

            vals = df_subset[pre_col].map(_s).tolist()
            uniq = sorted({v for v in vals if v not in {"NA", "Unknown"}})
            if not uniq:
                continue

            prompt_path = _resolve_post_prompt(Path(cfg.post_prompt_dir), f)
            print(f"[Stage2 RERUN POST] {f}: uniq={len(uniq)} prompt={Path(prompt_path).name}")

            mapping = _build_mapping_post(
                llm=llm,
                values=uniq,
                field=f,
                prompt_path=prompt_path,
                cache_json_path=Path(cfg.mapping_cache_dir) / f"{f}_Pre_to_Post.json",
                cache_parquet_path=Path(cfg.mapping_cache_dir) / f"{f}_Pre_to_Post.parquet",
                debug_dir=Path(cfg.debug_dir),
                batch_size=cfg.term_batch_size,
                cfg=cfg,
            )

            def apply_map(x: str) -> str:
                x = _s(x)
                if x in {"NA", "Unknown"}:
                    return x
                return mapping.get(x, x)

            df_work.loc[rerun_mask, post_col] = df_work.loc[rerun_mask, pre_col].map(apply_map)

    # Disease safeguards after selective rerun.
    # Selective rerun can re-apply cached/LLM Disease mappings after the
    # full pass1 disease safeguard has already run, so enforce both rules here.
    df_work = enforce_stage2_disease_no_disease_states(df_work)
    df_work = _preserve_adjacent_normal_disease(df_work)

    # Always refresh Age_Group_Post from the current standardized Age_Post.
    df_work = _apply_age_group_logic(
        cfg,
        llm,
        df_work,
    )

    # Recompute Sex if flagged
    if "Sex" in normalized_fields:
        df_work = _apply_sex_logic(cfg, llm, df_work)

    # Recompute Pert_Type if flagged
    if "Pert_Type" in normalized_fields or "Pert" in normalized_fields:
        df_work = _apply_pert_type_logic(cfg, llm, df_work)

    df_out = _build_stage2_output(df_work)
    return df_out