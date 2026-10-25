"""PDF text extraction and heuristic resume parsing (works with no API key)."""
import io
import re

from pypdf import PdfReader

SKILLS = {
    # language / core
    "python": ["python"], "java": ["java"], "javascript": ["javascript", "js"],
    "typescript": ["typescript"], "c++": ["c++"], "c#": ["c#"], "go": ["golang"],
    "rust": ["rust"], "ruby": ["ruby"], "php": ["php"], "kotlin": ["kotlin"],
    "swift": ["swift"], "scala": ["scala"], "r": [], "sql": ["sql", "mysql", "postgresql", "postgres"],
    # web
    "react": ["react", "reactjs", "react.js"], "angular": ["angular"], "vue": ["vue", "vue.js"],
    "node.js": ["node.js", "nodejs", "node"], "django": ["django"], "flask": ["flask"],
    "fastapi": ["fastapi"], "spring": ["spring", "spring boot"], "html": ["html"], "css": ["css"],
    "rest api": ["rest", "restful", "rest api"], "graphql": ["graphql"],
    # data / ml
    "machine learning": ["machine learning", "ml"], "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"], "computer vision": ["computer vision"],
    "pytorch": ["pytorch"], "tensorflow": ["tensorflow"], "scikit-learn": ["scikit-learn", "sklearn"],
    "pandas": ["pandas"], "numpy": ["numpy"], "spark": ["spark", "pyspark"],
    "data analysis": ["data analysis", "data analytics"], "tableau": ["tableau"], "power bi": ["power bi"],
    "llm": ["llm", "llms", "large language models"],
    # infra
    "aws": ["aws", "amazon web services"], "azure": ["azure"], "gcp": ["gcp", "google cloud"],
    "docker": ["docker"], "kubernetes": ["kubernetes", "k8s"], "terraform": ["terraform"],
    "ci/cd": ["ci/cd", "jenkins", "github actions", "gitlab ci"], "git": ["git", "github", "gitlab"],
    "linux": ["linux"], "mongodb": ["mongodb"], "redis": ["redis"], "kafka": ["kafka"],
    "elasticsearch": ["elasticsearch"],
    # general / business
    "agile": ["agile", "scrum"], "project management": ["project management"],
    "communication": ["communication"], "leadership": ["leadership"],
    "excel": ["excel"], "recruiting": ["recruiting", "talent acquisition", "sourcing"],
    "sales": ["sales"], "marketing": ["marketing"], "seo": ["seo"], "figma": ["figma"],
}

_ALIAS_RE = {}
for canon, aliases in SKILLS.items():
    for a in {canon, *aliases}:
        _ALIAS_RE[a] = re.compile(r"(?<![\w+#.])" + re.escape(a) + r"(?![\w+#]|\.\w)", re.I)


def extract_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = [(p.extract_text() or "") for p in reader.pages]
    return "\n".join(pages).strip()


def find_skills(text: str) -> list[str]:
    found = []
    for canon, aliases in SKILLS.items():
        if any(_ALIAS_RE[a].search(text) for a in {canon, *aliases}):
            found.append(canon)
    return sorted(found)


def normalize_skill(s: str) -> str:
    s = s.strip().lower()
    for canon, aliases in SKILLS.items():
        if s == canon or s in aliases:
            return canon
    return s


def _name(text: str) -> str:
    for line in text.splitlines()[:8]:
        line = line.strip()
        if not line or any(ch.isdigit() for ch in line) or "@" in line:
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z.\-']+", w) for w in words):
            return line.title() if line.isupper() else line
    return "Unknown"


def _years(text: str) -> float:
    best = 0.0
    for m in re.finditer(r"(\d{1,2})\+?\s*(?:years|yrs)", text, re.I):
        best = max(best, float(m.group(1)))
    if best:
        return best
    # fall back: span of year ranges like 2018 - 2023 / 2020 - Present
    total = 0
    for m in re.finditer(r"((?:19|20)\d{2})\s*[-–to]+\s*((?:19|20)\d{2}|present|current)", text, re.I):
        start = int(m.group(1))
        end = 2026 if m.group(2).lower() in ("present", "current") else int(m.group(2))
        if 0 <= end - start <= 40:
            total += end - start
    return float(min(total, 40))


def _education(text: str) -> str:
    levels = [
        ("PhD", r"ph\.?d|doctorate"), ("Master's", r"master|m\.?s\.?c|m\.?tech|mba|m\.?s\b"),
        ("Bachelor's", r"bachelor|b\.?tech|b\.?e\b|b\.?sc|b\.?s\b|b\.?a\b"),
    ]
    for label, pat in levels:
        if re.search(r"\b(?:" + pat + r")", text, re.I):
            return label
    return ""


def heuristic_parse(text: str) -> dict:
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3,5}\)?[\s-]?)\d{3,4}[\s-]?\d{3,4}", text)
    skills = find_skills(text)
    years = _years(text)
    name = _name(text)
    summary = f"{name} — {years:g} yrs experience. Key skills: {', '.join(skills[:8]) or 'n/a'}."
    return {
        "name": name,
        "email": email.group(0) if email else "",
        "phone": phone.group(0).strip() if phone else "",
        "skills": skills,
        "years_experience": years,
        "education": _education(text),
        "summary": summary,
    }
