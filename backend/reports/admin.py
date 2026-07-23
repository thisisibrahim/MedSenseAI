from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import MedicalKnowledgeDocument, MedicalReport, MedicalTestResult, SafetyAuditLog


class MedicalTestResultInline(admin.TabularInline):
    model = MedicalTestResult
    extra = 0


class SafetyAuditLogInline(admin.TabularInline):
    model = SafetyAuditLog
    extra = 0
    readonly_fields = [
        "risk_level",
        "blocked_diagnosis_claims",
        "blocked_treatment_advice",
        "blocked_false_reassurance",
        "safety_warnings",
        "final_safety_status",
        "created_at",
    ]
    can_delete = False


@admin.register(MedicalReport)
class MedicalReportAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "original_filename",
        "report_type",
        "patient_age",
        "patient_gender",
        "overall_risk_level",
        "status",
        "created_at",
    ]
    list_filter = ["status", "overall_risk_level", "report_type", "patient_gender", "created_at"]
    search_fields = ["original_filename", "report_type", "patient_age", "patient_gender", "extracted_text"]
    inlines = [MedicalTestResultInline, SafetyAuditLogInline]


@admin.register(MedicalTestResult)
class MedicalTestResultAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "report",
        "test_name",
        "value",
        "flag",
        "unit",
        "status",
    ]
    list_filter = ["status"]
    search_fields = ["test_name", "value"]

@admin.register(MedicalKnowledgeDocument)
class MedicalKnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "title",
        "source_name",
        "report_type",
        "is_active",
        "updated_at",
    ]
    list_filter = ["source_name", "report_type", "is_active"]
    search_fields = ["title", "source_name", "test_names", "content"]


@admin.register(SafetyAuditLog)
class SafetyAuditLogAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "report",
        "risk_level",
        "final_safety_status",
        "created_at",
    ]
    list_filter = ["risk_level", "final_safety_status", "created_at"]
    search_fields = [
        "report__original_filename",
        "reviewed_text_excerpt",
    ]
    readonly_fields = ["created_at"]
