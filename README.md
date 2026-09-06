# MedSenseAI

**MedSenseAI** is a safe AI-powered medical report understanding assistant. It helps users upload medical reports, extract test values, understand results in simple language, and prepare better questions for a doctor.

> MedSenseAI explains reports. It does **not** diagnose disease, prescribe medicine, suggest dosage, or replace a qualified doctor.

---

## GitHub Description

Safe AI medical report understanding assistant built with Django REST Framework, React, OCR, Gemini, LangChain, RAG-style retrieval, multilingual explanations, safety guardrails, authentication, and private report history.

---

## What It Does

- Upload PDF, image, and scanned medical reports
- Extract text using OCR
- Parse lab values from real-world report formats
- Explain results in simple English and Hindi
- Highlight values that need attention
- Generate questions to ask a doctor
- Show trusted medical context using RAG-style retrieval
- Run safety checks to avoid unsafe medical claims
- Keep private report history for each logged-in user
- Protect uploaded report files behind authenticated, owner-only download endpoints
- Store medical report files under randomized UUID-based filenames
- Export a patient-friendly PDF summary

---

## Why I Built This

Many people receive medical reports but do not understand what the numbers, units, flags, and reference ranges mean.

MedSenseAI was built to make reports easier to understand while staying safe and responsible. It is not a doctor replacement. It helps users understand their reports better and ask more informed questions during consultation.

---

## Key Features

### Report Upload

Users can upload:

- Digital PDFs
- Scanned PDFs
- JPG/PNG images
- Medical report screenshots

### OCR and Text Extraction

The backend extracts text using:

- `pdfplumber` for digital PDFs
- `PyMuPDF` for scanned PDF rendering
- `Pillow` for image preprocessing
- `Tesseract OCR` for scanned/image reports

Image preprocessing improves OCR quality using grayscale conversion, contrast enhancement, sharpening, and thresholding.

### Gemini + Fallback Parser

MedSenseAI uses Gemini for structured extraction first. If Gemini fails or the report is too messy, the deterministic fallback parser takes over.

The parser supports:

- CBC reports
- Biochemistry reports
- Kidney Function Tests
- Liver Function Tests
- Lipid Profiles
- Electrolyte panels
- Single-line report formats
- Multiline OCR formats
- Table-like report formats
- Short aliases such as Hb, TLC, Na, K, Mg, ALT, AST, HDL, LDL

### RAG-Style Medical Knowledge Retrieval

For each parsed test, the app retrieves trusted medical context from stored knowledge documents. This helps generate safer and more grounded explanations.

### Safety Guardrails

MedSenseAI includes rule-based safety checks to avoid:

- Diagnosis claims
- Prescription advice
- Dosage suggestions
- False reassurance
- Statements that discourage doctor consultation

### Authentication and Privacy

The app uses DRF Token Authentication.

Each user has:

- Register
- Login
- Logout
- Private report uploads
- Private report history
- Authenticated report-file downloads

Medical report files are no longer exposed through Django's public `/media/` route.

Uploaded files are stored with randomized UUID-based filenames, while the original filename is preserved separately for user-facing downloads.

Users can only download files that belong to their own account through an ownership-checked API endpoint.

Users cannot see or download reports uploaded by other users.

### English and Hindi Views

Users can switch between English and Hindi patient-friendly explanations.

### PDF Summary Export

Users can export a patient-friendly report summary as a PDF using the browser print/save flow.

---

## Tech Stack

### Backend

- Python
- Django
- Django REST Framework
- DRF Token Authentication
- Pydantic
- Gemini API
- LangChain
- Tesseract OCR
- Pillow
- pdfplumber
- PyMuPDF
- SQLite for local development

### Frontend

- React
- Vite
- JavaScript
- CSS
- lucide-react
- react-joyride

### DevOps / Tooling

- Git
- GitHub
- Dockerfile
- Docker Compose
- `.env.example`
- `.gitignore`

---

## Architecture

