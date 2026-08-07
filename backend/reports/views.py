import mimetypes
from pathlib import Path

from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ai_engine.services import (
    MedicalKnowledgeService,
    MedicalReportParserService,
    MultilingualReportService,
    PatientExplanationService,
    PDFTextExtractionService,
    RiskTriageService,
    SafetyGuardrailService,
)
from .models import MedicalKnowledgeDocument, MedicalReport, MedicalTestResult, SafetyAuditLog
from .serializers import MedicalKnowledgeDocumentSerializer, MedicalReportSerializer, SafetyAuditLogSerializer


def _get_owned_report_or_404(request, report_id, prefetch_tests: bool = False):
    queryset = MedicalReport.objects.filter(user=request.user)

    if prefetch_tests:
        queryset = queryset.prefetch_related("test_results")

    try:
        return queryset.get(id=report_id), None
    except MedicalReport.DoesNotExist:
        return None, Response(
            {"error": "Report not found or you do not have permission to access it."},
            status=status.HTTP_404_NOT_FOUND,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_report(request):
    uploaded_file = request.FILES.get("file")
    serializer = MedicalReportSerializer(data=request.data)

    if serializer.is_valid():
        report = serializer.save(
            user=request.user,
            original_filename=uploaded_file.name if uploaded_file else "",
        )

        return Response(
            {
                "message": "Report uploaded successfully.",
                "report": MedicalReportSerializer(report).data,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_report_file(request, report_id):
    report, error_response = _get_owned_report_or_404(request, report_id)

    if error_response:
        return error_response

    if not report.file:
        return Response(
            {"error": "No file is associated with this report."},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        file_handle = report.file.open("rb")
    except (FileNotFoundError, OSError):
        return Response(
            {"error": "Report file could not be found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    stored_name = Path(report.file.name).name
    download_name = report.original_filename or stored_name
    content_type, _ = mimetypes.guess_type(download_name)

    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=download_name,
        content_type=content_type or "application/octet-stream",
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_reports(request):
    reports = MedicalReport.objects.filter(user=request.user)
    serializer = MedicalReportSerializer(reports, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_detail(request, report_id):
    report, error_response = _get_owned_report_or_404(request, report_id)

    if error_response:
        return error_response

    serializer = MedicalReportSerializer(report)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def patient_friendly_report_view(request, report_id):
    report, error_response = _get_owned_report_or_404(request, report_id, prefetch_tests=True)

    if error_response:
        return error_response

    language = request.query_params.get("language", "en")
    data = MultilingualReportService.build_patient_view(report, language=language)
    return Response(data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def extract_report_text(request, report_id):
    report, error_response = _get_owned_report_or_404(request, report_id)

    if error_response:
        return error_response

    try:
        report.status = "processing"
        report.error_message = ""
        report.save(update_fields=["status", "error_message"])

        extracted_text = PDFTextExtractionService.extract_text(report.file.path)

        if not extracted_text:
            report.status = "failed"
            report.error_message = "No readable text could be extracted from this report."
            report.save(update_fields=["status", "error_message"])

            return Response(
                {
                    "error": "No readable text could be extracted from this report.",
                    "message": "If this is an image/scanned report, make sure Tesseract OCR is installed and TESSERACT_CMD is configured if needed.",
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        report.extracted_text = extracted_text
        report.status = "uploaded"
        report.save(update_fields=["extracted_text", "status"])

        return Response(
            {
                "message": "Text extracted successfully.",
                "report_id": report.id,
                "extracted_text": extracted_text,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as exc:
        report.status = "failed"
        report.error_message = str(exc)
        report.save(update_fields=["status", "error_message"])

        return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def parse_report(request, report_id):
    report, error_response = _get_owned_report_or_404(request, report_id)

    if error_response:
        return error_response

    if not report.extracted_text:
        return Response(
            {"error": "No extracted text found. Run extract-text first."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        report.status = "processing"
        report.error_message = ""
        report.parser_mode = ""
        report.parser_message = ""
        report.save(update_fields=["status", "error_message", "parser_mode", "parser_message"])

        parsed_report = MedicalReportParserService.parse(report.extracted_text)

        report.parser_mode = parsed_report.parser_mode
        report.parser_message = parsed_report.parser_message
        report.save(update_fields=["parser_mode", "parser_message"])

        if not parsed_report.tests:
            report.status = "failed"
            report.error_message = (
                parsed_report.parser_message
                or "No structured test values could be parsed. Check OCR text quality or configure Gemini API key."
            )
            report.save(update_fields=["status", "error_message", "parser_mode", "parser_message"])

            return Response(
                {
                    "error": "No structured test values could be parsed from this report.",
                    "parser_mode": parsed_report.parser_mode,
                    "parser_message": parsed_report.parser_message,
                    "hint": "If this was an image/scanned report, verify OCR text and make sure GOOGLE_API_KEY is configured.",
                    "report": MedicalReportSerializer(report).data,
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        report.test_results.all().delete()

        for parsed_test in parsed_report.tests:
            knowledge_context = MedicalKnowledgeService.retrieve_for_test(
                parsed_test.test_name,
                report_type=parsed_report.report_type,
            )

            MedicalTestResult.objects.create(
                report=report,
                test_name=parsed_test.test_name,
                value=parsed_test.value,
                flag=parsed_test.flag,
                unit=parsed_test.unit,
                reference_range=parsed_test.reference_range,
                status=parsed_test.status,
                simple_explanation=PatientExplanationService.explain_test(parsed_test, knowledge_context),
                explanation_sources=PatientExplanationService.extract_sources(knowledge_context),
                doctor_questions=PatientExplanationService.generate_doctor_questions(parsed_test),
            )

        risk_level, risk_reason = RiskTriageService.calculate_risk(parsed_report.tests)

        report.report_type = parsed_report.report_type
        report.patient_age = parsed_report.patient_age
        report.patient_gender = parsed_report.patient_gender
        report.overall_risk_level = risk_level
        report.ai_summary = risk_reason
        report.safety_note = SafetyGuardrailService.DEFAULT_SAFETY_NOTE
        report.status = "completed"
        report.error_message = ""
        report.parser_mode = parsed_report.parser_mode
        report.parser_message = parsed_report.parser_message
        report.save(
            update_fields=[
                "report_type",
                "patient_age",
                "patient_gender",
                "overall_risk_level",
                "ai_summary",
                "safety_note",
                "status",
                "error_message",
                "parser_mode",
                "parser_message",
            ]
        )

        review_text = SafetyGuardrailService.build_review_text(
            report_summary=report.ai_summary,
            test_results=list(report.test_results.all()),
        )
        safety_review = SafetyGuardrailService.review_text(
            review_text,
            risk_level=report.overall_risk_level,
        )
        SafetyAuditLog.objects.create(report=report, **safety_review)

        if safety_review["final_safety_status"] == "blocked":
            report.status = "failed"
            report.error_message = "Unsafe AI output was blocked by MedSenseAI safety guardrails."
            report.save(update_fields=["status", "error_message"])
            return Response(
                {
                    "error": "Unsafe AI output was blocked by safety guardrails.",
                    "safety_review": safety_review,
                    "report": MedicalReportSerializer(report).data,
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(
            {
                "message": "Report parsed successfully.",
                "parser_mode": parsed_report.parser_mode,
                "parser_message": parsed_report.parser_message,
                "report": MedicalReportSerializer(report).data,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as exc:
        report.status = "failed"
        report.error_message = str(exc)
        report.save(update_fields=["status", "error_message"])

        return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_knowledge_documents(request):
    documents = MedicalKnowledgeDocument.objects.all()
    serializer = MedicalKnowledgeDocumentSerializer(documents, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def seed_knowledge_documents(request):
    created_count = MedicalKnowledgeService.seed_default_documents()
    documents = MedicalKnowledgeDocument.objects.all()
    serializer = MedicalKnowledgeDocumentSerializer(documents, many=True)
    return Response(
        {
            "message": "Default trusted medical knowledge documents are ready.",
            "created_count": created_count,
            "total_documents": documents.count(),
            "documents": serializer.data,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_safety_audits(request):
    audits = SafetyAuditLog.objects.select_related("report").filter(report__user=request.user)
    serializer = SafetyAuditLogSerializer(audits, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_safety_audits(request, report_id):
    report, error_response = _get_owned_report_or_404(request, report_id)

    if error_response:
        return error_response

    audits = report.safety_audits.all()
    serializer = SafetyAuditLogSerializer(audits, many=True)
    return Response(serializer.data)
