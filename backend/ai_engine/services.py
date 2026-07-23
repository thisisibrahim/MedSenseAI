import io
import json
import re
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps
import pytesseract

import pdfplumber
from django.conf import settings

from .schemas import ParsedMedicalReport, ParsedTestResult


class PDFTextExtractionService:
    """
    Extracts text from medical reports.

    Supported now:
    - Digital PDFs through pdfplumber
    - Scanned PDFs through OCR fallback
    - Image reports: JPG, JPEG, PNG, WEBP, BMP, TIFF

    Notes:
    - OCR uses pytesseract, which also requires the Tesseract desktop binary.
    - On Windows, install Tesseract and optionally set TESSERACT_CMD in .env.
    """

    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    PDF_EXTENSIONS = {".pdf"}

    @classmethod
    def extract_text(cls, file_path: str) -> str:
        suffix = Path(file_path).suffix.lower()

        if suffix in cls.PDF_EXTENSIONS:
            return cls._extract_from_pdf(file_path)

        if suffix in cls.IMAGE_EXTENSIONS:
            return cls._extract_from_image(file_path)

        raise ValueError(
            "Unsupported report file type. Please upload a PDF, JPG, JPEG, PNG, WEBP, BMP, or TIFF file."
        )

    @classmethod
    def _extract_from_pdf(cls, file_path: str) -> str:
        digital_text = cls._extract_digital_pdf_text(file_path)

        # If a PDF contains selectable text, prefer it.
        # If it is scanned, pdfplumber may return empty/very small text, so OCR is used as fallback.
        if cls._has_enough_text(digital_text):
            return digital_text

        ocr_text = cls._extract_scanned_pdf_with_ocr(file_path)
        return ocr_text or digital_text

    @staticmethod
    def _extract_digital_pdf_text(file_path: str) -> str:
        extracted_pages = []

        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if text.strip():
                        extracted_pages.append(text.strip())

            return "\n\n".join(extracted_pages).strip()

        except Exception as exc:
            raise ValueError(f"PDF text extraction failed: {str(exc)}")

    @staticmethod
    def _has_enough_text(text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text or "").strip()
        return len(normalized) >= 80

    @classmethod
    def _extract_from_image(cls, file_path: str) -> str:
        try:
            image = Image.open(file_path)
            return cls._run_ocr(image).strip()
        except Exception as exc:
            raise ValueError(f"Image OCR extraction failed: {str(exc)}")

    @classmethod
    def _extract_scanned_pdf_with_ocr(cls, file_path: str) -> str:
        try:
            import fitz  # PyMuPDF
            from PIL import Image
        except Exception as exc:
            raise ValueError(
                "Scanned PDF OCR requires PyMuPDF and Pillow. Install requirements.txt and try again. "
                f"Details: {str(exc)}"
            )

        extracted_pages = []
        dpi = int(getattr(settings, "OCR_DPI", 200))
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)

        try:
            document = fitz.open(file_path)
            for page_index in range(document.page_count):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image_bytes = pixmap.tobytes("png")
                image = Image.open(io.BytesIO(image_bytes))
                text = cls._run_ocr(image)
                if text.strip():
                    extracted_pages.append(text.strip())

            document.close()
            return "\n\n".join(extracted_pages).strip()

        except Exception as exc:
            raise ValueError(f"Scanned PDF OCR extraction failed: {str(exc)}")

    @classmethod
    def _preprocess_image_for_ocr(cls, image: Image.Image) -> list[Image.Image]:
        """
        Build several OCR-friendly variants from a phone/scanned medical report image.

        Why multiple variants?
        - Some reports work better with grayscale + contrast.
        - Some table-heavy reports work better with black/white thresholding.
        - Some watermarked reports lose text if thresholding is too aggressive.
        """
        image = ImageOps.exif_transpose(image)

        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")

        width, height = image.size

        # Upscale small/phone images. Tesseract usually reads lab tables better
        # when the longest side is around 2200-2800px.
        longest_side = max(width, height)
        if longest_side < 2200:
            scale = min(3, max(2, round(2400 / max(longest_side, 1))))
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            image = image.resize((width * scale, height * scale), resampling)

        grayscale = ImageOps.grayscale(image)
        autocontrast = ImageOps.autocontrast(grayscale)
        denoised = autocontrast.filter(ImageFilter.MedianFilter(size=3))
        sharpened = denoised.filter(ImageFilter.SHARPEN)

        # Two thresholds because medical reports have different background/watermark intensity.
        threshold_soft = sharpened.point(lambda pixel: 255 if pixel > 150 else 0)
        threshold_hard = sharpened.point(lambda pixel: 255 if pixel > 180 else 0)

        return [
            sharpened,
            threshold_soft,
            threshold_hard,
        ]

    @staticmethod
    def _score_ocr_text(text: str) -> int:
        """Score OCR output by how useful it looks for medical report parsing."""
        lower_text = (text or "").lower()

        keywords = [
            "hemoglobin", "haemoglobin", "hb",
            "wbc", "rbc", "tlc", "platelet",
            "neutrophil", "lymphocyte", "monocyte", "eosinophil", "basophil",
            "esr", "erythrocyte", "sedimentation",
            "reference", "range", "result", "unit", "status",
            "complete blood", "cbc", "hemogram", "pathology",
            "biochemistry", "glucose", "urea", "creatinine", "uric acid",
            "sodium", "potassium", "chloride", "calcium", "phosphorous", "phosphorus",
            "magnesium", "albumin", "total protein", "cholesterol", "triglycerides",
            "bilirubin", "sgpt", "sgot", "alt", "ast", "alkaline phosphatase",
        ]

        keyword_score = sum(12 for keyword in keywords if keyword in lower_text)
        numeric_score = len(re.findall(r"\d+(?:\.\d+)?", text or ""))
        line_score = min(len([line for line in (text or "").splitlines() if line.strip()]), 80)

        return keyword_score + numeric_score + line_score

    @classmethod
    def _run_ocr(cls, image) -> str:
        try:
            import pytesseract
        except Exception as exc:
            raise ValueError(
                "pytesseract is not installed. Run: pip install pytesseract"
            ) from exc

        tesseract_cmd = getattr(settings, "TESSERACT_CMD", "")
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        try:
            processed_images = cls._preprocess_image_for_ocr(image)

            # PSM 6: single uniform block; good for rows/columns.
            # PSM 4: single column; sometimes better for lab report sections.
            # PSM 11: sparse text; useful for noisy phone photos.
            configs = [
                "--oem 3 --psm 6",
                "--oem 3 --psm 4",
                "--oem 3 --psm 11",
            ]

            candidates: list[str] = []

            for processed_image in processed_images:
                for config in configs:
                    text = pytesseract.image_to_string(
                        processed_image,
                        config=config,
                    ).strip()

                    if text:
                        candidates.append(text)

            if not candidates:
                return ""

            return max(candidates, key=cls._score_ocr_text)

        except Exception as exc:
            raise ValueError(
                "Tesseract OCR failed. Install the Tesseract desktop binary and set TESSERACT_CMD in .env if needed. "
                f"Details: {str(exc)}"
            )