```text
User
 ↓
React + Vite Frontend
 ↓
Django REST API
 ↓
Report Upload
 ↓
PDF/Image Text Extraction
 ↓
OCR Preprocessing + Tesseract
 ↓
Gemini Structured Parser
 ↓
Fallback Multi-Pattern Parser
 ↓
RAG-Style Knowledge Retrieval
 ↓
Patient Explanation Generator
 ↓
Safety Guardrail Review
 ↓
English/Hindi Patient View
 ↓
Private Report Storage
 ↓
Authenticated Owner-Only Download
 ↓
Report History + PDF Export
```

---

## Project Structure

```text
MedSenseAI/
├── backend/
│   ├── accounts/
│   ├── ai_engine/
│   ├── medsense/
│   ├── reports/
│   ├── manage.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── services/api.js
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── package.json
│   └── Dockerfile
│
├── docs/
├── docker-compose.yml
├── README.md
├── .env.example
└── .gitignore
```

---

## Local Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

For PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Backend runs at:

```text
http://127.0.0.1:8000/
```

### Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at:

```text
http://localhost:5173/
```

---

## Environment Variables

Create this file:

```text
backend/.env
```

Use `.env.example` as reference:

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

---

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
GET  /api/reports/<report_id>/download/
POST /api/reports/<report_id>/extract-text/
POST /api/reports/<report_id>/parse/
GET  /api/reports/<report_id>/patient-view/?language=en
GET  /api/reports/<report_id>/patient-view/?language=hi
GET  /api/reports/<report_id>/safety-audits/
```

The download endpoint requires authentication and verifies report ownership before serving the file.


### Knowledge Base

```text
GET  /api/reports/knowledge/
POST /api/reports/knowledge/seed/
```

---

## Secure Report File Handling

Medical reports may contain sensitive personal information, so uploaded files are treated as private application data.

Current protections include:

- Direct Django `/media/` serving is disabled for medical report files
- Uploaded files are stored using randomized UUID-based filenames
- Original filenames are stored separately for user-facing downloads
- Raw file URLs are not exposed through the report serializer
- Files are downloaded through:

```text
GET /api/reports/<report_id>/download/
```

- The download endpoint requires authentication
- Ownership is checked before the file is returned
- Cross-user access returns `404`
- Anonymous access is blocked

The backend includes security tests for owner access, anonymous access, cross-user access, direct `/media/` access, serializer exposure, and randomized storage filenames.

---

## Demo Flow

1. Open the app
2. Register or login
3. Upload a medical report
4. Click `Process report safely`
5. Wait for OCR, parsing, explanation, and safety audit
6. View parsed test cards
7. Check values that need attention
8. Switch between English and Hindi
9. Review doctor questions and trusted sources
10. Export the patient summary as PDF

---

## Why Not Publicly Deployed Yet

MedSenseAI handles medical report uploads, which may contain sensitive personal data.

The project is Docker-ready and deployment-ready. Uploaded medical reports are now protected from direct public `/media/` access, stored under randomized filenames, and served only through authenticated owner-only download endpoints.

A production deployment should additionally include a secure production database, private object/media storage, HTTPS, environment secret management, monitoring, retention policies, and cleanup of uploaded files.

For now, the project is demonstrated locally with GitHub documentation and a demo video.

---

## Future Scope

- Production deployment with Render/Railway/VPS
- PostgreSQL database
- Secure cloud file storage
- Better OCR for low-quality images
- More report types and lab formats
- Doctor/admin review dashboard
- Report comparison over time
- Better multilingual support
- Real OAuth login
- Broader automated test coverage across OCR, parsing, safety, and frontend flows

---

## Contribution

Contributions, suggestions, and improvements are welcome.

Possible areas to improve:

- Parser support for more report formats
- OCR accuracy
- UI/UX polish
- Medical safety checks
- Documentation
- Deployment setup
- Broader automated test coverage

If you find something that can be improved, feel free to open an issue or submit a pull request.

---

## Disclaimer

MedSenseAI is an educational report-understanding assistant.

It does not diagnose disease, prescribe medicine, suggest dosage, or replace a qualified doctor.

Always consult a qualified healthcare professional before making medical decisions based on any medical report.
