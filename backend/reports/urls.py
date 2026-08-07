from django.urls import path
from . import views

urlpatterns = [
    path("upload/", views.upload_report, name="upload_report"),
    path("", views.list_reports, name="list_reports"),
    path("<int:report_id>/", views.report_detail, name="report_detail"),
    path("<int:report_id>/download/", views.download_report_file, name="download_report_file"),
    path("<int:report_id>/patient-view/", views.patient_friendly_report_view, name="patient_friendly_report_view"),
    path("<int:report_id>/extract-text/", views.extract_report_text, name="extract_report_text"),
    path("<int:report_id>/parse/", views.parse_report, name="parse_report"),
    path("knowledge/", views.list_knowledge_documents, name="list_knowledge_documents"),
    path("knowledge/seed/", views.seed_knowledge_documents, name="seed_knowledge_documents"),
    path("safety-audits/", views.list_safety_audits, name="list_safety_audits"),
    path("<int:report_id>/safety-audits/", views.report_safety_audits, name="report_safety_audits"),
]
