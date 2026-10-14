import re

from services.skill_extractor import SKILLS


def calculate_match_score(resume_skills, job_description):
    """Compare the recognized skill terms using token boundaries (so e.g. Java != JavaScript)."""
    description = (job_description or "").lower()
    resume = {str(skill).lower() for skill in (resume_skills or [])}
    required = [skill for skill in SKILLS if re.search(r"(?<![\w+#])" + re.escape(skill) + r"(?![\w+#])", description)]
    matched = [skill for skill in required if skill in resume]
    missing = [skill for skill in required if skill not in resume]
    score = round((len(matched) / len(required)) * 100) if required else 0
    return score, matched, missing