class MedicalReportParserService:
    """
    Converts extracted report text into structured medical test results.

    Parser strategy:
    1. Try LangChain + Gemini structured output when GOOGLE_API_KEY is configured.
    2. If Gemini fails or returns empty, use a deterministic multi-pattern fallback:
       - single-line lab rows
       - multiline OCR rows
       - table-like stacked OCR rows
       - known CBC test-name windows
       - biochemistry/KFT/LFT/lipid/electrolyte windows

    This prevents the app from depending on one lab-report layout.
    """

    KNOWN_FLAGS = {"LOW", "HIGH", "BORDERLINE", "NORMAL", "L", "H"}
    KNOWN_UNITS = {
        "g/dL", "g/dl", "gm%", "mg/dL", "mmol/L", "mEq/L", "IU/L", "U/L",
        "%", "fL", "fl", "pg", "Pg", "cumm", "cmm", "/cumm", "/cmm",
        "cells/cumm", "million/cumm", "million/cmm", "mill/cumm", "mill/cmm",
        "millionfcumm", "lakhs/cumm", "lakh/cumm", "lakhs/cmm", "lakh/cmm",
        "10^3/uL", "10^3/ul", "10^6/uL", "10^6/ul", "x10^3/uL", "x10^3/ul",
        "ng/mL", "uIU/mL", "µIU/mL", "mcIU/mL", "mm/hr",
        "mmol/L", "mmol/l", "mmol/t", "mmoi/l", "mmoi/i", "mol/L",
        "umol/L", "µmol/L", "tumol/L", "jamol/L", "g/L", "g/l", "g/t", "e/t",
        "U/L", "IU/L", "u/l", "iu/l",
    }

    CBC_TEST_ALIASES = [
        ("MCHC", [
            "mean cell haemoglobin con", "mean cell hemoglobin con",
            "mean corpuscular hemoglobin concentration", "mean corpuscular haemoglobin concentration",
            "mchc",
        ]),
        ("MCH", [
            "mean cell haemoglobin", "mean cell hemoglobin",
            "mean corpuscular hemoglobin", "mean corpuscular haemoglobin",
            "mch",
        ]),
        ("Mean Corpuscular Volume (MCV)", [
            "mean corpuscular volume", "mcv",
        ]),
        ("Hematocrit / Packed Cell Volume (HCT/PCV)", [
            "hematocrit value", "hematocrit", "hct", "packed cell volume", "pcv",
        ]),
        ("Total WBC count", [
            "total leukocyte count", "total leucocyte count", "total wbc count",
            "white blood cell count", "wbc count", "tlc",
        ]),
        ("Total RBC count", [
            "total rbc count", "rbc count", "red blood cell count", "rbcs count",
        ]),
        ("Platelet Count", [
            "platelet count", "platelets count", "platelets", "platelet",
        ]),
        ("Neutrophils", [
            "neutrophils", "neutrophil",
        ]),
        ("Lymphocytes", [
            "lymphocytes", "lymphocyte",
        ]),
        ("Eosinophils", [
            "eosinophils", "eosinophil",
        ]),
        ("Monocytes", [
            "monocytes", "monocyte",
        ]),
        ("Basophils", [
            "basophils", "basophil", "basophiles",
        ]),
        ("ESR", [
            "erythrocyte sedimentation rate", "esr",
        ]),
        ("Hemoglobin", [
            "haemoglobin", "hemoglobin", "hemoglobin hb", "haemoglobin hb", "hb",
        ]),
    ]

    GENERAL_TEST_ALIASES = [
        ("Glucose", [
            "glucose", "blood glucose", "random glucose", "fasting glucose", "fbs",
            "blood sugar", "sugar",
        ]),
        ("Urea", [
            "urea", "blood urea",
        ]),
        ("Creatinine", [
            "creatinine", "serum creatinine",
        ]),
        ("Sodium (Na)", [
            "sodium", "na",
        ]),
        ("Potassium (K)", [
            "potassium", "k",
        ]),
        ("Chloride", [
            "chloride", "cl",
        ]),
        ("Calcium", [
            "calcium",
        ]),
        ("Calcium - adjusted", [
            "calcium adjusted", "calcium - adjusted", "adjusted calcium", "corrected calcium",
        ]),
        ("Phosphorous", [
            "phosphorous", "phosphorus", "phosphate", "po4",
        ]),
        ("Magnesium (Mg)", [
            "magnesium", "mg",
        ]),
        ("Albumin", [
            "albumin",
        ]),
        ("Total Protein", [
            "total protein", "protein total",
        ]),
        ("Uric Acid", [
            "uric acid", "urate",
        ]),
        ("Cholesterol", [
            "cholesterol", "total cholesterol",
        ]),
        ("Triglycerides", [
            "triglycerides", "triglyceride", "tg",
        ]),
        ("HDL Cholesterol", [
            "hdl", "hdl cholesterol",
        ]),
        ("LDL Cholesterol", [
            "ldl", "ldl cholesterol",
        ]),
        ("VLDL Cholesterol", [
            "vldl", "vldl cholesterol",
        ]),
        ("Total Bilirubin", [
            "total bilirubin", "bilirubin total",
        ]),
        ("Direct Bilirubin", [
            "direct bilirubin", "bilirubin direct",
        ]),
        ("Indirect Bilirubin", [
            "indirect bilirubin", "bilirubin indirect",
        ]),
        ("ALT / SGPT", [
            "alt", "sgpt", "alanine aminotransferase",
        ]),
        ("AST / SGOT", [
            "ast", "sgot", "aspartate aminotransferase",
        ]),
        ("Alkaline Phosphatase (ALP)", [
            "alkaline phosphatase", "alp",
        ]),
        ("GGT", [
            "ggt", "gamma glutamyl transferase", "gamma gt",
        ]),
        ("HbA1c", [
            "hba1c", "glycated hemoglobin", "glycosylated hemoglobin",
        ]),
        ("TSH", [
            "tsh", "thyroid stimulating hormone",
        ]),
        ("T3", [
            "t3", "triiodothyronine",
        ]),
        ("T4", [
            "t4", "thyroxine",
        ]),
    ]

    HEADER_OR_NOISE_TERMS = {
        "test", "value", "unit", "units", "reference", "reference range", "range", "status",
        "haematology", "hematology", "complete blood count", "cbc",
        "differential leucocyte count", "differential leukocyte count",
        "clinical notes", "possible causes", "high", "low", "ow",
        "biochemistry", "remark", "remarks", "flag",
    }

    @classmethod
    def parse(cls, extracted_text: str) -> ParsedMedicalReport:
        cleaned_text = cls._clean_text(extracted_text)

        if not cleaned_text:
            return ParsedMedicalReport(
                report_type="Unknown",
                tests=[],
                parser_mode="empty_text",
                parser_message="No extracted text was available for parsing.",
            )

        if getattr(settings, "GOOGLE_API_KEY", ""):
            try:
                parsed = cls._parse_with_langchain_gemini(cleaned_text)
                parsed = cls._repair_patient_info_from_text(parsed, cleaned_text)
                parsed.parser_mode = "gemini"
                parsed.parser_message = f"Gemini structured extraction returned {len(parsed.tests)} test result(s)."

                if parsed.tests:
                    return parsed

                fallback = cls._parse_with_regex(cleaned_text)
                fallback.parser_mode = "gemini_empty_regex_fallback"
                fallback.parser_message = (
                    f"Gemini returned no tests; multi-pattern fallback returned {len(fallback.tests)} test result(s)."
                )
                return fallback

            except Exception as exc:
                fallback = cls._parse_with_regex(cleaned_text)
                fallback.parser_mode = "gemini_failed_regex_fallback"
                fallback.parser_message = (
                    f"Gemini failed; multi-pattern fallback returned {len(fallback.tests)} test result(s). "
                    f"Gemini error: {str(exc)[:220]}"
                )
                return fallback

        parsed = cls._parse_with_regex(cleaned_text)
        parsed.parser_mode = "no_api_key_multi_pattern_fallback"
        parsed.parser_message = (
            f"GOOGLE_API_KEY is not configured. Multi-pattern fallback returned {len(parsed.tests)} test result(s)."
        )
        return parsed

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"\r", "\n", text or "")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"[|•]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _normalize_key(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

    @classmethod
    def _all_test_aliases(cls) -> list[tuple[str, list[str]]]:
        return cls.CBC_TEST_ALIASES + cls.GENERAL_TEST_ALIASES

    @classmethod
    def _canonical_test_name_from_line(cls, line: str) -> str:
        normalized_line = cls._normalize_key(line)
        if not normalized_line:
            return ""

        # Prefer longer aliases first so "calcium - adjusted" wins over "calcium".
        alias_pairs: list[tuple[str, str]] = []
        for canonical, aliases in cls._all_test_aliases():
            for alias in aliases:
                alias_key = cls._normalize_key(alias)
                if alias_key:
                    alias_pairs.append((canonical, alias_key))

        alias_pairs.sort(key=lambda item: len(item[1]), reverse=True)

        for canonical, alias_key in alias_pairs:
            # Short aliases like Na/K/Mg/ALT/AST should match only as clean tokens,
            # not inside patient names, addresses, or random OCR fragments.
            if len(alias_key) <= 3:
                if re.search(rf"(^|\s){re.escape(alias_key)}(\s|$)", normalized_line):
                    # Avoid false positives on long noisy lines unless the line starts with the token.
                    if len(normalized_line.split()) <= 5 or normalized_line.startswith(alias_key):
                        return canonical
                continue

            if alias_key in normalized_line:
                return canonical

        return ""


    @staticmethod
    def _extract_patient_info(text: str) -> dict:
        age = ""
        gender = ""

        age_sex_patterns = [
            r"Age\s*/\s*Sex\s*[:\-]?\s*([0-9]{1,3}\s*(?:Years?|Yrs?|Yr)?)\s*/\s*(Male|Female|Other|M|F)\b",
            r"AGE\s*\\\s*SEX\s*[:\-]?\s*([0-9]{1,3}\s*(?:Years?|Yrs?|Yr)?)\s*\\?\s*(Male|Female|Other|M|F|FE(?:MALE)?)\b",
        ]

        for pattern in age_sex_patterns:
            match = re.search(pattern, text or "", re.IGNORECASE)
            if match:
                age = match.group(1).strip()
                raw_gender = match.group(2).strip().lower()
                if raw_gender in {"m", "male"}:
                    gender = "Male"
                elif raw_gender in {"f", "fe", "female"}:
                    gender = "Female"
                else:
                    gender = raw_gender.title()
                return {"age": age, "gender": gender}

        age_patterns = [
            r"Age\s*[:\\/\-]?\s*([0-9]{1,3}\s*(?:Years?|Yrs?|Yr)?)",
            r"AGE\s*\\\s*SEX\s*[:\-]?\s*([0-9]{1,3}\s*(?:Years?|Yrs?|Yr)?)",
        ]
        for pattern in age_patterns:
            age_match = re.search(pattern, text or "", re.IGNORECASE)
            if age_match:
                age = age_match.group(1).strip()
                break

        gender_patterns = [
            r"(?:Sex|Gender)\s*[:\\/\-]?\s*(Male|Female|Other|M|F)\b",
            r"\b([0-9]{1,3}\s*(?:Years?|Yrs?|Yr)?)\s*/\s*(Male|Female|Other|M|F)\b",
        ]
        for pattern in gender_patterns:
            gender_match = re.search(pattern, text or "", re.IGNORECASE)
            if gender_match:
                raw_gender = gender_match.group(gender_match.lastindex).strip().lower()
                if raw_gender in {"m", "male"}:
                    gender = "Male"
                elif raw_gender in {"f", "fe", "female"}:
                    gender = "Female"
                else:
                    gender = raw_gender.title()
                break

        return {"age": age, "gender": gender}

    @classmethod
    def _repair_patient_info_from_text(cls, parsed_report: ParsedMedicalReport, text: str) -> ParsedMedicalReport:
        patient_info = cls._extract_patient_info(text)

        invalid_age_values = {"", "age", "patient age", "unknown", "not available", "na", "n/a"}
        invalid_gender_values = {"", "gender", "sex", "patient gender", "unknown", "not available", "na", "n/a"}

        parsed_age = (parsed_report.patient_age or "").strip()
        parsed_gender = (parsed_report.patient_gender or "").strip()

        if parsed_age.lower() in invalid_age_values:
            parsed_report.patient_age = patient_info.get("age", "")

        if parsed_gender.lower() in invalid_gender_values:
            parsed_report.patient_gender = patient_info.get("gender", "")

        return parsed_report

    @classmethod
    def _parse_with_langchain_gemini(cls, text: str) -> ParsedMedicalReport:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash"),
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0,
        )

        structured_llm = llm.with_structured_output(ParsedMedicalReport)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
