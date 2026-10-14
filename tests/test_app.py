import io
import os
import tempfile
import unittest
from reportlab.pdfgen import canvas
from unittest.mock import patch

from app import create_app
from services.job_matcher import calculate_match_score
from services.skill_extractor import extract_skills
from services.ai_client import generate_text
from services.job_api import JobSearchError, search_jobs


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_PATH": os.path.join(self.tmp.name, "test.db"),
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_pages_render(self):
        for path in ("/", "/dashboard", "/jobs", "/applications", "/analytics"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_upload_rejects_non_pdf_and_bad_pdf(self):
        response = self.client.post("/upload_resume", data={
            "resume": (io.BytesIO(b"not pdf"), "resume.pdf")
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"does not look like a valid PDF", response.data)

        response = self.client.post("/upload_resume", data={
            "resume": (io.BytesIO(b"hello"), "resume.txt")
        }, follow_redirects=True)
        self.assertIn(b"Only PDF resumes are supported", response.data)

    def test_match_scoring_uses_boundaries_and_handles_empty_description(self):
        skills = extract_skills("Python JavaScript")
        score, matched, missing = calculate_match_score(skills, "JavaScript and Java required")
        self.assertEqual(matched, ["javascript"])
        self.assertEqual(missing, ["java"])
        self.assertEqual(score, 50)
        self.assertEqual(calculate_match_score([], "No listed skills"), (0, [], []))

    def test_ai_client_uses_fallback_without_credentials(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            self.assertEqual(generate_text("prompt", "local draft"), "local draft")

    def test_ai_client_uses_google_sdk_when_configured(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}):
            with patch("google.genai.Client") as client_type:
                client_type.return_value.models.generate_content.return_value.text = "generated text"
                self.assertEqual(generate_text("prompt", "local draft"), "generated text")
                client_type.return_value.models.generate_content.assert_called_once_with(
                    model="test-model", contents="prompt"
                )
                client_type.return_value.close.assert_called_once()

    def test_workspace_data_is_isolated_between_clients(self):
        first = self.client
        second = self.app.test_client()
        first.get("/dashboard")
        with first.session_transaction() as current:
            workspace_id = current["workspace_id"]
        from services.database import save_workspace
        save_workspace(self.app.config["DATABASE_PATH"], workspace_id,
                       {"resume_text": "private resume text", "skills": ["python"]})
        self.assertIn(b"private resume text", first.get("/dashboard").data)
        self.assertNotIn(b"private resume text", second.get("/dashboard").data)

    def test_missing_resume_redirects_before_ai_work(self):
        response = self.client.post("/tailored_resume", data={"job_description": "Python"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Upload a PDF resume", response.data)

    def test_job_search_errors_are_presented_without_crashing(self):
        with patch("app.search_jobs", side_effect=RuntimeError("offline")):
            response = self.client.post("/search_jobs", data={"keyword": "engineer", "location": "Pune"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Search unavailable", response.data)

    def test_adzuna_request_maps_results_and_sanitizes_auth_errors(self):
        result = {"title": "Developer", "company": {"display_name": "Acme"},
                  "location": {"display_name": "Pune"}, "redirect_url": "https://example.test/job"}
        response = unittest.mock.Mock(status_code=200)
        response.json.return_value = {"results": [result]}
        with patch.dict(os.environ, {"ADZUNA_APP_ID": "private-id", "ADZUNA_APP_KEY": "private-key", "ADZUNA_COUNTRY": "in"}):
            with patch("services.job_api.requests.Session") as session_type:
                session_type.return_value.__enter__.return_value.get.return_value = response
                jobs = search_jobs("developer", "Pune")
                self.assertEqual(jobs[0]["company"], "Acme")
                args, kwargs = session_type.return_value.__enter__.return_value.get.call_args
                self.assertIn("/jobs/in/search/1", args[0])
                self.assertEqual(kwargs["params"]["app_id"], "private-id")

                response.status_code = 401
                with self.assertRaises(JobSearchError) as caught:
                    search_jobs("developer", "Pune")
                self.assertIn("credentials", str(caught.exception))
                self.assertNotIn("private-key", str(caught.exception))

    def test_application_save_validates_and_updates_analytics(self):
        bad = self.client.post("/save_application", data={"company": "Acme", "role": "Engineer", "score": "999"})
        self.assertEqual(bad.status_code, 302)
        response = self.client.post("/save_application", data={"company": "Acme", "role": "Engineer", "score": "82"})
        self.assertEqual(response.status_code, 302)
        page = self.client.get("/analytics")
        self.assertIn(b"82%", page.data)
        self.assertIn(b"Acme", self.client.get("/applications").data)

    def test_download_missing_document_redirects(self):
        response = self.client.get("/download/resume")
        self.assertEqual(response.status_code, 302)

    def test_pdf_upload_match_generate_and_download_flow(self):
        pdf = io.BytesIO()
        writer = canvas.Canvas(pdf)
        writer.drawString(72, 720, "Python Flask developer with Docker and PostgreSQL experience")
        writer.save()
        pdf.seek(0)
        uploaded = self.client.post("/upload_resume", data={
            "resume": (pdf, "my-resume.pdf")
        }, follow_redirects=True)
        self.assertEqual(uploaded.status_code, 200)
        self.assertIn(b"python", uploaded.data)

        match = self.client.post("/match_job", data={
            "job_description": "We need a Python developer who knows Flask and AWS."
        })
        self.assertEqual(match.status_code, 200)
        self.assertIn(b"67", match.data)

        with patch("app.generate_cover_letter", return_value="Dear Hiring Manager"):
            generated = self.client.post("/generate_cover_letter", data={
                "job_description": "Python Flask developer"
            })
        self.assertEqual(generated.status_code, 200)
        self.assertIn(b"Dear Hiring Manager", generated.data)
        download = self.client.get("/download/cover-letter")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.mimetype, "application/pdf")
        self.assertTrue(download.data.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
