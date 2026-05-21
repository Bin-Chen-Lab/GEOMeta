# Tissue Controlled Vocabulary Mapping Prompt

## Purpose

Standardize GEOMeta tissue and organ-region terms to a controlled tissue vocabulary derived primarily from Human Protein Atlas (HPA) top-level tissue categories. For brain-related terms, retain selected brain subregion resolution when supported.

This prompt is used as additional guidance inside the Stage 3 tissue mapping workflow. The Python script provides terms requiring mapping and expects a structured mapping output.

## Input

Each input is a tissue, organ, organ-region, anatomical source, cell-source, or disease-site term extracted from GEO metadata.

Examples:
- heart left ventricle
- hippocampus
- lower segment myometrium
- lymph node
- melanoma
- subcutaneous tumor

## Allowed Top-Level Tissue Categories

Map each term to one of the following categories when possible:

- Eye
- Retina
- Heart
- Skeletal muscle
- Smooth muscle
- Adrenal gland
- Parathyroid gland
- Thyroid gland
- Pituitary gland
- Lung
- Bone marrow
- Lymphoid tissue
- Liver
- Gallbladder
- Testis
- Epididymis
- Prostate
- Seminal vesicle
- Adipose tissue
- Brain
- Choroid plexus
- Salivary gland
- Esophagus
- Tongue
- Stomach
- Intestine
- Pancreas
- Kidney
- Urinary bladder
- Breast
- Vagina
- Cervix
- Endometrium
- Fallopian tube
- Ovary
- Placenta
- Skin

## Additional Curated Tissue Categories

To improve coverage for anatomically specialized, clinically common, or underrepresented GEO tissue annotations not adequately represented in the core HPA ontology, the following additional curated categories are also permitted:

- Blood
- Nasal
- Nasopharynx
- Oropharynx
- Synovium
- Umbilical vein
- Head and Neck

These categories were introduced to improve consistency and reduce excessive assignment of `NA` for recurrent tissue descriptors commonly observed in GEO metadata.

## Brain Subregion Mapping

For brain-related terms, map to `Brain` or to one of the following supported subregions using the format:

```text
Brain: <Region>
```

Allowed brain subregions:

- Brain: Cerebral cortex
- Brain: Cerebellum
- Brain: Basal ganglia
- Brain: Thalamus
- Brain: Hypothalamus
- Brain: Midbrain
- Brain: White matter
- Brain: Amygdala
- Brain: Choroid plexus
- Brain: Pons
- Brain: Medulla oblongata
- Brain: Hippocampal formation
- Brain: Spinal cord

If a brain term is clearly brain-derived but the subregion is unclear, return `Brain`.

## Mapping Rules

### 1. Use the Controlled Vocabulary

Do not create categories beyond the allowed HPA-derived tissue categories, supported brain subregions, additional curated categories, `Brain`, or `NA`.

Return only one valid mapping category per input term.

### 2. Use Title Case

Use the spelling and capitalization shown in the allowed category list.

Examples:
- heart → Heart
- bone marrow → Bone marrow

### 3. Remove Non-Brain Subregions

For non-brain tissues, remove subregion detail and map to the parent tissue.

Examples:
- Heart left ventricle → Heart
- Liver caudate lobe → Liver
- Lower segment myometrium → Endometrium or Smooth muscle, depending on context

### 4. Preserve Supported Brain Subregions

For brain terms, retain supported subregions when clearly stated.

Examples:
- hippocampus → Brain: Hippocampal formation
- cerebellum → Brain: Cerebellum

### 5. Reduce Synonyms

Map synonyms and related tissue descriptors to the closest allowed category.

Examples:
- lymph node → Lymphoid tissue
- lymph nodes → Lymphoid tissue
- ovaries → Ovary
- iwat or inguinal white adipose tissue → Adipose tissue

### 6. Immune and Hematopoietic Cell Terms

If the input describes immune or hematopoietic cell populations without a specific anatomical source, map to the closest lineage-associated tissue category.

Examples:
- plasma cell → Lymphoid tissue
- lymphocyte → Lymphoid tissue

If a source tissue is explicitly provided, prioritize the source tissue.

Examples:
- bone marrow plasma cells → Bone marrow
- peripheral blood mononuclear cells → Blood

### 7. Handle Disease-Site Terms Carefully

If the term describes a tumor or disease site and the anatomical source is clear, map to the tissue of origin or sampled tissue.

Examples:
- melanoma → Skin
- breast tumor → Breast

If the tissue source is not clear, return `NA`.

### 8. Cell Lines and Culture Systems

If a term describes only a cell line, culture system, organoid, or engineered model without clear tissue origin, return `NA`.

If the tissue origin is explicitly clear, map to that tissue.

### 9. Xenograft and Implantation Sites

If the term describes only the implantation site rather than the biological tissue of origin, do not assign the implantation site unless it represents the sampled tissue.

Examples:
- subcutaneous tumor → NA unless the tissue origin is provided
- breast cancer xenograft → Breast if breast origin is clear

### 10. Use NA When Not Matchable

Return `NA` if the term cannot be confidently mapped to an allowed tissue category or supported brain subregion.

## Required Output Format

When used by the Stage 3 mapping script, return strict JSON only:

```json
{
  "mappings": [
    {
      "raw": "<original input term>",
      "mapped": "<controlled tissue term or NA>",
      "explanation": "<brief explanation>"
    }
  ]
}
```

## Notes

- Return one mapping per input term.
- Do not include categories outside the controlled vocabulary.
- Do not include extra text outside the JSON object.