# MedSenseAI

Safe medical report understanding assistant for rural and non-technical users.

MedSenseAI helps users understand medical reports, identify abnormal values, view patient-friendly explanations, and prepare better questions for a doctor. It is not a diagnosis or treatment system.

## Current capabilities

- PDF report upload
- Image/scanned report OCR support
- CBC structured parsing
- LangChain + Gemini structured extraction with regex fallback
- Risk triage: green/yellow/orange/red
- Trusted medical knowledge base
- RAG-style explanations with source tracking
- Safety audit guardrails
- English/Hindi patient-friendly view
- React frontend dashboard

## Run backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```
