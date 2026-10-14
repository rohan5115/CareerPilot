from services.cover_letter_generator import generate_cover_letter
from services.interview_questions import generate_interview_questions
from services.job_matcher import calculate_match_score
from services.resume_generator import generate_tailored_resume
from services.resume_suggestions import generate_resume_suggestions


def generate_ai_package(resume_text, resume_skills, job_description):
    score, matched, missing = calculate_match_score(resume_skills, job_description)
    return {
        "score": score,
        "matched": matched,
        "missing": missing,
        "cover_letter": generate_cover_letter(resume_text, resume_skills, job_description),
        "tailored_resume": generate_tailored_resume(resume_text, job_description),
        "suggestions": generate_resume_suggestions(resume_text, resume_skills, job_description),
        "interview_questions": generate_interview_questions(resume_text, resume_skills, job_description),
    }
