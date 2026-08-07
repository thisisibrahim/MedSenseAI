import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import MedicalReport


TEMP_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class MedicalReportFileSecurityTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="StrongPassword123!",
        )
        self.other_user = User.objects.create_user(
            username="other-user",
            email="other@example.com",
            password="StrongPassword123!",
        )

        self.owner_token = Token.objects.create(user=self.owner)
        self.other_token = Token.objects.create(user=self.other_user)

        upload = SimpleUploadedFile(
            "cbc-report.pdf",
            b"%PDF-1.4\nSensitive medical report test content\n%%EOF",
            content_type="application/pdf",
        )

        self.report = MedicalReport.objects.create(
            user=self.owner,
            file=upload,
            original_filename="cbc-report.pdf",
        )

        self.download_url = f"/api/reports/{self.report.id}/download/"

    def authenticate(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_anonymous_user_cannot_download_report(self):
        response = self.client.get(self.download_url)
        self.assertIn(response.status_code, (401, 403))

    def test_owner_can_download_report(self):
        self.authenticate(self.owner_token)

        response = self.client.get(self.download_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="cbc-report.pdf"',
        )

        content = b"".join(response.streaming_content)
        self.assertIn(b"Sensitive medical report test content", content)

    def test_other_user_cannot_download_owners_report(self):
        self.authenticate(self.other_token)

        response = self.client.get(self.download_url)

        self.assertEqual(response.status_code, 404)

    def test_direct_media_url_is_not_publicly_served(self):
        direct_media_url = f"/media/{self.report.file.name}"

        response = self.client.get(direct_media_url)

        self.assertEqual(response.status_code, 404)

    def test_stored_filename_is_randomized(self):
        stored_name = Path(self.report.file.name)

        self.assertEqual(stored_name.parent.as_posix(), "medical_reports")
        self.assertEqual(stored_name.suffix, ".pdf")
        self.assertNotEqual(stored_name.name, "cbc-report.pdf")

        stem = stored_name.stem
        self.assertEqual(len(stem), 32)
        int(stem, 16)

    def test_report_serializer_does_not_expose_raw_media_url(self):
        self.authenticate(self.owner_token)

        response = self.client.get(f"/api/reports/{self.report.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("file", response.data)
        self.assertEqual(response.data["download_url"], self.download_url)

    def test_upload_preserves_original_filename_but_randomizes_storage_name(self):
        self.authenticate(self.owner_token)

        upload = SimpleUploadedFile(
            "my-private-lab-report.pdf",
            b"%PDF-1.4\nAnother private report\n%%EOF",
            content_type="application/pdf",
        )

        response = self.client.post(
            "/api/reports/upload/",
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)

        created_report = MedicalReport.objects.get(
            id=response.data["report"]["id"]
        )

        self.assertEqual(
            created_report.original_filename,
            "my-private-lab-report.pdf",
        )
        self.assertNotEqual(
            Path(created_report.file.name).name,
            "my-private-lab-report.pdf",
        )
        self.assertNotIn("file", response.data["report"])
        self.assertEqual(
            response.data["report"]["download_url"],
            f"/api/reports/{created_report.id}/download/",
        )