You are MedSenseAI's medical report parser. Extract data only. Do not diagnose or advise treatment.

You must handle noisy OCR text and varied Indian lab formats, including:
- single-line rows: Hemoglobin 12.5 LOW 13.0 - 17.0 g/dL
- table rows: Total Leucocyte Count 5,100 /cmm 4,000 - 10,000
- stacked OCR rows:
  HEMOGLOBIN
  15
  13-17
  g/dl

Extraction rules:
- Return only values present in the report text.
- Extract patient_age and patient_gender if visible.
- Normalize obvious test names: Haemoglobin -> Hemoglobin, TLC -> Total WBC count.
- value is the observed/measured value only.
- unit is the printed unit only.
- LOW, HIGH, BORDERLINE, L, H, NORMAL are flags, not units.
- reference_range is the printed range.
- If no LOW/HIGH flag is printed, compare numeric value with reference range.
- status must be one of: low, normal, high, borderline, unknown.
- Preserve units such as gm%, g/dL, /cmm, cumm, lakhs/cumm, million/cumm, %, fL, pg, mm/hr.
- Ignore lab address, doctor name, QR, remarks, phone numbers, registration numbers, dates, signatures.
                    """,
                ),
                (
                    "human",
                    "Extract structured medical report data from this OCR/PDF text:\n\n{report_text}",
                ),
            ]
        )

        chain = prompt | structured_llm
        parsed = chain.invoke({"report_text": text[:20000]})

        if isinstance(parsed, dict):
            parsed = ParsedMedicalReport.model_validate(parsed)

        return cls._normalize_parsed_report(parsed)

    @classmethod
    def _parse_with_gemini(cls, text: str) -> ParsedMedicalReport:
        """Legacy direct Gemini parser kept as backup if needed."""
        import google.generativeai as genai

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash"))

        prompt = f"""
You are MedSenseAI, a safe medical report understanding assistant.

Task: Extract structured data from the medical report text.

Rules:
- Do not diagnose.
- Do not prescribe medicine.
- Do not add values not present in the report.
- Return JSON only. No markdown.
- If a field is missing, use an empty string.
- Separate flag from unit. LOW, HIGH, BORDERLINE, L, H are flags, not units.
- Status must be one of: low, normal, high, borderline, unknown.

JSON schema:
{{
  "report_type": "Complete Blood Count / Liver Function Test / Kidney Function Test / Thyroid Profile / Lipid Profile / Diabetes Report / Unknown",
  "patient_age": "",
  "patient_gender": "",
  "tests": [
    {{
      "test_name": "Hemoglobin",
      "value": "10.2",
      "flag": "LOW",
      "unit": "g/dL",
      "reference_range": "13.0-17.0",
      "status": "low"
    }}
  ]
}}

