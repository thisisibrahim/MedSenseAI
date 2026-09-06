from rest_framework import serializers
from .models import MedicalKnowledgeDocument, MedicalReport, MedicalTestResult, SafetyAuditLog


class MedicalTestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalTestResult
        fields = [
            "id", "test_name", "value", "flag", "unit", "reference_range",
            "status", "simple_explanation", "explanation_sources",
            "doctor_questions", "created_at",
        ]


class MedicalReportSerializer(serializers.ModelSerializer):
    test_results = MedicalTestResultSerializer(many=True, read_only=True)
    owner_username = serializers.CharField(source="user.username", read_only=True)
    download_url = serializers.SerializerMethodField()
    file = serializers.FileField(write_only=True)   # ← added

    def get_download_url(self, obj):
        return f"/api/reports/{obj.id}/download/"

    class Meta:
        model = MedicalReport
        fields = [
            "id", "owner_username", "download_url", "file", "original_filename",  # ← "file" added here
            "report_type", "patient_age", "patient_gender", "extracted_text",
            "ai_summary", "safety_note", "overall_risk_level", "status",
            "error_message", "parser_mode", "parser_message", "test_results",
            "created_at", "updated_at",
        ]
        # read_only_fields unchanged — "file" isn't in it, so it stays writable on input


class MedicalKnowledgeDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalKnowledgeDocument
        fields = [
            "id", "title", "source_name", "source_url", "report_type",
            "test_names", "content", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class SafetyAuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SafetyAuditLog
        fields = [
            "id", "report", "risk_level", "blocked_diagnosis_claims",
            "blocked_treatment_advice", "blocked_false_reassurance",
            "safety_warnings", "final_safety_status", "reviewed_text_excerpt",
            "created_at",
        ]
        read_only_fields = fields
