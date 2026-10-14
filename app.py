"""Flask application for the AI Job Agent."""
from __future__ import annotations

import io
import logging
import os
import secrets
import uuid
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from markupsafe import escape
from werkzeug.exceptions import RequestEntityTooLarge

from services.ai_package import generate_ai_package
from services.cover_letter_generator import generate_cover_letter
from services.database import (
    create_tables, get_applications, get_average_score, get_company_count,
    get_highest_score, get_total_applications, get_workspace, save_application,
    save_workspace,
)
from services.interview_questions import generate_interview_questions
from services.job_api import JobSearchError, search_jobs
from services.job_matcher import calculate_match_score
from services.resume_generator import generate_tailored_resume
from services.resume_parser import extract_text_from_pdf
from services.resume_suggestions import generate_resume_suggestions
from services.skill_extractor import extract_skills

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        DATABASE_PATH=os.getenv("DATABASE_PATH", "instance/jobs.db"),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        ALLOWED_EXTENSIONS={"pdf"},
    )
    if test_config:
        app.config.update(test_config)

    create_tables(app.config["DATABASE_PATH"])

    @app.before_request
    def bind_workspace() -> None:
        # The signed session contains only an opaque identifier; resume data remains server-side.
        if "workspace_id" not in session:
            session["workspace_id"] = uuid.uuid4().hex

    def state() -> dict:
        return get_workspace(app.config["DATABASE_PATH"], session["workspace_id"])

    def update_state(**fields) -> None:
        current = state()
        current.update(fields)
        save_workspace(app.config["DATABASE_PATH"], session["workspace_id"], current)

    def require_resume(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            current = state()
            if not current.get("resume_text"):
                flash("Upload a PDF resume before using the career tools.", "warning")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        flash("That file is too large. Choose a PDF under 8 MB.", "danger")
        return redirect(url_for("dashboard")), 413

    @app.errorhandler(400)
    def bad_request(_error):
        flash("The request could not be processed. Check the form and try again.", "danger")
        return redirect(url_for("dashboard")), 400

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Unhandled request error: %s", error)
        return render_template("error.html", code=500,
                               message="Something went wrong while processing that request. Please try again."), 500

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.route("/dashboard")
    def dashboard():
        current = state()
        return render_template("dashboard.html", **current)

    @app.post("/upload_resume")
    def upload_resume():
        resume = request.files.get("resume")
        if not resume or not resume.filename:
            flash("Choose a PDF resume to upload.", "warning")
            return redirect(url_for("dashboard"))
        if "." not in resume.filename or resume.filename.rsplit(".", 1)[1].lower() not in app.config["ALLOWED_EXTENSIONS"]:
            flash("Only PDF resumes are supported.", "danger")
            return redirect(url_for("dashboard"))
        payload = resume.read(app.config["MAX_CONTENT_LENGTH"] + 1)
        if len(payload) > app.config["MAX_CONTENT_LENGTH"]:
            flash("That file is too large. Choose a PDF under 8 MB.", "danger")
            return redirect(url_for("dashboard"))
        if not payload.startswith(b"%PDF-"):
            flash("This file does not look like a valid PDF.", "danger")
            return redirect(url_for("dashboard"))
        try:
            text = extract_text_from_pdf(io.BytesIO(payload))
        except Exception as exc:
            logger.info("Resume parsing failed: %s", exc)
            flash("We couldn't read that PDF. Try an unlocked, text-based PDF.", "danger")
            return redirect(url_for("dashboard"))
        if not text.strip():
            flash("No selectable text was found. Scanned PDFs need OCR before upload.", "warning")
            return redirect(url_for("dashboard"))
        update_state(resume_text=text[:50000], skills=extract_skills(text), resume_name=resume.filename)
        flash("Resume uploaded and analyzed.", "success")
        return redirect(url_for("dashboard"))

    @app.post("/match_job")
    @require_resume
    def match_job():
        description = request.form.get("job_description", "").strip()
        if not description:
            flash("Paste a job description to calculate a match.", "warning")
            return redirect(url_for("dashboard"))
        current = state()
        score, matched, missing = calculate_match_score(current["skills"], description)
        return render_template("dashboard.html", **current, job_description=description,
                               score=score, matched=matched, missing=missing)

    def generate_result(generator, result_key: str, title: str):
        current = state()
        description = request.form.get("job_description", "").strip()
        if not description:
            flash("Paste a job description first.", "warning")
            return redirect(url_for("dashboard"))
        try:
            result = generator(current, description)
        except Exception as exc:
            logger.warning("AI generation failed (%s): %s", title, exc)
            flash(f"{title} could not be generated right now. Check your AI key and try again.", "danger")
            return render_template("dashboard.html", **current, job_description=description), 503
        update_state(**{result_key: result})
        if not os.getenv("GEMINI_API_KEY", "").strip():
            flash("Showing a local starter draft. Add GEMINI_API_KEY in .env for personalized AI writing.", "warning")
        score, matched, missing = calculate_match_score(current["skills"], description)
        current = state()
        return render_template("dashboard.html", **current, job_description=description,
                               score=score, matched=matched, missing=missing)

    @app.post("/generate_cover_letter")
    @require_resume
    def cover_letter():
        return generate_result(lambda current, description: generate_cover_letter(current["resume_text"], current["skills"], description), "cover_letter", "Cover letter")

    @app.post("/resume_suggestions")
    @require_resume
    def resume_suggestions():
        return generate_result(lambda current, description: generate_resume_suggestions(current["resume_text"], current["skills"], description), "suggestions", "Resume suggestions")

    @app.post("/interview_questions")
    @require_resume
    def interview_questions():
        return generate_result(lambda current, description: generate_interview_questions(current["resume_text"], current["skills"], description), "interview_questions", "Interview questions")

    @app.post("/tailored_resume")
    @require_resume
    def tailored_resume():
        return generate_result(lambda current, description: generate_tailored_resume(current["resume_text"], description), "tailored_resume", "Tailored resume")

    @app.post("/generate_ai_package")
    @require_resume
    def generate_complete_ai_package():
        return generate_result(lambda current, description: generate_ai_package(current["resume_text"], current["skills"], description), "ai_package", "Career package")

    @app.post("/save_application")
    def save_job():
        company = request.form.get("company", "").strip()[:120]
        role = request.form.get("role", "").strip()[:160]
        try:
            score = int(request.form.get("score", ""))
        except ValueError:
            score = -1
        if not company or not role or not 0 <= score <= 100:
            flash("Enter a company and role and use a valid match score.", "warning")
            return redirect(url_for("dashboard"))
        save_application(app.config["DATABASE_PATH"], company, role, score)
        flash("Application added to your tracker.", "success")
        return redirect(url_for("applications"))

    @app.route("/applications")
    def applications():
        return render_template("applications.html", applications=get_applications(app.config["DATABASE_PATH"]))

    @app.route("/analytics")
    def analytics():
        path = app.config["DATABASE_PATH"]
        return render_template("analytics.html", total=get_total_applications(path),
                               avg_score=get_average_score(path), highest=get_highest_score(path),
                               companies=get_company_count(path), applications=get_applications(path)[:8])

    @app.route("/jobs")
    def jobs():
        return render_template("jobs.html", jobs=[], keyword="", location="", searched=False)

    @app.post("/search_jobs")
    def search_jobs_route():
        keyword = request.form.get("keyword", "").strip()[:100]
        location = request.form.get("location", "").strip()[:100]
        if not keyword or not location:
            flash("Enter both a role or keyword and a location.", "warning")
            return redirect(url_for("jobs"))
        try:
            results = search_jobs(keyword, location)
            error = None
        except JobSearchError as exc:
            results, error = [], str(exc)
        except Exception as exc:
            # Avoid logging request exceptions: their URLs may contain API credentials.
            logger.warning("Job search failed (%s)", type(exc).__name__)
            results, error = [], "Job search is temporarily unavailable. Check the Adzuna settings and try again."
        return render_template("jobs.html", jobs=results, keyword=keyword, location=location,
                               searched=True, search_error=error)

    @app.get("/download/<document>")
    def download_document(document: str):
        keys = {"resume": "tailored_resume", "cover-letter": "cover_letter"}
        if document not in keys:
            abort(404)
        text = state().get(keys[document])
        if not text:
            flash("Generate the document before downloading it.", "warning")
            return redirect(url_for("dashboard"))
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, title="AI Job Agent document", rightMargin=48, leftMargin=48)
        styles = getSampleStyleSheet()
        story = []
        for line in text.splitlines():
            story.append(Paragraph(escape(line) or "&nbsp;", styles["BodyText"]))
            story.append(Spacer(1, 5))
        doc.build(story)
        output.seek(0)
        filename = "Tailored_Resume.pdf" if document == "resume" else "Cover_Letter.pdf"
        return send_file(output, as_attachment=True, download_name=filename, mimetype="application/pdf")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
