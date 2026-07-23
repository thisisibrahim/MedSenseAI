# MedSenseAI

MedSenseAI is a safe medical report understanding assistant. It helps users upload medical reports, extract text using PDF parsing/OCR, parse structured lab values, generate patient-friendly explanations, ask doctor-focused questions, and apply safety guardrails so the app does not diagnose disease, prescribe medicine, suggest dosage, or replace a qualified doctor.

## Current Features

- Django + Django REST Framework backend
- React + Vite frontend
- PDF and image report upload
- Tesseract OCR support for scanned/image reports
- Gemini-first parsing with deterministic fallback parser
- RAG-style trusted medical knowledge context
- English and Hindi patient-friendly views
- Safety audit guardrails
- User login/register with token authentication
- Private report history per user
- Printable patient summary PDF through browser print/save flow
- Interactive frontend tour using React Joyride

## Tech Stack

### Backend

- Python
- Django 6
- Django REST Framework
- DRF Token Authentication
- pdfplumber / pdfminer / PyMuPDF / pypdfium2
- Pillow
- pytesseract
- Google Gemini API
- LangChain + langchain-google-genai
- SQLite for local development

### Frontend

- React
- Vite
- lucide-react
- react-joyride

## Project Flow

```text
User logs in
↓
Uploads PDF / JPG / PNG / scanned report
↓
Backend extracts text using PDF parser or OCR
↓
Gemini parser attempts structured extraction
↓
Fallback parser handles single-line, multiline, and table-like OCR formats
↓
RAG knowledge context is retrieved for each test
↓
Patient-friendly explanation is generated
↓
Safety audit checks unsafe medical claims
↓
Frontend displays summary, test cards, doctor questions, sources, Hindi view, and PDF export
```

## Project Structure

```text
MedSenseAI/
├── backend/
│   ├── manage.py
│   ├── medsense/
│   ├── reports/
│   ├── accounts/
│   ├── ai_engine/
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       ├── styles.css
│       └── services/api.js
├── README.md
├── .env.example
└── .gitignore
```

## Safety Boundaries

MedSenseAI is intentionally designed as an educational report-understanding tool.

It does not:

- Diagnose disease
- Prescribe medicine
- Suggest dosage
- Replace a qualified doctor
- Guarantee that OCR/parser output is medically complete
- Provide emergency medical decisions

Users should consult a qualified healthcare professional before making medical decisions.

## Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

For PowerShell activation:

```powershell
.\.venv\Scripts\Activate.ps1
```

For macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Backend runs at:

```text
http://127.0.0.1:8000/
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at:

```text
http://localhost:5173/
```

## Environment Variables

Create this file:

```text
backend/.env
```

Use `.env.example` as the reference.

Minimum values:

```env
SECRET_KEY=replace-with-your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

GOOGLE_API_KEY=replace-with-your-google-ai-studio-api-key
GEMINI_MODEL=gemini-1.5-flash

TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
OCR_DPI=300
LANGCHAIN_VERBOSE=false
```

## API Endpoints

### Auth

```text
POST /api/auth/register/
POST /api/auth/login/
GET  /api/auth/me/
POST /api/auth/logout/
```

### Reports

```text
POST /api/reports/upload/
GET  /api/reports/
GET  /api/reports/<report_id>/
POST /api/reports/<report_id>/extract-text/
POST /api/reports/<report_id>/parse/
GET  /api/reports/<report_id>/patient-view/?language=en
GET  /api/reports/<report_id>/patient-view/?language=hi
GET  /api/reports/<report_id>/safety-audits/
```

### Knowledge Base

```text
GET  /api/reports/knowledge/
POST /api/reports/knowledge/seed/
```

## Authentication

The frontend stores the DRF token in localStorage:

```text
medsenseai_auth_token
```

Authenticated API requests include:

```text
Authorization: Token <token>
```

Report history is filtered by logged-in user.

## Tesseract OCR Notes

For image/scanned reports, Tesseract must be installed.

Check installation:

```bash
tesseract --version
```

On Windows, set:

```env
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
```

## Demo Flow

1. Open frontend.
2. Register or login.
3. Upload a PDF/JPG/PNG medical report.
4. Click `Process report safely`.
5. Wait for knowledge seed, upload, OCR extraction, parsing, RAG explanation, and safety audit.
6. Review parsed tests, needs-attention values, patient summary, doctor questions, sources, and OCR text.
7. Switch to Hindi if needed.
8. Print/save the patient summary as PDF.

## Common Issues

### `No module named django`

The virtual environment is not activated or requirements are not installed.

```bash
pip install -r requirements.txt
```

### `no such table: authtoken_token`

Token authentication migrations are missing.

```bash
python manage.py migrate
```

### `Tesseract OCR failed`

Tesseract desktop binary is missing or path is wrong.

```env
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
```

### Gemini `401 UNAUTHENTICATED`

The Gemini API key is missing, invalid, or not being read from `.env`.

```env
GOOGLE_API_KEY=your-valid-key
```

Restart backend after changing `.env`.

## Docker Plan

Dockerization is planned for a later phase.

Target Docker services:

```text
backend   Django + DRF + Tesseract
frontend  React + Vite
db        PostgreSQL
```

Docker will remove repeated local setup issues, especially for Tesseract and environment differences.

## Resume Description

MedSenseAI is a full-stack AI medical report understanding assistant built with Django REST Framework and React. It extracts text from PDF/image reports using OCR, parses structured test values using Gemini and fallback parsers, grounds explanations through trusted medical knowledge, supports English/Hindi patient views, applies medical safety guardrails, and provides user-specific private report history.

## Disclaimer

MedSenseAI is for educational and report-understanding purposes only. It is not a medical device and must not be used for diagnosis, treatment, dosage decisions, or emergency medical advice.
