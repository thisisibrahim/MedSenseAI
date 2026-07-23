from django.conf import settings
from django.db import models


class MedicalReport(models.Model):
    REPORT_STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    RISK_LEVEL_CHOICES = [
        ("green", "Green"),
        ("yellow", "Yellow"),
        ("orange", "Orange"),
        ("red", "Red"),
        ("unknown", "Unknown"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    file = models.FileField(upload_to="medical_reports/")
    original_filename = models.CharField(max_length=255, blank=True)

    report_type = models.CharField(max_length=100, blank=True)
    patient_age = models.CharField(max_length=50, blank=True)
    patient_gender = models.CharField(max_length=50, blank=True)
    extracted_text = models.TextField(blank=True)

    ai_summary = models.TextField(blank=True)
    safety_note = models.TextField(blank=True)

    overall_risk_level = models.CharField(
        max_length=20,
        choices=RISK_LEVEL_CHOICES,
        default="unknown",
    )

    status = models.CharField(
        max_length=20,
        choices=REPORT_STATUS_CHOICES,
        default="uploaded",
    )

    error_message = models.TextField(blank=True)
    
    parser_mode = models.CharField(max_length=50, blank=True)
    parser_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report #{self.id} - {self.original_filename or 'Medical Report'}"


class MedicalTestResult(models.Model):
    STATUS_CHOICES = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("borderline", "Borderline"),
        ("unknown", "Unknown"),
    ]

    report = models.ForeignKey(
        MedicalReport,
        on_delete=models.CASCADE,
        related_name="test_results",
    )

    test_name = models.CharField(max_length=255)
    value = models.CharField(max_length=100, blank=True)
    flag = models.CharField(max_length=50, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    reference_range = models.CharField(max_length=100, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="unknown",
    )

    simple_explanation = models.TextField(blank=True)
    explanation_sources = models.JSONField(default=list, blank=True)
    doctor_questions = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.test_name}: {self.value} {self.unit}"

class MedicalKnowledgeDocument(models.Model):
    REPORT_TYPE_CHOICES = [
        ("cbc", "Complete Blood Count"),
        ("lft", "Liver Function Test"),
        ("kft", "Kidney Function Test"),
        ("thyroid", "Thyroid Profile"),
        ("lipid", "Lipid Profile"),
        ("diabetes", "Diabetes Report"),
        ("general", "General"),
    ]

    title = models.CharField(max_length=255)
    source_name = models.CharField(max_length=100)
    source_url = models.URLField(blank=True)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES, default="general")
    test_names = models.JSONField(default=list, blank=True)
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_name", "title"]

    def __str__(self):
        return f"{self.title} ({self.source_name})"


class SafetyAuditLog(models.Model):
    """
    Stores safety review results for each AI-generated report output.
    This makes MedSenseAI auditable: diagnosis, prescription, dosage, and false-reassurance
    language can be detected, blocked, and reviewed later.
    """

    SAFETY_STATUS_CHOICES = [
        ("passed", "Passed"),
        ("review_required", "Review Required"),
        ("blocked", "Blocked"),
    ]

    report = models.ForeignKey(
        MedicalReport,
        on_delete=models.CASCADE,
        related_name="safety_audits",
    )

    risk_level = models.CharField(max_length=20, blank=True)
    blocked_diagnosis_claims = models.JSONField(default=list, blank=True)
    blocked_treatment_advice = models.JSONField(default=list, blank=True)
    blocked_false_reassurance = models.JSONField(default=list, blank=True)
    safety_warnings = models.JSONField(default=list, blank=True)

    final_safety_status = models.CharField(
        max_length=30,
        choices=SAFETY_STATUS_CHOICES,
        default="passed",
    )

    reviewed_text_excerpt = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Safety audit for report #{self.report_id} - {self.final_safety_status}"