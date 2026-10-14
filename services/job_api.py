import logging
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Adzuna requires credentials in query parameters, so urllib3's retry warnings
# would otherwise log the API key. Keep that logger quiet for these requests.
logging.getLogger("urllib3.connectionpool").disabled = True


class JobSearchError(RuntimeError):
    """Safe user-facing search error that never includes the credential-bearing URL."""


def search_jobs(keyword, location):
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        raise JobSearchError("Add ADZUNA_APP_ID and ADZUNA_APP_KEY to .env, then restart the app.")
    retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=0.4,
                  status_forcelist=(500, 502, 503, 504),
                  allowed_methods=frozenset({"GET"}), raise_on_status=False)
    country = os.getenv("ADZUNA_COUNTRY", "in").strip().lower()
    if len(country) != 2 or not country.isalpha():
        raise JobSearchError("ADZUNA_COUNTRY must be a two-letter country code, such as in or gb.")
    try:
        with requests.Session() as client:
            client.mount("https://", HTTPAdapter(max_retries=retry))
            response = client.get(
                f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                params={"app_id": app_id, "app_key": app_key, "results_per_page": 10,
                        "what": keyword, "where": location, "content-type": "application/json"},
                headers={"Accept": "application/json"},
                timeout=(4, 12),
            )
    except requests.Timeout:
        raise JobSearchError("Adzuna took too long to respond. Please try again.") from None
    except requests.ConnectionError:
        raise JobSearchError("Could not connect to Adzuna. Check your internet connection and try again.") from None
    except requests.RequestException:
        raise JobSearchError("Adzuna search could not be completed. Please try again.") from None
    if response.status_code != 200:
        messages = {
            400: "Adzuna rejected the search request. Check the country code and search terms.",
            401: "Adzuna rejected the API credentials. Verify ADZUNA_APP_ID and ADZUNA_APP_KEY in .env.",
            403: "Adzuna denied access to this API app. Check that the credentials are active and enabled for job search.",
            404: "Adzuna does not have this job-search region available. Change ADZUNA_COUNTRY in .env.",
            429: "Adzuna rate limit reached. Wait a little and try again.",
        }
        raise JobSearchError(messages.get(response.status_code, f"Adzuna returned an error (HTTP {response.status_code}). Please try again later."))
    try:
        data = response.json()
    except ValueError:
        raise JobSearchError("Adzuna returned an unreadable response. Please try again later.") from None
    jobs = []
    for item in data.get("results", []):
        jobs.append({
            "company": item.get("company", {}).get("display_name") or "Company not listed",
            "role": item.get("title") or "Role not listed",
            "location": item.get("location", {}).get("display_name") or "Location not listed",
            "description": item.get("description") or "",
            "salary_min": item.get("salary_min"),
            "salary_max": item.get("salary_max"),
            "redirect_url": item.get("redirect_url") or "",
        })
    return jobs