Report text:
{text[:12000]}
"""
        response = model.generate_content(prompt)
        raw = getattr(response, "text", "") or ""
        data = cls._extract_json(raw)
        parsed = ParsedMedicalReport.model_validate(data)
        return cls._normalize_parsed_report(parsed)

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        raw = raw.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"^```\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    @classmethod
    def _parse_with_regex(cls, text: str) -> ParsedMedicalReport:
        report_type = cls._detect_report_type(text)

        single_line_tests = cls._parse_single_line_results(text)
        multiline_tests = cls._parse_multiline_stacked_results(text)
        window_tests = cls._parse_known_test_windows(text)
        table_sequence_tests = cls._parse_table_sequence_results(text)

        merged_tests = cls._merge_test_results(single_line_tests + multiline_tests + window_tests + table_sequence_tests)
        normalized_report = cls._normalize_parsed_report(
            ParsedMedicalReport(
                report_type=report_type,
                patient_age=cls._extract_patient_info(text).get("age", ""),
                patient_gender=cls._extract_patient_info(text).get("gender", ""),
                tests=merged_tests,
                parser_mode="multi_pattern_fallback",
                parser_message="",
            )
        )

        normalized_report.parser_message = (
            "Multi-pattern fallback parser returned "
            f"{len(normalized_report.tests)} test result(s) "
            f"(single-line={len(single_line_tests)}, multiline={len(multiline_tests)}, "
            f"windows={len(window_tests)}, table-sequence={len(table_sequence_tests)})."
        )
        return normalized_report

    @classmethod
    def _parse_single_line_results(cls, text: str) -> list[ParsedTestResult]:
        tests: list[ParsedTestResult] = []

        for line in cls._prepare_candidate_lines(text):
            parsed_test = cls._parse_lab_result_line(line)
            if parsed_test:
                tests.append(parsed_test)

        return tests

    @classmethod
    def _normalize_ocr_lines(cls, text: str) -> list[str]:
        lines: list[str] = []

        for raw_line in (text or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line or "").strip(" :-\t")
            if not line:
                continue

            if cls._is_noise_line(line):
                continue

            lines.append(line)

        return lines

    @classmethod
    def _is_noise_line(cls, line: str) -> bool:
        lower = cls._normalize_key(line)

        if not lower:
            return True

        if lower in cls.HEADER_OR_NOISE_TERMS:
            return True

        blocked_terms = [
            "registered on", "collected on", "reported on", "received on", "referred by",
            "work timings", "please correlate", "sample", "doctor", "pathologist",
            "lab incharge", "download", "clinical notes", "possible causes",
            "contact the lab", "machine error", "unexpected test result", "nanded road",
            "ministry of health", "hospital laboratories", "patient name", "civil id",
            "nationality", "patient location", "specimen type", "sample uid", "referring doctor",
            "hosp no", "category", "registered on", "newkuwait",
        ]

        if any(term in lower for term in blocked_terms):
            return True

        # Filter lines that are mostly punctuation or decorative OCR noise.
        if len(re.sub(r"[^A-Za-z0-9]", "", line)) <= 1:
            return True

        return False

    @classmethod
    def _parse_multiline_stacked_results(cls, text: str) -> list[ParsedTestResult]:
        lines = cls._normalize_ocr_lines(text)
        tests: list[ParsedTestResult] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            canonical_name = cls._canonical_test_name_from_line(line)

            if not canonical_name:
                index += 1
                continue

            next_index = cls._find_next_test_index(lines, index + 1, max_lookahead=12)
            window_end = next_index if next_index != -1 else min(len(lines), index + 9)
            window = lines[index + 1:window_end]

            parsed = cls._parse_test_window(
                canonical_name=canonical_name,
                name_line=line,
                window=window,
            )

            if parsed:
                tests.append(parsed)

            index = max(index + 1, window_end if window_end > index else index + 1)

        return tests

    @classmethod
    def _find_next_test_index(cls, lines: list[str], start_index: int, max_lookahead: int = 12) -> int:
        max_index = min(len(lines), start_index + max_lookahead)

        for index in range(start_index, max_index):
            if cls._canonical_test_name_from_line(lines[index]):
                return index

        return -1

    @classmethod
    def _parse_test_window(cls, canonical_name: str, name_line: str, window: list[str]) -> ParsedTestResult | None:
        flag = cls._extract_flag_from_text(name_line)
        value = ""
        unit = ""
        reference_range = ""

        for line in window:
            if not reference_range:
                reference_range = cls._extract_reference_from_line(line)

            if not unit:
                unit = cls._extract_unit_from_line(line)

            if not value:
                value = cls._extract_value_from_line(line)

        # Second pass for units/reference that may be on the same line as the value.
        joined_window = " ".join(window)
        if not reference_range:
            reference_range = cls._extract_reference_from_line(joined_window)
        if not unit:
            unit = cls._extract_unit_from_line(joined_window)
        if not value:
            value = cls._extract_value_from_line(joined_window)

        value = cls._clean_numeric_text(value)
        unit = cls._clean_unit(unit)
        reference_range = cls._repair_reference_range_for_test(
            canonical_name,
            cls._clean_reference_range(reference_range),
            unit,
        )

        if not value:
            return None

        status = cls.detect_status(value=value, reference_range=reference_range, flag=flag)

        return ParsedTestResult(
            test_name=canonical_name,
            value=value,
            flag=flag,
            unit=unit,
            reference_range=reference_range,
            status=status,
        )

    @classmethod
    def _parse_table_sequence_results(cls, text: str) -> list[ParsedTestResult]:
        """
        Handles OCR tables where one test is split across several lines:
        Test name -> value -> unit -> reference range.
        Useful for Biochemistry/KFT/Electrolyte reports.
        """
        lines = cls._normalize_ocr_lines(text)
        tests: list[ParsedTestResult] = []

        for index, line in enumerate(lines):
            canonical_name = cls._canonical_test_name_from_line(line)
            if not canonical_name:
                continue

            next_index = cls._find_next_test_index(lines, index + 1, max_lookahead=14)
            window_end = next_index if next_index != -1 else min(len(lines), index + 10)
            window = lines[index + 1:window_end]

            parsed = cls._parse_table_sequence_window(canonical_name, line, window)
            if parsed:
                tests.append(parsed)

        return tests

    @classmethod
    def _parse_table_sequence_window(
        cls,
        canonical_name: str,
        name_line: str,
        window: list[str],
    ) -> ParsedTestResult | None:
        useful = [line for line in window if not cls._is_noise_line(line)]

        numeric_values: list[str] = []
        units: list[str] = []
        ranges: list[str] = []
        flags: list[str] = []

        for line in useful:
            flag = cls._extract_flag_from_text(line)
            if flag:
                flags.append(flag)

            reference = cls._extract_reference_from_line(line)
            if reference:
                ranges.append(reference)

            unit = cls._extract_unit_from_line(line)
            if unit:
                units.append(unit)

            value = cls._extract_value_from_line(line)
            if value:
                numeric_values.append(cls._clean_numeric_text(value))

        range_numbers: set[str] = set()
        for reference in ranges:
            for number in re.findall(r"[0-9][0-9,]*(?:\.[0-9]+)?", reference):
                range_numbers.add(cls._clean_numeric_text(number))

        observed_candidates = [value for value in numeric_values if value not in range_numbers]

        if not observed_candidates:
            return None

        # If result is repeated in OCR, keep the first observed value.
        observed_value = observed_candidates[0]
        unit = cls._clean_unit(units[0]) if units else ""
        reference_range = cls._clean_reference_range(ranges[0]) if ranges else ""
        reference_range = cls._repair_reference_range_for_test(canonical_name, reference_range, unit)
        flag = flags[0] if flags else cls._extract_flag_from_text(name_line)
        status = cls.detect_status(value=observed_value, reference_range=reference_range, flag=flag)

        return ParsedTestResult(
            test_name=canonical_name,
            value=observed_value,
            flag=flag,
            unit=unit,
            reference_range=reference_range,
            status=status,
        )

    @classmethod
    def _parse_known_test_windows(cls, text: str) -> list[ParsedTestResult]:
        """
        Last-resort scanner for OCR text where test name + value + unit + range appear
        in short local windows but not clean rows.
        """
        lines = cls._normalize_ocr_lines(text)
        tests: list[ParsedTestResult] = []

        for index, line in enumerate(lines):
            canonical_name = cls._canonical_test_name_from_line(line)
            if not canonical_name:
                continue

            window = lines[index:index + 8]
            parsed = cls._parse_test_window(
                canonical_name=canonical_name,
                name_line=line,
                window=window[1:],
            )
            if parsed:
                tests.append(parsed)

        return tests

    @classmethod
    def _extract_flag_from_text(cls, text: str) -> str:
        match = re.search(r"\b(LOW|HIGH|BORDERLINE|NORMAL|L|H)\b\s*$", text or "", re.IGNORECASE)
        if not match:
            return ""
        return cls._clean_flag(match.group(1))

    @classmethod
    def _extract_value_from_line(cls, line: str) -> str:
        if cls._looks_like_unit_only(line):
            return ""

        if cls._extract_reference_from_line(line) and len(re.findall(r"[0-9][0-9,]*(?:\.[0-9]+)?", line or "")) >= 2:
            # A pure reference range line is not the observed value.
            normalized = line.strip()
            if re.fullmatch(r"[<>]?\s*[0-9][0-9,]*(?:\.[0-9]+)?\s*[-–]\s*[0-9][0-9,]*(?:\.[0-9]+)?", normalized):
                return ""

        # Ignore dates and times.
        if re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", line or ""):
            return ""
        if re.search(r"\b\d{1,2}:\d{2}\b", line or ""):
            return ""

        match = re.search(r"[<>]?\s*[0-9][0-9,]*(?:\.[0-9]+)?", line or "")
        return match.group(0).strip() if match else ""

    @classmethod
    def _extract_reference_from_line(cls, line: str) -> str:
        if not line:
            return ""

        # Normal range: 13-17, 4,800 - 10,800, 31.5 - 34.5
        match = re.search(
            r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*[-–]\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
            line,
        )
        if match:
            return f"{match.group(1)} - {match.group(2)}"

        # One-sided ranges: <2, <= 5, > 20
        match = re.search(r"([<>]=?)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", line)
        if match:
            return f"{match.group(1)}{match.group(2)}"

        return ""

    @classmethod
    def _extract_unit_from_line(cls, line: str) -> str:
        if not line:
            return ""

        unit_patterns = [
            r"lakhs?/cumm", r"lakhs?/cmm",
            r"million[/f]?cumm", r"million[/f]?cmm",
            r"mill/cumm", r"mill/cmm",
            r"cells/cumm", r"cells/cmm",
            r"10\^3/uL", r"10\^3/ul", r"x10\^3/uL", r"x10\^3/ul",
            r"10\^6/uL", r"10\^6/ul",
            r"g/dL", r"g/dl", r"g/L", r"g/l", r"g/t", r"e/t", r"gm%", r"mg/dL",
            r"mmol/L", r"mmol/l", r"mmol/t", r"mmoi/l", r"mmoi/i", r"mol/L",
            r"umol/L", r"µmol/L", r"tumol/L", r"jamol/L",
            r"U/L", r"u/l", r"IU/L", r"iu/l",
            r"mm/hr", r"/cumm", r"/cmm", r"cumm", r"cmm",
            r"fL", r"fl", r"Pg", r"pg", r"%",
        ]

        for pattern in unit_patterns:
            match = re.search(rf"\b({pattern})\b", line or "", re.IGNORECASE)
            if match:
                return match.group(1)

        if (line or "").strip() == "%":
            return "%"

        return ""

    @classmethod
    def _merge_test_results(cls, tests: list[ParsedTestResult]) -> list[ParsedTestResult]:
        best_by_name: dict[str, ParsedTestResult] = {}

        for test in tests:
            cleaned_name = cls._clean_test_name(test.test_name)
            if not cleaned_name:
                continue

            test.test_name = cleaned_name
            key = cls._normalize_key(cleaned_name)

            if key not in best_by_name:
                best_by_name[key] = test
                continue

            if cls._test_quality_score(test) > cls._test_quality_score(best_by_name[key]):
                best_by_name[key] = test

        return list(best_by_name.values())

    @staticmethod
    def _test_quality_score(test: ParsedTestResult) -> int:
        score = 0
        if test.value:
            score += 5
        if test.unit:
            score += 2
        if test.reference_range:
            score += 3
        if test.status and test.status != "unknown":
            score += 2
        if test.flag:
            score += 1
        return score

    @classmethod
    def _prepare_candidate_lines(cls, text: str) -> list[str]:
        """Combines unit-only continuation lines such as a lone 'g/dL' after MCHC."""
        raw_lines = [line.strip() for line in text.splitlines()]
        lines: list[str] = []

        for line in raw_lines:
            if not line or set(line) <= {"-", "=", " "}:
                continue

            if lines and cls._looks_like_unit_only(line):
                lines[-1] = f"{lines[-1]} {line}"
                continue

            # Also try compacting common OCR table fragments into candidate rows.
            if lines and cls._extract_reference_from_line(line) and cls._canonical_test_name_from_line(lines[-1]):
                lines[-1] = f"{lines[-1]} {line}"
                continue

            lines.append(line)

        return lines

    @classmethod
    def _looks_like_unit_only(cls, line: str) -> bool:
        normalized = (line or "").strip()
        if not normalized:
            return False

        if cls._clean_unit(normalized):
            return cls._normalize_key(normalized) in {cls._normalize_key(unit) for unit in cls.KNOWN_UNITS} or normalized == "%"

        return bool(re.fullmatch(r"[A-Za-zµμ/%^0-9.]+", normalized)) and len(normalized) <= 14

    @classmethod
    def _parse_lab_result_line(cls, line: str) -> ParsedTestResult | None:
        if len(line) > 260:
            return None

        lower = line.lower()
        blocked_terms = [
            "investigation result", "patient details", "sample collected", "report timeline",
            "registered on", "collected on", "reported on", "generated on", "primary sample",
            "medical lab technician", "thanks for reference", "instruments:", "interpretation:",
            "test name observed value", "pathological examination report",
        ]
        if any(term in lower for term in blocked_terms):
            return None

        # Format A: Test Name | Result | Flag or '-' | Low - High | Unit
        pattern_a = re.compile(
            r"^(?P<name>[A-Za-z][A-Za-z0-9%()/.,*\-\s]{1,110}?)\s+"
            r"(?P<value>[<>]?[0-9][0-9,]*(?:\.[0-9]+)?)\s+"
            r"(?:(?P<flag>LOW|HIGH|BORDERLINE|NORMAL|L|H|-)\s+)?"
            r"(?P<low>[0-9][0-9,]*(?:\.[0-9]+)?)\s*[-–]\s*(?P<high>[0-9][0-9,]*(?:\.[0-9]+)?)"
            r"(?:\s+(?P<unit>[A-Za-zµμ/%^0-9.]+(?:/[A-Za-z0-9]+)?))?$",
            flags=re.IGNORECASE,
        )

        match = pattern_a.search(line)
        if match:
            name = cls._clean_test_name(match.group("name"))
            if not name:
                return None

            value = cls._clean_numeric_text(match.group("value") or "")
            flag = cls._clean_flag(match.group("flag") or "")
            unit = cls._clean_unit(match.group("unit") or "")
            reference_range = cls._repair_reference_range_for_test(
                name,
                cls._clean_reference_range(f"{match.group('low')} - {match.group('high')}"),
                unit,
            )
            status = cls.detect_status(value=value, reference_range=reference_range, flag=flag)

            return ParsedTestResult(
                test_name=name,
                value=value,
                flag=flag,
                unit=unit,
                reference_range=reference_range,
                status=status,
            )

        # Format B: Test Name | Observed Value | Unit | Reference Range
        pattern_b = re.compile(
            r"^(?P<name>[A-Za-z][A-Za-z0-9%()/.,*\-\s]{1,110}?)\s+"
            r"(?P<value>[<>]?[0-9][0-9,]*(?:\.[0-9]+)?)\s+"
            r"(?P<unit>gm%|g/dl|g/dL|g/l|g/L|g/t|e/t|mg/dL|mmol/L|mmol/l|mmol/t|mmoi/l|mmoi/i|mol/L|umol/L|µmol/L|tumol/L|jamol/L|U/L|u/l|IU/L|iu/l|/cmm|/cumm|cmm|cumm|lakhs?/cumm|million[/f]?cumm|mill/cumm|%|fl|fL|pg|Pg|mm/hr)\s+"
            r"(?P<low>[0-9][0-9,]*(?:\.[0-9]+)?)\s*[-–]\s*(?P<high>[0-9][0-9,]*(?:\.[0-9]+)?)$",
            flags=re.IGNORECASE,
        )

        match = pattern_b.search(line)
        if match:
            name = cls._clean_test_name(match.group("name"))
            if not name:
                return None

            value = cls._clean_numeric_text(match.group("value") or "")
            flag = ""
            unit = cls._clean_unit(match.group("unit") or "")
            reference_range = cls._repair_reference_range_for_test(
                name,
                cls._clean_reference_range(f"{match.group('low')} - {match.group('high')}"),
                unit,
            )
            status = cls.detect_status(value=value, reference_range=reference_range, flag=flag)

            return ParsedTestResult(
                test_name=name,
                value=value,
                flag=flag,
                unit=unit,
                reference_range=reference_range,
                status=status,
            )

        return None

    @staticmethod
    def _clean_numeric_text(value: str) -> str:
        return (value or "").replace(",", "").strip()

    @classmethod
    def _clean_reference_range(cls, reference_range: str) -> str:
        reference_range = (reference_range or "").strip()
        one_sided = re.search(r"([<>]=?)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", reference_range)
        if one_sided and "-" not in reference_range:
            return f"{one_sided.group(1)}{cls._clean_numeric_text(one_sided.group(2))}"

        nums = re.findall(r"[0-9][0-9,]*(?:\.[0-9]+)?", reference_range)
        if len(nums) >= 2:
            return f"{cls._clean_numeric_text(nums[0])} - {cls._clean_numeric_text(nums[1])}"
        return reference_range

    @classmethod
    def _repair_reference_range_for_test(cls, test_name: str, reference_range: str, unit: str = "") -> str:
        numbers = re.findall(r"[0-9][0-9,]*(?:\.[0-9]+)?", reference_range or "")
        if len(numbers) < 2:
            return reference_range or ""

        low = cls._clean_numeric_text(numbers[0])
        high = cls._clean_numeric_text(numbers[1])

        try:
            low_float = float(low)
            high_float = float(high)
        except Exception:
            return reference_range or ""

        normalized_name = cls._normalize_key(test_name)
        normalized_unit = cls._normalize_key(unit)

        # OCR often drops decimals: 45-55 instead of 4.5-5.5 for RBC.
        if "rbc" in normalized_name and "million" in normalized_unit and low_float >= 20 and high_float >= 20:
            return f"{low_float / 10:g} - {high_float / 10:g}"

        # Some labs print platelet in lakhs/cumm with 1.5-4.1. OCR may produce 15-41.
        if "platelet" in normalized_name and "lakh" in normalized_unit and low_float >= 10 and high_float >= 20:
            return f"{low_float / 10:g} - {high_float / 10:g}"

        return f"{low_float:g} - {high_float:g}"

    @classmethod
    def _normalize_parsed_report(cls, parsed_report: ParsedMedicalReport) -> ParsedMedicalReport:
        normalized_tests: list[ParsedTestResult] = []

        for test in parsed_report.tests:
            flag = cls._clean_flag(test.flag)
            unit = cls._clean_unit(test.unit)
            value = cls._clean_numeric_text(test.value)
            cleaned_name = cls._clean_test_name(test.test_name)
            reference_range = cls._repair_reference_range_for_test(
                cleaned_name,
                cls._clean_reference_range(test.reference_range),
                unit,
            )

            if unit.upper() in cls.KNOWN_FLAGS and not flag:
                flag = unit.upper()
                unit = ""

            status = (test.status or "unknown").lower().strip()
            if status not in {"low", "normal", "high", "borderline", "unknown"}:
                status = "unknown"

            if status == "unknown" or flag or reference_range:
                status = cls.detect_status(value, reference_range, flag)

            if not cleaned_name or not value:
                continue

            normalized_tests.append(
                ParsedTestResult(
                    test_name=cleaned_name,
                    value=value,
                    flag=flag,
                    unit=unit,
                    reference_range=reference_range,
                    status=status,
                )
            )

        normalized_tests = cls._merge_test_results(normalized_tests)

        return ParsedMedicalReport(
            report_type=parsed_report.report_type or "Unknown",
            patient_age=parsed_report.patient_age,
            patient_gender=parsed_report.patient_gender,
            tests=normalized_tests,
            parser_mode=parsed_report.parser_mode,
            parser_message=parsed_report.parser_message,
        )

    @staticmethod
    def _detect_report_type(text: str) -> str:
        lower = text.lower()

        if any(term in lower for term in [
            "hemoglobin", "haemoglobin", "platelet", "wbc", "rbc",
            "leukocyte", "leucocyte", "complete blood count", "cbc", "hemogram", "haematology", "hematology",
        ]):
            return "Complete Blood Count"

        if any(term in lower for term in ["bilirubin", "sgpt", "sgot", "alkaline phosphatase", " ggt "]):
            return "Liver Function Test"

        if any(term in lower for term in ["cholesterol", "triglycerides", " hdl", " ldl", "lipid"]):
            return "Lipid Profile"

        if any(term in lower for term in ["creatinine", "urea", "uric acid", "sodium", "potassium", "chloride", "calcium", "phosphorous", "phosphorus", "magnesium", "electrolyte", "kft"]):
            return "Kidney Function / Electrolyte Panel"

        if any(term in lower for term in ["biochemistry", "glucose", "albumin", "total protein"]):
            return "Biochemistry Report"

        if any(term in lower for term in ["t3", "t4", "tsh", "thyroid"]):
            return "Thyroid Profile"

        if any(term in lower for term in ["hba1c", "blood sugar"]):
            return "Diabetes Report"

        return "Unknown"

    @classmethod
    def _clean_test_name(cls, name: str) -> str:
        name = re.sub(r"\*", "", name or "")
        name = re.sub(r"\s+", " ", name).strip(" :-")
        name = name.replace("M.C.V.", "MCV").replace("M.C.H.", "MCH").replace("M.C.H.C.", "MCHC")

        canonical = cls._canonical_test_name_from_line(name)
        if canonical:
            return canonical[:255]

        blocked_names = {
            "result", "test name", "investigation", "unit",
            "reference", "reference value", "observed value",
        }

        if name.lower() in blocked_names:
            return ""

        return name[:255]

    @classmethod
    def _clean_flag(cls, flag: str) -> str:
        cleaned = (flag or "").strip().upper()
        if cleaned == "-":
            return ""
        return cleaned if cleaned in cls.KNOWN_FLAGS else ""

    @classmethod
    def _clean_unit(cls, unit: str) -> str:
        cleaned = (unit or "").strip()
        if not cleaned or cleaned == "-" or cleaned.upper() in cls.KNOWN_FLAGS:
            return ""

        normalized = cleaned.lower().replace("µ", "u").replace("μ", "u")
        normalized = normalized.replace("millionfcumm", "million/cumm")
        normalized = normalized.replace("millionfcmm", "million/cmm")
        normalized = normalized.replace("g/dl", "g/dL")
        normalized = normalized.replace("g/t", "g/L")
        normalized = normalized.replace("e/t", "g/L")
        normalized = normalized.replace("mmol/t", "mmol/L")
        normalized = normalized.replace("mmoi/l", "mmol/L")
        normalized = normalized.replace("mmoi/i", "mmol/L")
        normalized = normalized.replace("tumol/l", "umol/L")
        normalized = normalized.replace("jamol/l", "umol/L")
        normalized = normalized.replace("µmol/l", "umol/L")
        normalized = normalized.replace("u/l", "U/L")
        normalized = normalized.replace("iu/l", "IU/L")
        normalized = normalized.replace("fl", "fL")
        normalized = normalized.replace("pg", "pg")
        normalized = normalized.replace("lakhs/cmm", "lakhs/cumm")
        normalized = normalized.replace("lakh/cmm", "lakh/cumm")

        if normalized == "cmm":
            normalized = "cumm"

        return normalized

    @staticmethod
    def _is_duplicate_test(tests: list[ParsedTestResult], name: str) -> bool:
        normalized = name.lower().strip()
        return any(test.test_name.lower().strip() == normalized for test in tests)

    @classmethod
    def detect_status(cls, value: str, reference_range: str, flag: str = "") -> str:
        normalized_flag = (flag or "").strip().upper()
        if normalized_flag in {"LOW", "L"}:
            return "low"
        if normalized_flag in {"HIGH", "H"}:
            return "high"
        if normalized_flag == "BORDERLINE":
            return "borderline"
        if normalized_flag == "NORMAL":
            return "normal"

        try:
            numeric_value = float(cls._clean_numeric_text(re.sub(r"[^0-9.,]", "", value)))
            reference = (reference_range or "").strip().replace(" ", "")

            one_sided = re.fullmatch(r"([<>]=?)([0-9][0-9,]*(?:\.[0-9]+)?)", reference)
            if one_sided:
                operator = one_sided.group(1)
                limit = float(cls._clean_numeric_text(one_sided.group(2)))

                if operator in {"<", "<="}:
                    return "normal" if numeric_value <= limit else "high"
                if operator in {">", ">="}:
                    return "normal" if numeric_value >= limit else "low"

            numbers = re.findall(r"[0-9][0-9,]*(?:\.[0-9]+)?", reference_range or "")
            if len(numbers) < 2:
                return "unknown"

            low = float(cls._clean_numeric_text(numbers[0]))
            high = float(cls._clean_numeric_text(numbers[1]))

            # Borderline when exactly equal to range boundary.
            if numeric_value == low or numeric_value == high:
                return "borderline"
            if numeric_value < low:
                return "low"
            if numeric_value > high:
                return "high"
            return "normal"
        except Exception:
            return "unknown"


class MedicalKnowledgeService:
    """
    Lightweight RAG service over trusted medical knowledge documents.
    Phase 4 uses database-backed keyword retrieval. Later we can replace the scoring
    method with embeddings + pgvector without changing the API shape.
    """

    DEFAULT_DOCUMENTS = [
        {
            "title": "Understanding Lab Test Results",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/how-to-understand-your-lab-results/",
            "report_type": "general",
            "test_names": ["reference range", "lab results", "abnormal results"],
            "content": (
                "Lab test results are usually compared with a reference range. A value outside the range "
                "does not always mean a person has a disease. Results can be affected by age, sex, medicines, "
                "diet, timing, lab method, and medical history. Abnormal or borderline results should be discussed "
                "with a healthcare professional."
            ),
        },
        {
            "title": "Complete Blood Count",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/complete-blood-count-cbc/",
            "report_type": "cbc",
            "test_names": ["CBC", "Complete Blood Count", "Hemoglobin", "WBC", "RBC", "Platelet Count"],
            "content": (
                "A complete blood count measures different parts of blood, including red blood cells, white blood "
                "cells, hemoglobin, hematocrit, and platelets. It can help a doctor evaluate general health and look "
                "for clues related to infection, anemia, inflammation, bleeding, or other conditions, but it does not "
                "confirm a diagnosis by itself."
            ),
        },
        {
            "title": "Hemoglobin Test",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/hemoglobin-test/",
            "report_type": "cbc",
            "test_names": ["Hemoglobin", "Hemoglobin (Hb)", "Hb"],
            "content": (
                "Hemoglobin is a protein in red blood cells that carries oxygen from the lungs to the rest of the body. "
                "Low hemoglobin can have many possible causes, including anemia, iron deficiency, vitamin deficiency, "
                "blood loss, chronic illness, or other causes. A doctor should interpret the value with symptoms and "
                "other test results."
            ),
        },
        {
            "title": "Hematocrit / Packed Cell Volume",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/hematocrit-test/",
            "report_type": "cbc",
            "test_names": ["Packed Cell Volume", "PCV", "Hematocrit"],
            "content": (
                "Hematocrit, also called packed cell volume in some reports, measures how much of the blood is made up "
                "of red blood cells. High or low values may occur for several reasons and should be interpreted with "
                "hydration status, symptoms, altitude, smoking history, and other blood values."
            ),
        },
        {
            "title": "Platelet Count",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/platelet-tests/",
            "report_type": "cbc",
            "test_names": ["Platelet", "Platelet Count", "Thrombocyte"],
            "content": (
                "Platelets help blood clot and stop bleeding. A platelet count near the lower or upper end of the range "
                "may need review, especially if there is easy bruising, bleeding, fever, recent illness, medicine use, "
                "or previous abnormal reports."
            ),
        },
        {
            "title": "White Blood Cell Count",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/white-blood-count-wbc/",
            "report_type": "cbc",
            "test_names": ["WBC", "White Blood Cell", "Total WBC count", "Neutrophils", "Lymphocytes"],
            "content": (
                "White blood cells are part of the immune system. WBC and differential counts can change with infection, "
                "inflammation, stress, medicines, allergies, and other causes. These values should be interpreted by a "
                "doctor along with symptoms and examination findings."
            ),
        },
        {
            "title": "Blood Glucose Test",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/blood-glucose-test/",
            "report_type": "biochemistry",
            "test_names": ["Glucose", "Blood Sugar", "Fasting Glucose"],
            "content": (
                "A blood glucose test measures the amount of sugar in the blood. Results can be affected by meals, timing, medicines, stress, and medical history. "
                "High or low values should be interpreted by a healthcare professional with symptoms and other results."
            ),
        },
        {
            "title": "Kidney Function Tests",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/kidneytests.html",
            "report_type": "kidney",
            "test_names": ["Urea", "Creatinine", "Uric Acid", "Kidney Function Test"],
            "content": (
                "Kidney-related blood tests can include creatinine, urea, and other chemistry values. Abnormal results may have many causes and should be interpreted with clinical history, hydration, medicines, and other tests."
            ),
        },
        {
            "title": "Electrolyte Panel",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/electrolyte-panel/",
            "report_type": "biochemistry",
            "test_names": ["Sodium", "Na", "Potassium", "K", "Chloride", "Calcium", "Magnesium", "Phosphorous"],
            "content": (
                "Electrolytes help regulate fluid balance, nerve signals, and muscle function. Values outside the reference range can occur for different reasons and need medical interpretation."
            ),
        },
        {
            "title": "Liver Function Tests",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/liver-function-tests/",
            "report_type": "liver",
            "test_names": ["Bilirubin", "ALT", "AST", "SGPT", "SGOT", "ALP", "GGT", "Albumin", "Total Protein"],
            "content": (
                "Liver function tests measure enzymes, proteins, and bilirubin. Abnormal values do not diagnose a condition by themselves and should be reviewed with symptoms, medicines, alcohol history, and other tests."
            ),
        },
        {
            "title": "Cholesterol and Lipid Tests",
            "source_name": "MedlinePlus",
            "source_url": "https://medlineplus.gov/lab-tests/cholesterol-levels/",
            "report_type": "lipid",
            "test_names": ["Cholesterol", "Triglycerides", "HDL", "LDL", "VLDL"],
            "content": (
                "Lipid tests measure cholesterol and related fats in the blood. Results help doctors understand cardiovascular risk, but interpretation depends on age, risk factors, medicines, and medical history."
            ),
        },
    ]

    @staticmethod
    def seed_default_documents() -> int:
        from reports.models import MedicalKnowledgeDocument

        created_count = 0
        for item in MedicalKnowledgeService.DEFAULT_DOCUMENTS:
            _, created = MedicalKnowledgeDocument.objects.get_or_create(
                title=item["title"],
                source_name=item["source_name"],
                defaults=item,
            )
            if created:
                created_count += 1
        return created_count

    @staticmethod
    def retrieve_for_test(test_name: str, report_type: str = "", limit: int = 3) -> list[dict[str, str]]:
        from reports.models import MedicalKnowledgeDocument

        docs = MedicalKnowledgeDocument.objects.filter(is_active=True)
        query_terms = MedicalKnowledgeService._tokenize(f"{test_name} {report_type}")
        scored_docs: list[tuple[int, Any]] = []

        for doc in docs:
            searchable = " ".join([
                doc.title,
                doc.source_name,
                doc.report_type,
                " ".join(doc.test_names or []),
                doc.content,
            ])
            doc_terms = MedicalKnowledgeService._tokenize(searchable)
            score = len(query_terms.intersection(doc_terms))

            # Strong boost when the test name is explicitly mapped to the document.
            for mapped_test in doc.test_names or []:
                if test_name.lower() in mapped_test.lower() or mapped_test.lower() in test_name.lower():
                    score += 5

            if score > 0:
                scored_docs.append((score, doc))

        scored_docs.sort(key=lambda item: item[0], reverse=True)

        return [
            {
                "title": doc.title,
                "source_name": doc.source_name,
                "source_url": doc.source_url,
                "content": doc.content,
            }
            for _, doc in scored_docs[:limit]
        ]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        stopwords = {"test", "count", "total", "value", "report", "profile", "the", "and", "of"}
        tokens = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
        return {token for token in tokens if len(token) > 1 and token not in stopwords}


class PatientExplanationService:
    """Creates safe, simple explanations without diagnosis or treatment advice."""

    @staticmethod
    def explain_test(test: ParsedTestResult, knowledge_context: list[dict[str, str]] | None = None) -> str:
        status_text = {
            "low": "below",
            "high": "above",
            "borderline": "near the edge of",
            "normal": "within",
            "unknown": "not clearly comparable with",
        }.get(test.status, "not clearly comparable with")

        if knowledge_context:
            trusted_note = knowledge_context[0]["content"]
            source_name = knowledge_context[0]["source_name"]
            source_sentence = f" Trusted context from {source_name}: {trusted_note}"
        else:
            source_sentence = ""

        if test.status == "normal":
            return (
                f"{test.test_name} appears to be within the reference range provided in this report. "
                "Reference ranges can vary by lab, so this should still be read with your symptoms and doctor's advice."
                f"{source_sentence}"
            )

        if test.status in ["low", "high"]:
            return (
                f"{test.test_name} is {status_text} the reference range provided in this report. "
                "This does not confirm any disease by itself. It should be discussed with a qualified doctor, "
                "especially if you have symptoms or previous abnormal reports."
                f"{source_sentence}"
            )

        if test.status == "borderline":
            return (
                f"{test.test_name} is marked as borderline or is close to the reference range boundary in this report. "
                "This does not confirm any disease by itself, but it is worth discussing with a doctor along with symptoms and previous reports."
                f"{source_sentence}"
            )

        return (
            f"{test.test_name} was found in the report, but MedSenseAI could not confidently compare it with a reference range. "
            "Please confirm this value with your doctor or lab report notes."
            f"{source_sentence}"
        )

    @staticmethod
    def extract_sources(knowledge_context: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
        return [
            {
                "title": item.get("title", ""),
                "source_name": item.get("source_name", ""),
                "source_url": item.get("source_url", ""),
            }
            for item in (knowledge_context or [])
        ]

    @staticmethod
    def generate_doctor_questions(test: ParsedTestResult) -> list[str]:
        questions = [
            f"What does my {test.test_name} value mean in my case?",
            "Is this related to any symptoms I am having?",
            "Should I repeat this test or compare it with previous reports?",
        ]

        if test.status in ["low", "high"]:
            questions.insert(1, f"What are common reasons for {test.test_name} being {test.status}?")
            questions.append("Do I need any follow-up test based on this result?")

        if test.status == "borderline":
            questions.insert(1, f"Why is my {test.test_name} marked borderline?")
            questions.append("Should this borderline value be monitored or repeated?")

        return questions

class MultilingualReportService:
    """Builds a safe patient-facing report view in English or Hindi without changing stored source data."""

    SUPPORTED_LANGUAGES = {"en", "hi"}

    HINDI_STATUS = {
        "low": "सामान्य सीमा से कम",
        "high": "सामान्य सीमा से अधिक",
        "borderline": "सीमा के पास / बॉर्डरलाइन",
        "normal": "सामान्य सीमा में",
        "unknown": "स्पष्ट नहीं",
    }

    HINDI_RISK = {
        "green": "ग्रीन — अधिकतर जाँच-मान सामान्य सीमा में दिख रहे हैं।",
        "yellow": "येलो — कुछ जाँच-मान सामान्य सीमा से बाहर हैं। डॉक्टर से नियमित परामर्श करना उचित रहेगा।",
        "orange": "ऑरेंज — कई जाँच-मान सामान्य सीमा से बाहर हैं। जल्द डॉक्टर से सलाह लेना बेहतर रहेगा।",
        "red": "रेड — रिपोर्ट में ऐसे संकेत हो सकते हैं जिन पर तुरंत चिकित्सा सहायता की आवश्यकता हो सकती है।",
        "unknown": "जोखिम स्तर स्पष्ट नहीं है। रिपोर्ट को डॉक्टर से समझना बेहतर रहेगा।",
    }

    # Keep this literal here because SafetyGuardrailService is defined later in this file.
    # Referencing it during class creation causes NameError at Django startup.
    ENGLISH_SAFETY_NOTE = (
        "MedSenseAI is an educational report-understanding assistant. It does not diagnose disease, "
        "prescribe medicine, suggest dosage, or replace a qualified doctor. Reference ranges can vary by lab. "
        "Please consult a healthcare professional for medical decisions."
    )
    HINDI_SAFETY_NOTE = (
        "MedSenseAI एक शैक्षणिक रिपोर्ट-समझ सहायता उपकरण है। यह बीमारी की पुष्टि नहीं करता, "
        "दवा या खुराक नहीं बताता, और किसी योग्य डॉक्टर की जगह नहीं लेता। संदर्भ सीमाएँ लैब के अनुसार बदल सकती हैं। "
        "किसी भी चिकित्सा निर्णय के लिए योग्य स्वास्थ्य विशेषज्ञ से सलाह लें।"
    )

    @classmethod
    def build_patient_view(cls, report, language: str = "en") -> dict:
        language = (language or "en").lower().strip()
        if language not in cls.SUPPORTED_LANGUAGES:
            language = "en"

        if language == "hi":
            return cls._build_hindi_view(report)
        return cls._build_english_view(report)

    @classmethod
    def _build_english_view(cls, report) -> dict:
        return {
            "language": "en",
            "report_id": report.id,
            "report_type": report.report_type,
            "patient_age": report.patient_age,
            "patient_gender": report.patient_gender,
            "overall_risk_level": report.overall_risk_level,
            "summary": report.ai_summary,
            "safety_note": cls.ENGLISH_SAFETY_NOTE,
            "tests": [
                {
                    "test_name": test.test_name,
                    "value": test.value,
                    "flag": test.flag,
                    "unit": test.unit,
                    "reference_range": test.reference_range,
                    "status": test.status,
                    "explanation": test.simple_explanation,
                    "doctor_questions": test.doctor_questions,
                    "sources": test.explanation_sources,
                }
                for test in report.test_results.all()
            ],
        }

    @classmethod
    def _build_hindi_view(cls, report) -> dict:
        return {
            "language": "hi",
            "report_id": report.id,
            "report_type": cls._translate_report_type(report.report_type),
            "patient_age": report.patient_age,
            "patient_gender": cls._translate_gender(report.patient_gender),
            "overall_risk_level": report.overall_risk_level,
            "summary": cls._translate_summary(report.overall_risk_level, report.ai_summary),
            "safety_note": cls.HINDI_SAFETY_NOTE,
            "tests": [cls._build_hindi_test(test) for test in report.test_results.all()],
        }

    @classmethod
    def _build_hindi_test(cls, test) -> dict:
        status_hi = cls.HINDI_STATUS.get(test.status, "स्पष्ट नहीं")
        value_with_unit = " ".join(part for part in [test.value, test.unit] if part)
        reference_text = test.reference_range or "उपलब्ध नहीं"

        if test.status == "normal":
            explanation = (
                f"{test.test_name} का मान {value_with_unit} रिपोर्ट में दी गई संदर्भ सीमा "
                f"({reference_text}) के अंदर दिख रहा है। फिर भी इसे लक्षणों, पुरानी रिपोर्टों और डॉक्टर की सलाह के साथ समझना चाहिए।"
            )
        elif test.status in {"low", "high"}:
            direction = "कम" if test.status == "low" else "अधिक"
            explanation = (
                f"{test.test_name} का मान {value_with_unit} रिपोर्ट में दी गई संदर्भ सीमा "
                f"({reference_text}) से {direction} है। यह अपने आप किसी बीमारी की पुष्टि नहीं करता। "
                "इसे योग्य डॉक्टर से समझना चाहिए, खासकर अगर कोई लक्षण हैं या पहले की रिपोर्ट भी असामान्य रही है।"
            )
        elif test.status == "borderline":
            explanation = (
                f"{test.test_name} का मान {value_with_unit} बॉर्डरलाइन है या संदर्भ सीमा "
                f"({reference_text}) के बहुत पास है। यह अपने आप कोई निदान नहीं है, लेकिन इसे डॉक्टर से चर्चा करना उचित रहेगा।"
            )
        else:
            explanation = (
                f"{test.test_name} रिपोर्ट में मिला है, लेकिन MedSenseAI इसे संदर्भ सीमा से भरोसेमंद तरीके से तुलना नहीं कर पाया। "
                "कृपया लैब रिपोर्ट के नोट्स या डॉक्टर से इसकी पुष्टि करें।"
            )

        source_names = []
        for source in test.explanation_sources or []:
            name = source.get("source_name", "")
            if name and name not in source_names:
                source_names.append(name)

        if source_names:
            explanation += f" जानकारी का आधार: {', '.join(source_names)}."

        return {
            "test_name": test.test_name,
            "value": test.value,
            "flag": test.flag,
            "unit": test.unit,
            "reference_range": test.reference_range,
            "status": test.status,
            "status_hindi": status_hi,
            "explanation": explanation,
            "doctor_questions": cls._translate_questions(test),
            "sources": test.explanation_sources,
        }

    @classmethod
    def _translate_questions(cls, test) -> list[str]:
        questions = [
            f"मेरी {test.test_name} जाँच का यह मान मेरे लिए क्या मतलब रखता है?",
            "क्या यह मेरे लक्षणों या मेडिकल हिस्ट्री से जुड़ा हो सकता है?",
            "क्या मुझे यह जाँच दोबारा करवानी चाहिए या पुरानी रिपोर्टों से तुलना करनी चाहिए?",
        ]
        if test.status in {"low", "high"}:
            questions.insert(1, f"{test.test_name} का मान {cls.HINDI_STATUS.get(test.status, test.status)} आने के सामान्य कारण क्या हो सकते हैं?")
            questions.append("क्या इस परिणाम के आधार पर किसी follow-up जाँच की आवश्यकता हो सकती है?")
        if test.status == "borderline":
            questions.insert(1, f"मेरी {test.test_name} जाँच बॉर्डरलाइन क्यों दिख रही है?")
            questions.append("क्या इस बॉर्डरलाइन मान को दोबारा जाँचना या मॉनिटर करना चाहिए?")
        return questions

    @staticmethod
    def _translate_report_type(report_type: str) -> str:
        mapping = {
            "Complete Blood Count": "Complete Blood Count (CBC) / पूर्ण रक्त जाँच",
            "Liver Function Test": "Liver Function Test (LFT)",
            "Kidney Function Test": "Kidney Function Test (KFT)",
            "Kidney Function / Electrolyte Panel": "Kidney Function / Electrolyte Panel",
            "Biochemistry Report": "Biochemistry Report",
            "Thyroid Profile": "Thyroid Profile",
            "Lipid Profile": "Lipid Profile",
            "Diabetes Report": "Diabetes Report",
        }
        return mapping.get(report_type or "", report_type or "Unknown")

    @staticmethod
    def _translate_gender(gender: str) -> str:
        mapping = {"male": "Male / पुरुष", "female": "Female / महिला", "other": "Other"}
        return mapping.get((gender or "").lower(), gender or "")

    @classmethod
    def _translate_summary(cls, risk_level: str, fallback_summary: str) -> str:
        return cls.HINDI_RISK.get(risk_level, fallback_summary or "Report summary available नहीं है।")


class RiskTriageService:
    """Rule-based conservative triage. This is not a diagnosis."""

    @staticmethod
    def calculate_risk(tests: list[ParsedTestResult]) -> tuple[str, str]:
        abnormal = [test for test in tests if test.status in ["low", "high"]]
        borderline = [test for test in tests if test.status == "borderline"]

        if not tests:
            return "unknown", "No structured test values could be confidently extracted."

        if not abnormal and not borderline:
            return "green", "Extracted values appear mostly within the provided reference ranges."

        if len(abnormal) <= 2:
            if borderline and not abnormal:
                return "yellow", "One or more values are marked borderline and should be discussed with a doctor routinely."
            return "yellow", "Some values are outside the provided reference range and should be discussed with a doctor routinely."

        return "orange", "Multiple values are outside the provided reference range. A doctor consultation should be considered soon."


class SafetyGuardrailService:
    """
    Safety constants and final review logic used across generated outputs.
    This is intentionally rule-based so the project has deterministic safety checks,
    not only LLM self-review.
    """

    DEFAULT_SAFETY_NOTE = (
        "MedSenseAI is an educational report-understanding assistant. It does not diagnose disease, "
        "prescribe medicine, suggest dosage, or replace a qualified doctor. Reference ranges can vary by lab. "
        "Please consult a healthcare professional for medical decisions."
    )

    # These patterns are intentionally strict. Earlier broad patterns like "you have"
    # and "dosage" caused false blocks for safe phrases such as
    # "especially if you have symptoms" and the safety disclaimer
    # "does not ... suggest dosage". Keep these checks focused on actual unsafe claims.
    DIAGNOSIS_PATTERNS = [
        r"\byou\s+(?:definitely\s+|certainly\s+)?have\s+(?:anemia|diabetes|cancer|kidney\s+failure|liver\s+disease|thyroid\s+disease|infection)\b",
        r"\byou\s+are\s+suffering\s+from\s+[a-zA-Z][a-zA-Z\s-]{2,60}",
        r"\bthis\s+(?:report\s+)?confirms\s+(?:that\s+you\s+have\s+)?[a-zA-Z][a-zA-Z\s-]{2,60}",
        r"\bdiagnosed\s+with\s+[a-zA-Z][a-zA-Z\s-]{2,60}",
        r"\bconfirmed\s+case\s+of\s+[a-zA-Z][a-zA-Z\s-]{2,60}",
    ]

    TREATMENT_PATTERNS = [
        r"\btake\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|tablet|tablets|capsule|capsules)\b",
        r"\bstart\s+taking\s+(?!.*(?:doctor|physician|healthcare professional|qualified))",
        r"\bstop\s+taking\s+(?!.*(?:doctor|physician|healthcare professional|qualified))",
        r"\bdiscontinue\s+(?:this\s+)?(?:medicine|medication|tablet|drug)\b",
        r"\b\d+(?:\.\d+)?\s*mg\s+(?:once|twice|thrice)\s+daily\b",
        r"\btablet\b.{0,40}\bdaily\b",
    ]

    FALSE_REASSURANCE_PATTERNS = [
        r"\bno\s+need\s+to\s+see\s+(?:a\s+)?doctor\b",
        r"\bnothing\s+to\s+worry\b",
        r"\bcompletely\s+safe\b",
        r"\bignore\s+this\b",
        r"\bnot\s+serious\b",
    ]

    SAFE_CONTEXT_PATTERNS = [
        r"does\s+not\s+diagnose",
        r"does\s+not\s+confirm",
        r"does\s+not\s+prescribe",
        r"does\s+not\s+.*suggest\s+dosage",
        r"this\s+does\s+not\s+confirm\s+any\s+disease",
        r"especially\s+if\s+you\s+have\s+symptoms",
        r"if\s+you\s+have\s+symptoms",
        r"questions?\s+to\s+ask",
    ]

    @classmethod
    def review_text(cls, text: str, risk_level: str = "unknown") -> dict:
        """Return deterministic safety findings for generated patient-facing text.

        The review is conservative, but avoids blocking safe disclaimers and doctor-question text.
        It is designed to catch actual diagnosis/treatment/reassurance claims, not educational wording.
        """
        normalized_text = text or ""

        diagnosis_claims = cls._find_matches(normalized_text, cls.DIAGNOSIS_PATTERNS)
        treatment_advice = cls._find_matches(normalized_text, cls.TREATMENT_PATTERNS)
        false_reassurance = cls._find_matches(normalized_text, cls.FALSE_REASSURANCE_PATTERNS)

        warnings = []
        if risk_level == "red" and "doctor" not in normalized_text.lower() and "medical care" not in normalized_text.lower():
            warnings.append("Red-level output should clearly advise urgent professional medical care.")

        if diagnosis_claims or treatment_advice or false_reassurance:
            final_status = "blocked"
        elif warnings:
            final_status = "review_required"
        else:
            final_status = "passed"

        return {
            "risk_level": risk_level,
            "blocked_diagnosis_claims": diagnosis_claims,
            "blocked_treatment_advice": treatment_advice,
            "blocked_false_reassurance": false_reassurance,
            "safety_warnings": warnings,
            "final_safety_status": final_status,
            "reviewed_text_excerpt": normalized_text[:2000],
        }

    @classmethod
    def _find_matches(cls, text: str, patterns: list[str]) -> list[str]:
        matches = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                if cls._is_safe_context(text, match.start(), match.end()):
                    continue
                matches.append(pattern)
                break
        return matches

    @classmethod
    def _is_safe_context(cls, text: str, start: int, end: int) -> bool:
        window_start = max(0, start - 120)
        window_end = min(len(text), end + 120)
        context = text[window_start:window_end].lower()
        return any(re.search(pattern, context, flags=re.IGNORECASE) for pattern in cls.SAFE_CONTEXT_PATTERNS)

    @classmethod
    def build_review_text(cls, report_summary: str, test_results: list) -> str:
        # Review only patient-facing generated explanations and summary.
        # Do not include the default safety disclaimer or doctor questions in the blocking scan,
        # because they naturally contain safe words like "dosage", "doctor", and "you have symptoms".
        parts = [report_summary or ""]
        for test in test_results:
            parts.append(getattr(test, "simple_explanation", "") or "")
        return "\n".join(part for part in parts if part)