from __future__ import annotations

import json
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

from .json_safety import safe_json_loads_with_repair
from .llm_client import make_llm_from_config


# -------------------------
# Helpers
# -------------------------
def _s(x) -> str:
    if x is None:
        return "NA"
    try:
        if isinstance(x, float) and x != x:
            return "NA"
    except Exception:
        pass

    v = str(x).strip()
    return "NA" if v.lower() in {"", "nan", "none"} else v


def _blank(x) -> str:
    v = _s(x)
    return "" if v in {"NA", "Unknown"} else v

def blank_release_na(df_out: pd.DataFrame) -> pd.DataFrame:
    df_out = df_out.copy()
    return df_out.replace({"NA": "", "Unknown": ""})


def normalize_pubchem_cid(x: Any) -> str:
    """Return PubChem CID as integer-like text, preserving blanks.

    Examples:
    - 3345.0  -> 3345
    - 3345.00 -> 3345
    - 3345    -> 3345
    - blank/NA/Unknown -> ""
    """
    v = _blank(x)
    if not v:
        return ""

    v = str(v).strip()
    v = re.sub(r"^https?://pubchem\.ncbi\.nlm\.nih\.gov/compound/", "", v, flags=re.I)
    v = v.strip().strip("/")

    if re.fullmatch(r"\d+", v):
        return v

    try:
        d = Decimal(v)
    except (InvalidOperation, ValueError):
        return v

    if d == d.to_integral_value():
        return str(int(d))
    return v


def normalize_cid_columns(df_out: pd.DataFrame) -> pd.DataFrame:
    """Normalize PubChem CID columns without changing non-CID columns."""
    df_out = df_out.copy()
    for c in ["CP_CID", "CID"]:
        if c in df_out.columns:
            df_out[c] = df_out[c].map(normalize_pubchem_cid)
    return df_out


def _norm(s: str) -> str:
    return str(s).strip().lower() if s is not None else ""


