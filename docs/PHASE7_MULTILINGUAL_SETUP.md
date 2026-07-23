# MedSenseAI Phase 7: Patient Info Fix + Hindi/English Patient View

## What changed

1. Fixed patient age/gender normalization.
   - If the LLM returns placeholders like `age` or `gender`, the backend now falls back to deterministic extraction from report text.
   - Example expected values: `21 Years`, `Male`.

2. Added patient-friendly multilingual report view.
   - English view remains available.
   - Hindi view provides simple Hindi/Hinglish explanations while preserving medical terms.
   - The original parsed data is not overwritten.

## New endpoint

```http
GET /api/reports/<report_id>/patient-view/?language=en
GET /api/reports/<report_id>/patient-view/?language=hi
```

## Recommended Postman flow

```http
POST /api/reports/knowledge/seed/
POST /api/reports/upload/
POST /api/reports/<id>/extract-text/
POST /api/reports/<id>/parse/
GET  /api/reports/<id>/
GET  /api/reports/<id>/patient-view/?language=en
GET  /api/reports/<id>/patient-view/?language=hi
GET  /api/reports/<id>/safety-audits/
```

## Notes

- This phase does not require new migrations because it adds a response endpoint instead of new database columns.
- The Hindi endpoint is designed for patient understanding, not medical diagnosis.
- Existing parsing, RAG, OCR, and safety audit behavior is preserved.
