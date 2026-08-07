# GEOMeta Runtime Artifacts

This directory stores runtime-generated outputs, caches, logs, review files,
and audit records.

Typical runtime subdirectories include:

- `outputs/`: intermediate and final pipeline outputs
- `logs/`: execution logs
- `geo_cache/`: cached GEO metadata
- `mapping_cache/`: reusable runtime mapping caches
- `debug/` and `debug_llm_raw/`: debugging records and raw model responses
- `review_queue/`: records requiring additional review
- `manual_review/`: manually reviewed correction files
- `novel_terms/`: previously unseen metadata terms
- `ledgers/`: processing and review ledgers
- `runs/`: run-specific records
- `memory/`: persistent runtime memory resources

These subdirectories are created or populated during pipeline execution and
are excluded from version control by default. Curated mapping resources used
by the released pipeline are maintained separately under `mappings/`.