def _chunk(xs: List[str], n: int) -> List[List[str]]:
    return [xs[i : i + n] for i in range(0, len(xs), n)]


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_prompt_file(prompt_path: str | Path) -> str:
    """Read a prompt from Markdown, plain text, or DOCX.

    Stage 3 public prompts are stored as .md files. DOCX support is retained
    only for backward compatibility.
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


def strip_extract_infer_suffix(x: str) -> str:
    x = _s(x)
    if x in {"NA", "Unknown"}:
        return x
    return re.sub(r"\s*\((Extracted|Inferred)\)\s*$", "", x, flags=re.IGNORECASE).strip()


def normalize_lookup_term(x: str) -> str:
    x = strip_extract_infer_suffix(_s(x))
    if x in {"NA", "Unknown"}:
        return x
    x = re.sub(r"[^\w\s\-\+;/|,]", " ", x)
    x = re.sub(r"\s+", " ", x).strip().lower()
    return x


def _wratio(a: str, b: str) -> float:
    if fuzz is None:
        sa, sb = set(a.split()), set(b.split())
        if not sa or not sb:
            return 0.0
        return 100.0 * (len(sa & sb) / max(len(sa), len(sb)))
    return float(fuzz.WRatio(a, b))


def _no_disease_state(x: str) -> bool:
    key = normalize_lookup_term(x)
    return key in {"normal", "no disease mentioned", "na", "unknown", ""}


# -------------------------
# CTD KB
# -------------------------
CTD_META_COLS = [
    "DiseaseName",
    "DiseaseID",
    "AltDiseaseIDs",
    "Definition",
    "ParentIDs",
    "TreeNumbers",
    "ParentTreeNumbers",
    "Synonyms",
    "SlimMappings",
]


def load_ctd_kb(ctd_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(ctd_csv)
    missing = [c for c in CTD_META_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"CTD file missing expected columns: {missing}")

    df = df.copy()
    for c in CTD_META_COLS:
        df[c] = df[c].fillna("").astype(str)

    df["norm_name"] = df["DiseaseName"].map(normalize_lookup_term)
    df["norm_syn"] = df["Synonyms"].fillna("").astype(str).str.lower()
    df["search_text"] = (
        df["DiseaseName"].fillna("").astype(str)
        + " "
        + df["Synonyms"].fillna("").astype(str)
        + " "
        + df["Definition"].fillna("").astype(str)
    ).str.lower()

    return df


# -------------------------
# Prior mapping loaders
# -------------------------
def _ensure_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")


def load_prior_disease_mapping(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load curated disease mappings using finalized public schema."""
    if not path.exists():
        print(f"[Stage3] prior_disease_mapping_xlsx not found: {path}")
        return {}

    df = pd.read_excel(path, engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip()

    required = {
        "Original_Raw_Disease_Term",
        "Standardized_Disease_Term",
        "Final_Mapped_Disease_Term",
        "DiseaseName",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Broad_Disease_Category",
    }
    _ensure_columns(df, required, "Prior disease mapping")

    mapping: Dict[str, Dict[str, Any]] = {}

    for _, r in df.iterrows():
        final_mapped = _blank(r.get("Final_Mapped_Disease_Term"))
        disease_name = _blank(r.get("DiseaseName"))
        mapped_label = final_mapped if final_mapped else disease_name

        rec = {
            "Disease_Mapped": mapped_label,
            "DiseaseID": _blank(r.get("DiseaseID")),
            "AltDiseaseIDs": _blank(r.get("AltDiseaseIDs")),
            "Definition": _blank(r.get("Definition")),
            "ParentIDs": _blank(r.get("ParentIDs")),
            "TreeNumbers": _blank(r.get("TreeNumbers")),
            "ParentTreeNumbers": _blank(r.get("ParentTreeNumbers")),
            "Synonyms": _blank(r.get("Synonyms")),
            "SlimMappings": _blank(r.get("SlimMappings")),
            "Broad_Disease_Category": _blank(r.get("Broad_Disease_Category")),
            "Disease_Map_Explanation": "Mapped from prior curated disease mapping file.",
            "Disease_Review_Required": False,
            "Disease_Map_Method": "prior_disease_file",
        }

        keys = [
            normalize_lookup_term(r.get("Original_Raw_Disease_Term", "")),
            normalize_lookup_term(r.get("Standardized_Disease_Term", "")),
            normalize_lookup_term(r.get("Final_Mapped_Disease_Term", "")),
            normalize_lookup_term(r.get("DiseaseName", "")),
        ]

        for key in keys:
            if key not in {"", "NA", "Unknown"}:
                mapping[key] = rec

    return mapping


def load_prior_tissue_mapping(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load curated tissue mappings using finalized public schema."""
    if not path.exists():
        print(f"[Stage3] prior_tissue_mapping_xlsx not found: {path}")
        return {}

    df = pd.read_excel(path, engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip()

    required = {
        "Original_Tissue_Term",
        "Standardized_Tissue_Term",
        "Final_Mapped_Tissue_Term",
    }
    _ensure_columns(df, required, "Prior tissue mapping")

    out: Dict[str, Dict[str, Any]] = {}

    for _, r in df.iterrows():
        keys = [
            normalize_lookup_term(r.get("Original_Tissue_Term", "")),
            normalize_lookup_term(r.get("Standardized_Tissue_Term", "")),
            normalize_lookup_term(r.get("Final_Mapped_Tissue_Term", "")),
        ]

        rec = {
            "Tissue_Mapped": _blank(r.get("Final_Mapped_Tissue_Term")),
            "Tissue_Map_Explanation": _blank(r.get("Comments")) if "Comments" in df.columns else "",
            "Tissue_Map_Method": "prior_tissue_file",
        }

        for k in keys:
            if k not in {"", "NA", "Unknown"} and k not in out:
                out[k] = rec

    return out


def load_prior_cp_mapping(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load curated compound mappings using finalized public schema."""
    if not path.exists():
        print(f"[Stage3] prior_cp_mapping_xlsx not found: {path}")
        return {}

    df = pd.read_excel(path, engine="openpyxl")
    df.columns = df.columns.astype(str).str.strip()

    required = {
        "Original_Raw_Compound_Term",
        "Standardized_Compound_Term",
        "Final_Mapped_Compound_Name",
        "CID",
        "MatchType",
        "CanonicalSMILES",
        "PubChemURL",
    }
    _ensure_columns(df, required, "Prior CP mapping")

    out: Dict[str, Dict[str, Any]] = {}

    for _, r in df.iterrows():
        keys = [
            normalize_lookup_term(r.get("Original_Raw_Compound_Term", "")),
            normalize_lookup_term(r.get("Standardized_Compound_Term", "")),
            normalize_lookup_term(r.get("Final_Mapped_Compound_Name", "")),
        ]

        rec = {
            "CP_PubChem_Name": _blank(r.get("Final_Mapped_Compound_Name")),
            "CP_CID": normalize_pubchem_cid(r.get("CID")),
            "CP_CanonicalSMILES": _blank(r.get("CanonicalSMILES")),
            "CP_PubChemURL": _blank(r.get("PubChemURL")),
            "CP_MatchType": _blank(r.get("MatchType")),
            "CP_Map_Explanation": "Mapped from prior curated compound mapping file.",
            "CP_Map_Method": "prior_cp_file",
        }

        for k in keys:
            if k not in {"", "NA", "Unknown"} and k not in out:
                out[k] = rec

    return out


# -------------------------
# LLM systems
# -------------------------
CTD_LLM_SYSTEM = (
    "You are a biomedical ontology mapping assistant working under a reviewer-governed disease mapping workflow.\n"
    "Return STRICT JSON only. No markdown. No commentary.\n"
    "Input JSON: {\"terms\": [\"...\"], \"candidates\": {\"term\": [{\"DiseaseName\":\"...\",\"DiseaseID\":\"...\",\"score\":99.1}]}}\n"
    "Output JSON: {\"mappings\": [{\"raw\":\"...\",\"DiseaseName\":\"...\",\"DiseaseID\":\"...\",\"explanation\":\"...\"}]}\n"
    "Rules:\n"
    "- Exactly one mapping per input term.\n"
    "- Prefer deterministic reasoning: normalized exact DiseaseName match, normalized synonym match, then generalized match.\n"
    "- Use candidate retrieval only after deterministic matching fails.\n"
    "- Prefer parent/general disease categories over numbered or genetic subtypes unless explicitly required by the input.\n"
    "- Do not overmatch vague descriptors, anatomical phrases, unrelated loci, or context-only similarities.\n"
    "- If no plausible CTD mapping exists, return DiseaseName=NA and DiseaseID=NA.\n"
    "- Never hallucinate a CTD mapping.\n"
)

TISSUE_LLM_SYSTEM = (
    "You are a biomedical tissue mapping assistant working under a controlled tissue mapping workflow.\n"
    "Return STRICT JSON only. No markdown. No commentary.\n"
    "Input JSON: {\"terms\": [..]}\n"
    "Output JSON: {\"mappings\": [{\"raw\":...,\"mapped\":...,\"explanation\":...}]}\n"
    "Rules:\n"
    "- Exactly one mapping per input term.\n"
    "- Map only to allowed HPA-derived tissue categories, supported brain subregions, additional curated tissue categories, Brain, or NA.\n"
    "- For brain-related terms only, map to Brain: [Region] using approved brain subregions when supported.\n"
    "- Outside brain, collapse subregions to the parent tissue.\n"
    "- Apply abbreviation expansion, synonym reduction, singular-over-plural, and title case normalization.\n"
    "- Do not invent categories beyond the controlled vocabulary.\n"
    "- If no valid mapping exists, return mapped=NA.\n"
)

CP_LLM_SYSTEM = (
    "You help normalize chemical perturbation names for PubChem mapping under a curated compound mapping workflow.\n"
    "Return STRICT JSON only. No markdown. No commentary.\n"
    "Input JSON: {\"terms\": [..]}\n"
    "Output JSON: {\"mappings\": [{\"raw\":...,\"query\":...,\"explanation\":...}]}\n"
    "Rules:\n"
    "- Exactly one mapping per input term.\n"
    "- query should be the best canonical compound name to send to PubChem name lookup.\n"
    "- Remove dose, duration, route, and other non-identifying modifiers.\n"
    "- Expand abbreviations and unify synonyms only when supported.\n"
    "- Only map single-compound chemical perturbations.\n"
    "- If the term is not a chemical perturbation or remains ambiguous, return query=NA.\n"
)


# -------------------------
# PubChem helpers
# -------------------------
def _request_json(url: str, timeout: int = 20, max_retries: int = 3):
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(0.5 * attempt)
    return None


def pubchem_cid_from_name(term: str, timeout: int = 20) -> Optional[str]:
    if not term or not str(term).strip():
        return None

    q = requests.utils.quote(str(term).strip())
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{q}/cids/JSON"
    data = _request_json(url, timeout=timeout)

    if not data:
        return None

    cids = data.get("IdentifierList", {}).get("CID", [])
    return normalize_pubchem_cid(cids[0]) if cids else None


def pubchem_cid_from_url(pubchem_url: str) -> str:
    """Extract a CID from common PubChem compound URLs."""
    v = _blank(pubchem_url)
    if not v:
        return ""
    m = re.search(r"/compound/(?:cid/)?(\d+)(?:[/?#]|$)", v, flags=re.I)
    if m:
        return normalize_pubchem_cid(m.group(1))
    return ""


def _find_pubchem_record_smiles(node: Any) -> str:
    """Recursively search a PUG-View record JSON object for canonical SMILES."""
    if isinstance(node, dict):
        heading = str(node.get("TOCHeading", "")).strip().lower()
        if "smiles" in heading:
            info_items = node.get("Information", [])
            if isinstance(info_items, list):
                for item in info_items:
                    value = item.get("Value", {}) if isinstance(item, dict) else {}
                    strings = value.get("StringWithMarkup") if isinstance(value, dict) else None
                    if isinstance(strings, list):
                        for s_item in strings:
                            text = s_item.get("String", "") if isinstance(s_item, dict) else ""
                            if text and " " not in text.strip():
                                return text.strip()
                    sval = value.get("String") if isinstance(value, dict) else None
                    if isinstance(sval, str) and sval.strip():
                        return sval.strip()
        for value in node.values():
            hit = _find_pubchem_record_smiles(value)
            if hit:
                return hit
    elif isinstance(node, list):
        for item in node:
            hit = _find_pubchem_record_smiles(item)
            if hit:
                return hit
    return ""


def pubchem_record_smiles_from_cid(cid: str, timeout: int = 20) -> str:
    cid = normalize_pubchem_cid(cid)
    if not cid:
        return ""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
    data = _request_json(url, timeout=timeout)
    return _find_pubchem_record_smiles(data) if data else ""


def pubchem_title_and_smiles_from_cid(cid: str, timeout: int = 20) -> Dict[str, str]:
    cid = normalize_pubchem_cid(cid)
    fallback = {
        "Title": "",
        "CanonicalSMILES": "",
        "PubChemURL": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid else "",
    }

    if not cid:
        return fallback

    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/"
        f"{cid}/property/Title,CanonicalSMILES/JSON"
    )
    data = _request_json(url, timeout=timeout)

    if not data:
        fallback["CanonicalSMILES"] = pubchem_record_smiles_from_cid(cid, timeout=timeout)
        return fallback

    try:
        p = data["PropertyTable"]["Properties"][0]
        smiles = _blank(p.get("CanonicalSMILES"))
        if not smiles:
            smiles = pubchem_record_smiles_from_cid(cid, timeout=timeout)
        return {
            "Title": _blank(p.get("Title")),
            "CanonicalSMILES": smiles,
            "PubChemURL": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
        }
    except Exception:
        fallback["CanonicalSMILES"] = pubchem_record_smiles_from_cid(cid, timeout=timeout)
        return fallback


def pubchem_synonyms_for_cid(cid: str, timeout: int = 20) -> set[str]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
    data = _request_json(url, timeout=timeout)

    if not data:
        return set()

    try:
        syns = data["InformationList"]["Information"][0]["Synonym"]
        return {_norm(s) for s in syns if s}
    except Exception:
        return set()


def resolve_cp_term_with_pubchem(query_term: str, timeout: int = 20) -> Dict[str, str]:
    if not query_term or _s(query_term) in {"NA", "Unknown"}:
        return {
            "CP_PubChem_Name": "",
            "CP_CID": "",
            "CP_CanonicalSMILES": "",
            "CP_PubChemURL": "",
            "CP_MatchType": "",
            "CP_Map_Explanation": "No valid PubChem query term.",
            "CP_Map_Method": "pubchem_na",
        }

    cid = pubchem_cid_from_name(query_term, timeout=timeout)

    if not cid:
        return {
            "CP_PubChem_Name": query_term,
            "CP_CID": "",
            "CP_CanonicalSMILES": "",
            "CP_PubChemURL": "",
            "CP_MatchType": "not_found",
            "CP_Map_Explanation": "PubChem name lookup failed.",
            "CP_Map_Method": "pubchem_name_failed",
        }

    props = pubchem_title_and_smiles_from_cid(cid, timeout=timeout)
    title = props.get("Title", "")
    match_type = "best_match"

    qnorm = _norm(query_term)
    if title and _norm(title) == qnorm:
        match_type = "exact_title"
    else:
        syns = pubchem_synonyms_for_cid(cid, timeout=timeout)
        if qnorm in syns:
            match_type = "synonym"

    return {
        "CP_PubChem_Name": title if title else query_term,
        "CP_CID": normalize_pubchem_cid(cid),
        "CP_CanonicalSMILES": props.get("CanonicalSMILES", ""),
        "CP_PubChemURL": props.get("PubChemURL", ""),
        "CP_MatchType": match_type,
        "CP_Map_Explanation": f"Resolved through PubChem {match_type} lookup.",
        "CP_Map_Method": "pubchem_name_then_synonym",
    }


def backfill_cp_smiles_from_existing_ids(df: pd.DataFrame, timeout: int = 20) -> pd.DataFrame:
    """Backfill missing CP_CanonicalSMILES from existing CP_CID or CP_PubChemURL.

    This function only changes rows that already have compound identifiers/URLs
    and an empty CP_CanonicalSMILES value. It also normalizes CP_CID to
    integer-like text before returning.
    """
    df = df.copy()
    for c in ["CP_CID", "CP_CanonicalSMILES", "CP_PubChemURL"]:
        if c not in df.columns:
            df[c] = ""

    df["CP_CID"] = df["CP_CID"].map(normalize_pubchem_cid)

    smiles_cache: Dict[str, str] = {}
    for idx in df.index:
        current_smiles = _blank(df.at[idx, "CP_CanonicalSMILES"])
        if current_smiles:
            continue

        cid = normalize_pubchem_cid(df.at[idx, "CP_CID"])
        if not cid:
            cid = pubchem_cid_from_url(df.at[idx, "CP_PubChemURL"])
            if cid:
                df.at[idx, "CP_CID"] = cid

        if not cid:
            continue

        if cid not in smiles_cache:
            props = pubchem_title_and_smiles_from_cid(cid, timeout=timeout)
            smiles_cache[cid] = _blank(props.get("CanonicalSMILES"))

        if smiles_cache[cid]:
            df.at[idx, "CP_CanonicalSMILES"] = smiles_cache[cid]
            if "CP_Map_Method" in df.columns and not _blank(df.at[idx, "CP_Map_Method"]):
                df.at[idx, "CP_Map_Method"] = "pubchem_cid_smiles_backfill"
            if "CP_Map_Explanation" in df.columns and not _blank(df.at[idx, "CP_Map_Explanation"]):
                df.at[idx, "CP_Map_Explanation"] = "CanonicalSMILES backfilled from existing PubChem CID/URL."

    return df


# -------------------------
# Candidate retrieval
# -------------------------
def ctd_candidates_for_term(
    term: str,
    ctd_df: pd.DataFrame,
    vectorizer: TfidfVectorizer,
    tfidf_matrix,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    raw = _s(term)
    norm = normalize_lookup_term(raw)

    if norm in {"NA", "Unknown"}:
        return []

    exact = ctd_df[ctd_df["norm_name"] == norm]
    if not exact.empty:
        return [
            {
                "DiseaseName": r["DiseaseName"],
                "DiseaseID": r["DiseaseID"],
                "score": 100.0,
            }
            for _, r in exact.head(top_k).iterrows()
        ]

    syn_hits = ctd_df[
        ctd_df["norm_syn"].str.contains(re.escape(norm), regex=True, na=False)
        | ctd_df["search_text"].str.contains(re.escape(norm), regex=True, na=False)
    ]

    rows: List[Dict[str, Any]] = []
    seen = set()

    for _, r in syn_hits.head(top_k).iterrows():
        key = (r["DiseaseName"], r["DiseaseID"])
        if key in seen:
            continue
        seen.add(key)
        score = max(
            _wratio(norm, normalize_lookup_term(r["DiseaseName"])),
            _wratio(norm, normalize_lookup_term(r["Synonyms"])),
        )
        rows.append(
            {
                "DiseaseName": r["DiseaseName"],
                "DiseaseID": r["DiseaseID"],
                "score": round(score, 2),
            }
        )

    if rows:
        return rows[:top_k]

    query_vec = vectorizer.transform([norm])
    sims = cosine_similarity(query_vec, tfidf_matrix)[0]
    idxs = sims.argsort()[::-1][:top_k]

    out: List[Dict[str, Any]] = []
    seen = set()

    for idx in idxs:
        r = ctd_df.iloc[int(idx)]
        key = (r["DiseaseName"], r["DiseaseID"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "DiseaseName": r["DiseaseName"],
                "DiseaseID": r["DiseaseID"],
                "score": round(float(sims[idx]) * 100.0, 2),
            }
        )

    return out


# -------------------------
# Novel term helpers
# -------------------------
def _build_novel_term_df(terms: List[str], domain: str) -> pd.DataFrame:
    if not terms:
        return pd.DataFrame(columns=["domain", "raw_term"])
    return pd.DataFrame({"domain": [domain] * len(terms), "raw_term": sorted(set(terms))})


# -------------------------
# Review / correction
# -------------------------
def _review_and_correct_stage3(
    df: pd.DataFrame,
    prior_tissue: Dict[str, Dict[str, Any]],
    prior_cp: Dict[str, Dict[str, Any]],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    review_rows: List[Dict[str, Any]] = []

    def record(gsm_id: str, field: str, old: str, new: str, reason: str):
        review_rows.append(
            {
                "GSM_ID": _s(gsm_id),
                "field": field,
                "old_value": _s(old),
                "new_value": _s(new),
                "reason": reason,
            }
        )

    for field in ["Disease_Pre", "Disease_Post", "Tissue_Pre", "Tissue_Post", "Pert_Pre", "Pert_Post"]:
        if field in df.columns:
            old_vals = df[field].copy()
            df[field] = df[field].map(strip_extract_infer_suffix)
            for idx in df.index:
                old = _s(old_vals.loc[idx])
                new = _s(df.at[idx, field])
                if old != new:
                    record(df.at[idx, "GSM_ID"], field, old, new, "strip_extract_infer_suffix")

    if {"Tissue_Post", "Tissue_Mapped"}.issubset(df.columns):
        for idx in df.index:
            key = normalize_lookup_term(df.at[idx, "Tissue_Post"])
            if key in prior_tissue:
                wanted = _blank(prior_tissue[key].get("Tissue_Mapped"))
                if wanted and _blank(df.at[idx, "Tissue_Mapped"]) != wanted:
                    old = _s(df.at[idx, "Tissue_Mapped"])
                    df.at[idx, "Tissue_Mapped"] = wanted

                    if "Tissue_Map_Explanation" in df.columns:
                        df.at[idx, "Tissue_Map_Explanation"] = _blank(
                            prior_tissue[key].get("Tissue_Map_Explanation")
                        )
                    if "Tissue_Map_Method" in df.columns:
                        df.at[idx, "Tissue_Map_Method"] = "prior_tissue_file"

                    record(df.at[idx, "GSM_ID"], "Tissue_Mapped", old, wanted, "prior_tissue_mapping_override")

    disease_payload_cols = [
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
    ]

    if "Disease_Post" in df.columns:
        for idx in df.index:
            if _no_disease_state(df.at[idx, "Disease_Post"]):
                for col in disease_payload_cols:
                    if col in df.columns and _blank(df.at[idx, col]) != "":
                        old = _s(df.at[idx, col])
                        df.at[idx, col] = ""
                        record(df.at[idx, "GSM_ID"], col, old, "", "clear_mapping_for_no_disease_state")

                if "Broad_Disease_Category" in df.columns and _s(df.at[idx, "Broad_Disease_Category"]) not in {"", "NA"}:
                    old = _s(df.at[idx, "Broad_Disease_Category"])
                    df.at[idx, "Broad_Disease_Category"] = "NA"
                    record(
                        df.at[idx, "GSM_ID"],
                        "Broad_Disease_Category",
                        old,
                        "NA",
                        "clear_broad_group_for_no_disease_state",
                    )

    if {"Pert_Post", "Pert_Type"}.issubset(df.columns):
        for idx in df.index:
            if _s(df.at[idx, "Pert_Type"]) == "CP":
                key = normalize_lookup_term(df.at[idx, "Pert_Post"])
                if key in prior_cp:
                    rec = prior_cp[key]
                    for col in [
                        "CP_PubChem_Name",
                        "CP_CID",
                        "CP_CanonicalSMILES",
                        "CP_PubChemURL",
                        "CP_MatchType",
                        "CP_Map_Explanation",
                    ]:
                        if col in df.columns:
                            wanted = _blank(rec.get(col))
                            if wanted and _blank(df.at[idx, col]) != wanted:
                                old = _s(df.at[idx, col])
                                df.at[idx, col] = wanted
                                record(df.at[idx, "GSM_ID"], col, old, wanted, "prior_cp_mapping_override")

                    if "CP_Map_Method" in df.columns:
                        df.at[idx, "CP_Map_Method"] = "prior_cp_file"

    return df, pd.DataFrame(review_rows)


# -------------------------
# Stage 3 main
# -------------------------
def run_stage3_mapping(cfg, df_stage2: pd.DataFrame) -> pd.DataFrame:
    cfg.validate_env()

    required = {"GSM_ID", "GSE_ID", "Disease_Post", "Tissue_Post", "Pert_Type", "Pert_Post"}
    missing = required - set(df_stage2.columns)
    if missing:
        raise ValueError(f"Stage2 output missing required columns for Stage3: {sorted(missing)}")

    llm = make_llm_from_config(cfg)

    outdir = Path(cfg.outputs_dir)
    mapdir = Path(cfg.mapping_cache_dir)
    debugdir = Path(cfg.debug_dir)
    reviewdir = Path(cfg.review_dir)
    novel_dir = Path(cfg.novel_term_dir)

    for d in [outdir, mapdir, debugdir, reviewdir, novel_dir]:
        d.mkdir(parents=True, exist_ok=True)

    df = df_stage2.copy()

    for col in ["Disease_Pre", "Disease_Post", "Tissue_Pre", "Tissue_Post", "Pert_Pre", "Pert_Post"]:
        if col in df.columns:
            df[col] = df[col].map(strip_extract_infer_suffix)

    ctd_df = load_ctd_kb(Path(cfg.ctd_csv))
    prior_disease = load_prior_disease_mapping(Path(cfg.prior_disease_mapping_xlsx))
    prior_tissue = load_prior_tissue_mapping(Path(cfg.prior_tissue_mapping_xlsx))
    prior_cp = load_prior_cp_mapping(Path(cfg.prior_cp_mapping_xlsx))

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    tfidf_matrix = vectorizer.fit_transform(ctd_df["search_text"].tolist())

    # -------------------------
    # Disease mapping
    # -------------------------
    disease_vals = df["Disease_Post"].map(_s).tolist()
    disease_uniq = sorted({v for v in disease_vals if v not in {"NA", "Unknown"}})
    disease_cache_fp = mapdir / "DiseasePost_to_CTD.json"
    disease_cache = _load_json(disease_cache_fp)

    need_terms: List[str] = []

    for t in disease_uniq:
        key = normalize_lookup_term(t)

        if key in prior_disease:
            disease_cache[t] = prior_disease[key]
            continue

        if _no_disease_state(t):
            disease_cache[t] = {
                "Disease_Mapped": "",
                "DiseaseID": "",
                "AltDiseaseIDs": "",
                "Definition": "",
                "ParentIDs": "",
                "TreeNumbers": "",
                "ParentTreeNumbers": "",
                "Synonyms": "",
                "SlimMappings": "",
                "Broad_Disease_Category": "NA",
                "Disease_Map_Explanation": "Explicit no-disease state.",
                "Disease_Review_Required": False,
                "Disease_Map_Method": "no_disease_state",
                "Final_Diease_Term_Flag": "",
                "Comment1": "",
                "Comment2": "",
                "Match_MESHCode": "",
            }
            continue

        if t in disease_cache:
            continue

        need_terms.append(t)

    _save_json(disease_cache_fp, disease_cache)
    print(f"[Stage3 CTD] Unique={len(disease_uniq)} Need={len(need_terms)}")

    novel_disease_df = _build_novel_term_df(need_terms, "Disease")

    if need_terms:
        extra_disease_guidance = ""
        try:
            p = Path(cfg.disease_mapping_prompt_docx)
            if p.exists():
                extra_disease_guidance = "\n\n" + read_prompt_file(p)
        except Exception:
            pass

        new_results: Dict[str, Dict[str, Any]] = {}

        for bi, chunk_terms in enumerate(_chunk(need_terms, min(cfg.term_batch_size, 20))):
            cand_payload = {
                t: ctd_candidates_for_term(t, ctd_df, vectorizer, tfidf_matrix, top_k=8)
                for t in chunk_terms
            }
            payload = {"terms": chunk_terms, "candidates": cand_payload}
            messages = [
                {"role": "system", "content": CTD_LLM_SYSTEM + extra_disease_guidance},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]

            txt = llm.chat(messages, temperature=0.0)
            out = safe_json_loads_with_repair(
                txt,
                debug_dir=str(debugdir),
                debug_tag=f"CTD_{bi}",
                llm_chat_fn=lambda msgs, temperature=0.0: llm.chat(msgs, temperature=temperature),
            )

            got = set()

            for r in out.get("mappings", []):
                raw = _s(r.get("raw"))
                mapped_name = _s(r.get("DiseaseName"))
                mapped_id = _s(r.get("DiseaseID"))
                expl = _s(r.get("explanation"))
                got.add(raw)

                if raw in {"NA", ""}:
                    continue

                if mapped_name in {"NA", "Unknown"} or mapped_id in {"NA", "Unknown"}:
                    new_results[raw] = {
                        "Disease_Mapped": "",
                        "DiseaseID": "",
                        "AltDiseaseIDs": "",
                        "Definition": "",
                        "ParentIDs": "",
                        "TreeNumbers": "",
                        "ParentTreeNumbers": "",
                        "Synonyms": "",
                        "SlimMappings": "",
                        "Broad_Disease_Category": "",
                        "Disease_Map_Explanation": expl if expl not in {"NA", "Unknown"} else "",
                        "Disease_Review_Required": True,
                        "Disease_Map_Method": "llm_no_match",
                        "Final_Diease_Term_Flag": "NEW_TERM_REVIEW",
                        "Comment1": "LLM no good disease mapping found.",
                        "Comment2": "",
                        "Match_MESHCode": "",
                    }
                    continue

                hit = ctd_df[
                    (ctd_df["DiseaseName"].astype(str) == mapped_name)
                    & (ctd_df["DiseaseID"].astype(str) == mapped_id)
                ]

                if hit.empty:
                    new_results[raw] = {
                        "Disease_Mapped": "",
                        "DiseaseID": "",
                        "AltDiseaseIDs": "",
                        "Definition": "",
                        "ParentIDs": "",
                        "TreeNumbers": "",
                        "ParentTreeNumbers": "",
                        "Synonyms": "",
                        "SlimMappings": "",
                        "Broad_Disease_Category": "",
                        "Disease_Map_Explanation": "LLM selected CTD term not found in KB.",
                        "Disease_Review_Required": True,
                        "Disease_Map_Method": "llm_invalid",
                        "Final_Diease_Term_Flag": "NEW_TERM_REVIEW",
                        "Comment1": "LLM invalid CTD selection.",
                        "Comment2": "",
                        "Match_MESHCode": "",
                    }
                    continue

                row0 = hit.iloc[0]
                new_results[raw] = {
                    "Disease_Mapped": _blank(row0.get("DiseaseName")),
                    "DiseaseID": _blank(row0.get("DiseaseID")),
                    "AltDiseaseIDs": _blank(row0.get("AltDiseaseIDs")),
                    "Definition": _blank(row0.get("Definition")),
                    "ParentIDs": _blank(row0.get("ParentIDs")),
                    "TreeNumbers": _blank(row0.get("TreeNumbers")),
                    "ParentTreeNumbers": _blank(row0.get("ParentTreeNumbers")),
                    "Synonyms": _blank(row0.get("Synonyms")),
                    "SlimMappings": _blank(row0.get("SlimMappings")),
                    "Broad_Disease_Category": "",
                    "Disease_Map_Explanation": expl if expl not in {"NA", "Unknown"} else "",
                    "Disease_Review_Required": True,
                    "Disease_Map_Method": "llm_ctd",
                    "Final_Diease_Term_Flag": "NEW_TERM_LLM",
                    "Comment1": "Mapped by LLM after prior mapping miss.",
                    "Comment2": "",
                    "Match_MESHCode": "",
                }

            missing_terms = set(chunk_terms) - got
            for m in missing_terms:
                new_results[m] = {
                    "Disease_Mapped": "",
                    "DiseaseID": "",
                    "AltDiseaseIDs": "",
                    "Definition": "",
                    "ParentIDs": "",
                    "TreeNumbers": "",
                    "ParentTreeNumbers": "",
                    "Synonyms": "",
                    "SlimMappings": "",
                    "Broad_Disease_Category": "",
                    "Disease_Map_Explanation": "No mapping returned.",
                    "Disease_Review_Required": True,
                    "Disease_Map_Method": "llm_missing",
                    "Final_Diease_Term_Flag": "NEW_TERM_REVIEW",
                    "Comment1": "No LLM mapping returned.",
                    "Comment2": "",
                    "Match_MESHCode": "",
                }

        for t, rec in new_results.items():
            key = normalize_lookup_term(t)
            if key in prior_disease:
                continue
            disease_cache[t] = rec

        _save_json(disease_cache_fp, disease_cache)

    disease_records = [disease_cache.get(v, {}) for v in disease_vals]
    disease_cols = [
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Broad_Disease_Category",
        "Disease_Map_Explanation",
        "Disease_Review_Required",
        "Disease_Map_Method",
        "Final_Diease_Term_Flag",
        "Comment1",
        "Comment2",
        "Match_MESHCode",
    ]

    for c in disease_cols:
        default_val = False if c == "Disease_Review_Required" else ""
        df[c] = [rec.get(c, default_val) for rec in disease_records]

    # -------------------------
    # Tissue mapping
    # -------------------------
    tissue_vals = df["Tissue_Post"].map(_s).tolist()
    tissue_uniq = sorted({v for v in tissue_vals if v not in {"NA", "Unknown"}})
    tissue_cache_fp = mapdir / "TissuePost_to_Mapped.json"
    tissue_cache = _load_json(tissue_cache_fp)

    tissue_need: List[str] = []

    for t in tissue_uniq:
        key = normalize_lookup_term(t)

        if key in prior_tissue:
            tissue_cache[t] = prior_tissue[key]
            continue

        if t in tissue_cache:
            continue

        tissue_need.append(t)

    _save_json(tissue_cache_fp, tissue_cache)
    print(f"[Stage3 Tissue] Unique={len(tissue_uniq)} Need={len(tissue_need)}")

    novel_tissue_df = _build_novel_term_df(tissue_need, "Tissue")

    if tissue_need:
        extra_tissue_guidance = ""
        try:
            p = Path(cfg.tissue_mapping_prompt_docx)
            if p.exists():
                extra_tissue_guidance = "\n\n" + read_prompt_file(p)
        except Exception:
            pass

        for bi, chunk_terms in enumerate(_chunk(tissue_need, min(cfg.term_batch_size, 20))):
            payload = {"terms": chunk_terms}
            messages = [
                {"role": "system", "content": TISSUE_LLM_SYSTEM + extra_tissue_guidance},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]

            txt = llm.chat(messages, temperature=0.0)
            out = safe_json_loads_with_repair(
                txt,
                debug_dir=str(debugdir),
                debug_tag=f"TISSUE_{bi}",
                llm_chat_fn=lambda msgs, temperature=0.0: llm.chat(msgs, temperature=temperature),
            )

            got = set()

            for r in out.get("mappings", []):
                raw = _s(r.get("raw"))
                mapped = _s(r.get("mapped"))
                expl = _s(r.get("explanation"))
                got.add(raw)

                if raw in {"NA", ""}:
                    continue

                tissue_cache[raw] = {
                    "Tissue_Mapped": "" if mapped == "NA" else mapped,
                    "Tissue_Map_Explanation": "" if expl == "NA" else expl,
                    "Tissue_Map_Method": "llm_tissue",
                }

            missing_terms = set(chunk_terms) - got
            for m in missing_terms:
                tissue_cache[m] = {
                    "Tissue_Mapped": "",
                    "Tissue_Map_Explanation": "No mapping returned.",
                    "Tissue_Map_Method": "llm_missing",
                }

        _save_json(tissue_cache_fp, tissue_cache)

    df["Tissue_Mapped"] = [tissue_cache.get(v, {}).get("Tissue_Mapped", "") for v in tissue_vals]
    df["Tissue_Map_Explanation"] = [
        tissue_cache.get(v, {}).get("Tissue_Map_Explanation", "") for v in tissue_vals
    ]
    df["Tissue_Map_Method"] = [tissue_cache.get(v, {}).get("Tissue_Map_Method", "") for v in tissue_vals]

    # -------------------------
    # Pert / PubChem mapping
    # -------------------------
    pert_vals = df["Pert_Post"].map(_s).tolist()
    pert_uniq = sorted({v for v in pert_vals if v not in {"NA", "Unknown"}})
    cp_cache_fp = mapdir / "PertPost_to_PubChem.json"
    cp_cache = _load_json(cp_cache_fp)

    cp_need: List[str] = []

    for t in pert_uniq:
        rows = df.loc[df["Pert_Post"] == t, "Pert_Type"]
        is_cp = not rows.empty and _s(rows.iloc[0]) == "CP"

        if not is_cp:
            continue

        key = normalize_lookup_term(t)

        if key in prior_cp:
            cp_cache[t] = prior_cp[key]
            continue

        if t in cp_cache:
            continue

        cp_need.append(t)

    _save_json(cp_cache_fp, cp_cache)

    unique_cp_terms = len(
        [
            t for t in pert_uniq
            if not df.loc[df["Pert_Post"] == t, "Pert_Type"].empty
            and _s(df.loc[df["Pert_Post"] == t, "Pert_Type"].iloc[0]) == "CP"
        ]
    )
    print(f"[Stage3 Pert/CP] Unique_CP_terms={unique_cp_terms} Need={len(cp_need)}")

    novel_pert_df = _build_novel_term_df(cp_need, "Pert")

    if cp_need:
        extra_cp_guidance = ""
        try:
            p = Path(cfg.cp_mapping_prompt_docx)
            if p.exists():
                extra_cp_guidance = "\n\n" + read_prompt_file(p)
        except Exception:
            pass

        for bi, chunk_terms in enumerate(_chunk(cp_need, min(cfg.term_batch_size, 25))):
            payload = {"terms": chunk_terms}
            messages = [
                {"role": "system", "content": CP_LLM_SYSTEM + extra_cp_guidance},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]

            txt = llm.chat(messages, temperature=0.0)
            out = safe_json_loads_with_repair(
                txt,
                debug_dir=str(debugdir),
                debug_tag=f"CP_{bi}",
                llm_chat_fn=lambda msgs, temperature=0.0: llm.chat(msgs, temperature=temperature),
            )

            got = set()

            for r in out.get("mappings", []):
                raw = _s(r.get("raw"))
                query = _s(r.get("query"))
                expl = _s(r.get("explanation"))
                got.add(raw)

                if raw in {"NA", ""}:
                    continue

                resolved = resolve_cp_term_with_pubchem(query, timeout=int(cfg.pubchem_timeout_sec))
                if expl not in {"NA", "Unknown", ""}:
                    resolved["CP_Map_Explanation"] = expl
                cp_cache[raw] = resolved

            missing_terms = set(chunk_terms) - got
            for m in missing_terms:
                cp_cache[m] = {
                    "CP_PubChem_Name": "",
                    "CP_CID": "",
                    "CP_CanonicalSMILES": "",
                    "CP_PubChemURL": "",
                    "CP_MatchType": "",
                    "CP_Map_Explanation": "No mapping returned.",
                    "CP_Map_Method": "llm_missing",
                }

        _save_json(cp_cache_fp, cp_cache)

    def apply_cp_row(pert_type: str, pert_post: str) -> Dict[str, str]:
        if _s(pert_type) != "CP":
            return {
                "CP_PubChem_Name": "",
                "CP_CID": "",
                "CP_CanonicalSMILES": "",
                "CP_PubChemURL": "",
                "CP_MatchType": "",
                "CP_Map_Explanation": "",
                "CP_Map_Method": "",
            }

        rec = cp_cache.get(_s(pert_post), {})
        return {
            "CP_PubChem_Name": rec.get("CP_PubChem_Name", ""),
            "CP_CID": rec.get("CP_CID", ""),
            "CP_CanonicalSMILES": rec.get("CP_CanonicalSMILES", ""),
            "CP_PubChemURL": rec.get("CP_PubChemURL", ""),
            "CP_MatchType": rec.get("CP_MatchType", ""),
            "CP_Map_Explanation": rec.get("CP_Map_Explanation", ""),
            "CP_Map_Method": rec.get("CP_Map_Method", ""),
        }

    df_cp = pd.DataFrame(
        [apply_cp_row(pt, pp) for pt, pp in zip(df["Pert_Type"].tolist(), df["Pert_Post"].tolist())]
    )
    df = pd.concat([df, df_cp], axis=1)

    # -------------------------
    # New-term flags for manual review
    # -------------------------
    df["Disease_New_Term_Flag"] = df["Disease_Post"].map(
        lambda x: normalize_lookup_term(x) not in prior_disease and not _no_disease_state(x)
    )

    df["Tissue_New_Term_Flag"] = df["Tissue_Post"].map(
        lambda x: normalize_lookup_term(x) not in prior_tissue and _s(x) not in {"NA", "Unknown"}
    )

    df["Pert_New_Term_Flag"] = df.apply(
        lambda r: (
            normalize_lookup_term(r["Pert_Post"]) not in prior_cp
            if _s(r["Pert_Type"]) == "CP" and _s(r["Pert_Post"]) not in {"NA", "Unknown"}
            else False
        ),
        axis=1,
    )

    # -------------------------
    # Save novel term workbook
    # -------------------------
    novel_df = pd.concat([novel_disease_df, novel_tissue_df, novel_pert_df], ignore_index=True)
    novel_fp = novel_dir / f"{cfg.run_version}_stage3_novel_terms.xlsx"
    novel_df.to_excel(novel_fp, index=False)

    # -------------------------
    # Review / correct
    # -------------------------
    df, review_df = _review_and_correct_stage3(df, prior_tissue, prior_cp)

    # -------------------------
    # Backfill missing CP_CanonicalSMILES from existing CP_CID or CP_PubChemURL
    # and normalize CP_CID before final outputs are assembled.
    # -------------------------
    df = backfill_cp_smiles_from_existing_ids(df, timeout=int(cfg.pubchem_timeout_sec))

    # -------------------------
    # Backfill Broad_Disease_Category using prior disease mapping
    # This is needed when Disease_Mapped was generated by LLM CTD mapping
    # but the broad disease category exists in the curated disease mapping file.
    # -------------------------
    disease_category_lookup = {}

    for rec in prior_disease.values():
        mapped = normalize_lookup_term(rec.get("Disease_Mapped", ""))
        category = _blank(rec.get("Broad_Disease_Category", ""))

        if mapped and mapped not in {"na", "unknown"} and category:
            disease_category_lookup[mapped] = category

    if "Broad_Disease_Category" in df.columns and "Disease_Mapped" in df.columns:
        for idx in df.index:
            current_cat = _blank(df.at[idx, "Broad_Disease_Category"])
            mapped_key = normalize_lookup_term(df.at[idx, "Disease_Mapped"])

            if not current_cat and mapped_key in disease_category_lookup:
                df.at[idx, "Broad_Disease_Category"] = disease_category_lookup[mapped_key]


    # -------------------------
    # Final safeguard: GSM_Pert_Post must mirror GSM_Pert_Pre
    # Allowed final values: Control / Perturbed / NA
    # -------------------------
    def _normalize_gsm_pert_from_pre(x):
        x = str(x).strip().lower()
        if x in {"control", "ctrl", "no", "false", "0"}:
            return "Control"
        if x in {"perturbed", "treated", "yes", "true", "1"}:
            return "Perturbed"
        if x in {"na", "unknown", ""}:
            return "NA"
        return "NA"

    if "GSM_Pert_Pre" in df.columns:
        df["GSM_Pert_Post"] = df["GSM_Pert_Pre"].apply(_normalize_gsm_pert_from_pre)

    # -------------------------
    # Final columns
        # -------------------------
    # Final columns
    # -------------------------
    final_cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Pre",
        "Seq_Type_Post",
        "Organism_Pre",
        "Organism_Post",
        "Strain_Pre",
        "Strain_Post",
        "Genotype_Pre",
        "Genotype_Post",
        "Cell_Line_Post",
        "RNA_Library_Pre",
        "RNA_Library_Post",
        "RNA_Source_Pre",
        "RNA_Source_Post",
        "Tissue_Pre",
        "Tissue_Post",
        "Tissue_Mapped",
        "Tissue_Map_Explanation",
        "Tissue_Map_Method",
        "Experimental_Setting_Pre",
        "Experimental_Setting_Post",
        "Model_Type_Pre",
        "Model_Type_Post",
        "Disease_Pre",
        "Disease_Post",
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Final_Diease_Term_Flag",
        "Comment1",
        "Comment2",
        "Match_MESHCode",
        "Broad_Disease_Category",
        "Disease_Map_Explanation",
        "Disease_Review_Required",
        "Disease_Map_Method",
        "Disease_New_Term_Flag",
        "Tissue_New_Term_Flag",
        "Pert_New_Term_Flag",
        "GSE_Pert_Pre",
        "GSE_Pert_Post",
        "GSM_Pert_Pre",
        "GSM_Pert_Post",
        "Pert_Pre",
        "Pert_Post",
        "Pert_Type",
        "CP_PubChem_Name",
        "CP_CID",
        "CP_CanonicalSMILES",
        "CP_PubChemURL",
        "CP_MatchType",
        "CP_Map_Explanation",
        "CP_Map_Method",
        "Pert_Dose_Pre",
        "Pert_Dose_Post",
        "Pert_Freq_Pre",
        "Pert_Freq_Post",
        "Pert_Duration_Pre",
        "Pert_Duration_Post",
        "Route_Admin_Pre",
        "Route_Admin_Post",
        "SampleType",
        "Specimen_Type_Pre",
        "Specimen_Type_Post",
        "Race_Pre",
        "Race_Post",
        "Ethnicity_Pre",
        "Ethnicity_Post",
        "Age_Pre",
        "Age_Post",
        "Age_Group_Post",
        "Sex_Pre",
        "Sex_Inferred_from_Organ",
        "Sex_Post",
        "Timepoint_Pre",
        "Timepoint_Post",
        "Outcome_Pre",
        "Outcome_Post",
        "GSE_Info",
        "GSM_Info",
    ]

    blank_cols = {
        "Tissue_Mapped",
        "Tissue_Map_Explanation",
        "Tissue_Map_Method",
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Final_Diease_Term_Flag",
        "Comment1",
        "Comment2",
        "Match_MESHCode",
        "Broad_Disease_Category",
        "Disease_Map_Explanation",
        "Disease_Map_Method",
        "CP_PubChem_Name",
        "CP_CID",
        "CP_CanonicalSMILES",
        "CP_PubChemURL",
        "CP_MatchType",
        "CP_Map_Explanation",
        "CP_Map_Method",
        "GSE_Info",
        "GSM_Info",
    }

    flag_cols = {
        "Disease_Review_Required",
        "Disease_New_Term_Flag",
        "Tissue_New_Term_Flag",
        "Pert_New_Term_Flag",
    }

    for c in final_cols:
        if c not in df.columns:
            if c in flag_cols:
                df[c] = False
            elif c in blank_cols:
                df[c] = ""
            else:
                df[c] = "NA"

    df_final = df.loc[:, final_cols].copy()


    # ============================================================
    # Filtered mapped release file
    # ============================================================

    release_cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Pre",	
        "Seq_Type_Post",	
        "Organism_Pre",
        "Organism_Post",
        "RNA_Library_Pre",
        "RNA_Library_Post",
        "Experimental_Setting_Pre",
        "Experimental_Setting_Post",
        "GSE_Pert_Pre",
        "GSE_Pert_Post",
        "GSM_Pert_Pre",
        "GSM_Pert_Post",
        "Disease_Pre",
        "Disease_Post",
        "Disease_Mapped",
        "DiseaseID",
        "AltDiseaseIDs",
        "Definition",
        "ParentIDs",
        "TreeNumbers",
        "ParentTreeNumbers",
        "Synonyms",
        "SlimMappings",
        "Broad_Disease_Category",
        "Tissue_Pre",
        "Tissue_Post",
        "Tissue_Mapped",
        "Age_Pre",
        "Age_Post",
        "Age_Group_Post",
        "Sex_Pre",
        "Sex_Inferred_from_Organ",
        "Sex_Post",
        "GSE_Info",
        "GSM_Info",
    ]

    for c in release_cols:
        if c not in df_final.columns:
            df_final[c] = ""

    df_release = df_final.loc[:, release_cols].copy()



   # ============================================================
    # Final simplified release file with renamed columns
    # ============================================================

    simple_release_cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Post",
        "Organism_Post",
        "RNA_Library_Post",
        "Experimental_Setting_Post",
        "GSE_Pert_Post",
        "GSM_Pert_Post",
        "Disease_Mapped",
        "Broad_Disease_Category",
        "Tissue_Mapped",
        "Age_Post",
        "Age_Group_Post",
        "Sex_Post",
        "GSE_Info",
        "GSM_Info",
    ]

    for c in simple_release_cols:
        if c not in df_final.columns:
            df_final[c] = ""

    df_simple_release = df_final.loc[:, simple_release_cols].copy()

    df_simple_release = df_simple_release.rename(
        columns={
            "Seq_Type_Post": "Seq_Type",
            "Organism_Post": "Organism",
            "RNA_Library_Post": "RNA_Library",
            "Experimental_Setting_Post": "Exp_Setting",
            "GSE_Pert_Post": "GSE_Pert",
            "GSM_Pert_Post": "GSM_Pert",
            "Disease_Mapped": "Disease",
            "Tissue_Mapped": "Tissue",
            "Age_Post": "Age",
            "Age_Group_Post": "Age_Group",
            "Sex_Post": "Sex",
        }
    )



    # ============================================================
    # CP perturbation GSE release file with renamed columns
    # Keep all GSMs from any GSE containing at least one CP sample.
    # ============================================================

    cp_release_cols = [
        "GSM_ID",
        "GSE_ID",
        "Seq_Type_Post",  
        "Organism_Post",  
        "Cell_Line_Post",
        "Strain_Post",
        "Genotype_Post",
        "RNA_Library_Post",
        "Experimental_Setting_Post",
        "GSE_Pert_Post",
        "GSM_Pert_Post",
        "Disease_Mapped",
        "Broad_Disease_Category",
        "Tissue_Mapped",
        "Age_Post",
        "Age_Group_Post",
        "Sex_Post",
        "Pert_Post",
        "Pert_Type",
        "CP_PubChem_Name",
        "CP_CID",
        "CP_CanonicalSMILES",
        "CP_PubChemURL",
        "Pert_Dose_Post",
        "Pert_Freq_Post",
        "Pert_Duration_Post",
        "Route_Admin_Post",
        "GSE_Info",
        "GSM_Info",
    ]

    for c in cp_release_cols:
        if c not in df_final.columns:
            df_final[c] = ""

    cp_gse_ids = set(
        df_final.loc[
            df_final["Pert_Type"].astype(str).str.upper().eq("CP"),
            "GSE_ID",
        ].dropna().astype(str)
    )
    df_cp_release = df_final.loc[df_final["GSE_ID"].astype(str).isin(cp_gse_ids), cp_release_cols].copy()

    df_cp_release = df_cp_release.rename(
        columns={
            "Seq_Type_Post": "Seq_Type",	
            "Organism_Post": "Organism",
            "Cell_Line_Post": "Cell_Line",
            "Strain_Post": "Strain",
            "Genotype_Post": "Genotype",
            "RNA_Library_Post": "RNA_Library",
            "Experimental_Setting_Post": "Exp_Setting",
            "GSE_Pert_Post": "GSE_Pert",
            "GSM_Pert_Post": "GSM_Pert",
            "Disease_Mapped": "Disease",
            "Tissue_Mapped": "Tissue",
            "Age_Post": "Age",
            "Age_Group_Post": "Age_Group",
            "Sex_Post": "Sex",
            "Pert_Post": "Perturbation",
            "Pert_Dose_Post": "Pert_Dose",
            "Pert_Freq_Post": "Pert_Freq",
            "Pert_Duration_Post": "Pert_Duration",
            "Route_Admin_Post": "Route_Admin",
        }
    )

    df_final = normalize_cid_columns(df_final)
    df_release = normalize_cid_columns(blank_release_na(df_release))
    df_simple_release = normalize_cid_columns(blank_release_na(df_simple_release))
    df_cp_release = normalize_cid_columns(blank_release_na(df_cp_release))

    # Blank selected NA-style fields in the full mapped output
    full_output_blank_cols = [
        "Cell_Line_Post",
        "Disease_Pre",
        "Disease_Post",
        "Pert_Pre",
        "Pert_Post",
        "Sex_Inferred_from_Organ",
    ]
    for c in full_output_blank_cols:
        if c in df_final.columns:
            df_final[c] = df_final[c].replace({"NA": "", "Unknown": ""})

    out_xlsx = outdir / f"{cfg.run_version}_stage3_mapped.xlsx"
    release_xlsx = outdir / f"{cfg.run_version}_stage3_mapped_filtered.xlsx"
    simple_release_xlsx = outdir / f"{cfg.run_version}_stage3_final_release.xlsx"
    cp_release_xlsx = outdir / f"{cfg.run_version}_stage3_cp_perturbation_release.xlsx"
    review_xlsx = reviewdir / f"{cfg.run_version}_stage3_post_mapping_review_corrections.xlsx"

    df_final.to_excel(out_xlsx, index=False)
    df_release.to_excel(release_xlsx, index=False)
    df_simple_release.to_excel(simple_release_xlsx, index=False)
    df_cp_release.to_excel(cp_release_xlsx, index=False)
    review_df.to_excel(review_xlsx, index=False)

    print("[SAVED] Stage3 mapped Excel:", out_xlsx)
    print("[SAVED] Stage3 filtered release Excel:", release_xlsx)
    print("[SAVED] Stage3 final simplified release Excel:", simple_release_xlsx)
    print("[SAVED] Stage3 CP perturbation GSE release Excel:", cp_release_xlsx)
    print("[SAVED] Stage3 post-mapping review corrections:", review_xlsx)
    print("[SAVED] Stage3 novel terms:", novel_fp)

    return df_final
