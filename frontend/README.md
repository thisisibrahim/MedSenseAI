# MedSenseAI Frontend

React + Vite frontend for MedSenseAI.

## What it does

- Uploads PDF/image medical reports
- Triggers backend pipeline automatically:
  1. Seed trusted knowledge base
  2. Upload report
  3. Extract text / OCR
  4. Parse structured test results
  5. Load patient-friendly view
  6. Load safety audit
- Shows risk level, parsed tests, RAG explanation sources, doctor questions, and Hindi/English patient view

## Run backend first

```bash
cd ../backend
source .venv/Scripts/activate
python manage.py runserver
```

Backend should run on:

```text
http://127.0.0.1:8000
```

## Run frontend

Open a new terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend will run on:

```text
http://127.0.0.1:5173
```

The Vite dev server proxies `/api` and `/media` to Django, so no CORS setup is needed for local development.
