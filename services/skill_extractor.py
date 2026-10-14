import re


SKILLS = (
    "python", "flask", "django", "fastapi", "java", "javascript", "typescript",
    "html", "css", "react", "next.js", "node.js", "sql", "mysql", "postgresql",
    "mongodb", "redis", "aws", "azure", "gcp", "docker", "kubernetes", "linux",
    "git", "ci/cd", "machine learning", "deep learning", "data analysis", "pandas",
    "numpy", "tensorflow", "pytorch", "rest api", "graphql", "selenium", "pytest",
    "communication", "project management", "agile", "excel", "power bi", "tableau",
)


def extract_skills(text: str) -> list[str]:
    normalized = (text or "").lower()
    return [skill for skill in SKILLS if re.search(r"(?<![\w+#])" + re.escape(skill) + r"(?![\w+#])", normalized)]
