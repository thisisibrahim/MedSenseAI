# MedSenseAI Setup Commands

## Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

## Verify Tesseract

```bash
tesseract --version
```

## Verify Django reads Gemini settings

```bash
python manage.py shell
```

```python
from django.conf import settings
print(settings.GOOGLE_API_KEY[:8])
print(settings.GEMINI_MODEL)
```
