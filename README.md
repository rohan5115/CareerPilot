# CareerPilot · AI Job Agent

A local Flask app for comparing a resume with job descriptions, drafting application materials, preparing for interviews, searching job listings, and tracking applications.

## Requirements

- Python 3.10 or newer
- Optional Gemini API key for AI-generated writing
- Optional Adzuna credentials for live job search

The app works without either API. AI features return clearly scoped local draft templates; live job search requires Adzuna credentials.

## Run locally (Windows PowerShell)

```powershell
cd D:\Desktop\ai-job-agent\ai-job-agent
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open http://127.0.0.1:5000. Edit `.env` to add API keys if you want AI writing or live job search. `ADZUNA_COUNTRY` is a two-letter region code and defaults to `in`. Use a long random `SECRET_KEY` for a shared or internet-facing deployment. The app stores the SQLite database under `instance/` by default and keeps uploaded resume text on the local machine, scoped to a signed browser session.

## Run locally (macOS / Linux)

```sh
cd ai-job-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## Verify

```sh
python -m unittest discover -s tests -v
```

The tests use temporary databases and mock PDF/API interactions; they do not require API keys or network access.

## Notes

- Uploads are restricted to PDFs under 8 MB. Scanned PDFs need OCR before upload.
- AI output is a draft. Review and correct every claim before using it in an application.
- Job results are fetched from Adzuna's India endpoint and are not available until credentials are configured.
- `FLASK_DEBUG=true` enables Flask's development debugger; keep it false outside local development.
