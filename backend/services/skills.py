"""Skill taxonomy + extraction. Pure Python (no external deps) so it is easy to test."""
from __future__ import annotations

import re

# canonical name -> aliases (lowercase)
SKILLS: dict[str, list[str]] = {
    "Python": ["python"], "Java": ["java"], "JavaScript": ["javascript", "js", "es6"], "TypeScript": ["typescript"],
    "C++": ["c++"], "C#": ["c#"], "Go": ["golang"], "Rust": ["rust"], "Kotlin": ["kotlin"], "Swift": ["swift"],
    "PHP": ["php"], "Ruby": ["ruby"], "Scala": ["scala"], "SQL": ["sql"], "Bash": ["bash", "shell scripting"],
    "React": ["react", "react.js", "reactjs"], "Next.js": ["next.js", "nextjs"], "Vue": ["vue", "vue.js"],
    "Angular": ["angular"], "HTML": ["html", "html5"], "CSS": ["css", "css3"], "Tailwind CSS": ["tailwind", "tailwindcss"],
    "Redux": ["redux"], "Node.js": ["node.js", "nodejs", "node"], "Express": ["express", "express.js"],
    "FastAPI": ["fastapi"], "Django": ["django"], "Flask": ["flask"], "Spring Boot": ["spring boot", "springboot", "spring"],
    ".NET": [".net", "asp.net", "dotnet"], "GraphQL": ["graphql"], "REST APIs": ["rest", "restful", "rest api", "rest apis"],
    "Microservices": ["microservices"],
    "Pandas": ["pandas"], "NumPy": ["numpy"], "Scikit-learn": ["scikit-learn", "sklearn"], "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"], "Machine Learning": ["machine learning", "ml"], "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"], "Computer Vision": ["computer vision", "opencv"],
    "LLMs": ["llm", "llms", "large language model", "large language models"], "LangChain": ["langchain"],
    "LangGraph": ["langgraph"], "RAG": ["rag", "retrieval augmented generation"], "Generative AI": ["generative ai", "genai"],
    "Data Analysis": ["data analysis", "data analytics"], "Statistics": ["statistics"], "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"], "Excel": ["excel", "advanced excel"], "Spark": ["spark", "pyspark"], "Airflow": ["airflow"],
    "ETL": ["etl"], "Data Engineering": ["data engineering"],
    "PostgreSQL": ["postgresql", "postgres"], "MySQL": ["mysql"], "MongoDB": ["mongodb", "mongo"], "Redis": ["redis"],
    "SQLite": ["sqlite"], "Elasticsearch": ["elasticsearch"], "Kafka": ["kafka"],
    "AWS": ["aws", "amazon web services"], "Azure": ["azure"], "GCP": ["gcp", "google cloud"], "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"], "Terraform": ["terraform"], "CI/CD": ["ci/cd", "cicd", "jenkins", "github actions"],
    "Linux": ["linux"], "Git": ["git", "github", "gitlab"], "DevOps": ["devops"], "Ansible": ["ansible"],
    "Android": ["android"], "iOS": ["ios"], "Flutter": ["flutter"], "React Native": ["react native"],
    "Selenium": ["selenium"], "Cypress": ["cypress"], "Testing": ["unit testing", "pytest", "jest", "test automation", "qa"],
    "Agile": ["agile", "scrum"], "Figma": ["figma"], "UI/UX": ["ui/ux", "ux design"], "Product Management": ["product management"],
    "SEO": ["seo"], "Communication": ["communication"], "Leadership": ["leadership", "team lead"],
}

_CANON_LOOKUP: dict[str, str] = {}
for _canon, _aliases in SKILLS.items():
    _CANON_LOOKUP[_canon.lower()] = _canon
    for _a in _aliases:
        _CANON_LOOKUP[_a] = _canon

_PATTERNS: list[tuple[str, re.Pattern[str]]] = []
for _alias, _canon in sorted(_CANON_LOOKUP.items(), key=lambda kv: -len(kv[0])):
    _PATTERNS.append((_canon, re.compile(r"(?<![A-Za-z0-9+#.])" + re.escape(_alias) + r"(?![A-Za-z0-9+#])", re.IGNORECASE)))

ROLE_CLUSTERS: dict[str, set[str]] = {
    "Frontend Engineer": {"React", "Vue", "Angular", "JavaScript", "TypeScript", "HTML", "CSS", "Tailwind CSS", "Next.js", "Redux"},
    "Backend Engineer": {"Python", "Java", "Node.js", "FastAPI", "Django", "Flask", "Spring Boot", "PostgreSQL", "REST APIs", "Microservices", "Express", ".NET", "Go"},
    "Data Scientist": {"Machine Learning", "Pandas", "NumPy", "Scikit-learn", "Statistics", "Deep Learning", "TensorFlow", "PyTorch"},
    "AI / ML Engineer": {"LLMs", "LangChain", "LangGraph", "RAG", "Generative AI", "NLP", "PyTorch", "TensorFlow", "Machine Learning"},
    "DevOps Engineer": {"Docker", "Kubernetes", "Terraform", "AWS", "Azure", "GCP", "CI/CD", "Linux", "Ansible", "DevOps"},
    "Data Analyst": {"SQL", "Excel", "Power BI", "Tableau", "Data Analysis", "Statistics"},
    "Data Engineer": {"Spark", "Airflow", "ETL", "Kafka", "Data Engineering", "SQL"},
    "Mobile Developer": {"Android", "iOS", "Flutter", "React Native", "Kotlin", "Swift"},
    "QA Engineer": {"Selenium", "Cypress", "Testing"},
}


def extract_skills(text: str) -> list[str]:
    """Return canonical skills found in text, ordered by first appearance."""
    found: dict[str, int] = {}
    for canon, pat in _PATTERNS:
        m = pat.search(text or "")
        if m and (canon not in found or m.start() < found[canon]):
            found[canon] = m.start()
    return [k for k, _ in sorted(found.items(), key=lambda kv: kv[1])]


def infer_roles(skills: list[str], limit: int = 3) -> list[str]:
    have = set(skills)
    scored = [(len(have & cluster), role) for role, cluster in ROLE_CLUSTERS.items()]
    scored = [s for s in scored if s[0] >= 2]
    scored.sort(reverse=True)
    roles = [r for _, r in scored[:limit]]
    if {"Frontend Engineer", "Backend Engineer"} <= set(roles[:2]):
        roles.insert(0, "Full Stack Developer")
    return roles[: limit + 1] or ["Software Engineer"]
