# MedSenseAI Phase 6 — OCR Setup

Phase 6 adds OCR extraction for image reports and scanned PDFs.

## Supported files

- Digital PDFs: extracted with `pdfplumber`
- Scanned PDFs: rendered with `PyMuPDF`, then OCR is applied
- Images: JPG, JPEG, PNG, WEBP, BMP, TIFF

## Python package

The project uses:

```bash
pip install pytesseract
```

This is already included in `requirements.txt`.

## Important Windows requirement

`pytesseract` is only a Python wrapper. You must also install the Tesseract OCR desktop binary on Windows.

After installing Tesseract, set this in `backend/.env` if needed:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
OCR_DPI=200
```

If Tesseract is added to PATH, `TESSERACT_CMD` can be left blank.

## Test flow in Postman

Use the same API flow:

```text
POST /api/reports/upload/
POST /api/reports/<id>/extract-text/
POST /api/reports/<id>/parse/
GET  /api/reports/<id>/
```

Now the uploaded report can be a PDF or image.
