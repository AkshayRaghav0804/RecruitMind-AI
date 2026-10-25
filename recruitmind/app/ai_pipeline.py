"""Optional Claude-powered pipeline. Every function degrades gracefully when no API key is set."""
import json
import os

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")


def enabled() -> bool:
    return bool(anthropic and os.getenv("ANTHROPIC_API_KEY"))


def _ask(system: str, user: str, max_tokens: int = 1024) -> str:
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


def parse_resume(text: str) -> dict | None:
    if not enabled():
        return None
    system = (
        "You extract structured data from resumes. Reply with ONLY a JSON object with keys: "
        "name (string), email (string), phone (string), skills (array of short lowercase skill names), "
        "years_experience (number, total professional years), education (highest degree, string), "
        "summary (2 sentence professional summary). Use empty values when unknown. Never invent facts."
    )
    try:
        out = _ask(system, f"Resume text:\n\n{text[:12000]}", 1024)
        data = json.loads(out[out.index("{"): out.rindex("}") + 1])
        data["skills"] = [str(s).lower() for s in data.get("skills", [])]
        data["years_experience"] = float(data.get("years_experience") or 0)
        return data
    except Exception:
        return None


def explain_match(job: dict, cand: dict, scores: dict) -> str | None:
    if not enabled():
        return None
    system = (
        "You are a recruiting assistant. In 2-3 sentences, explain how well the candidate fits the job: "
        "strengths, gaps, and a recommendation (advance / maybe / pass). Be factual; use only the provided data. "
        "Do not factor in name, gender, age, or other protected characteristics."
    )
    user = (
        f"JOB: {job['title']}\n{job['description'][:2000]}\nRequired skills: {job['required_skills']}\n"
        f"Min experience: {job['min_experience']}\n\nCANDIDATE: {cand['years_experience']} yrs, "
        f"skills {cand['skills']}, education {cand['education']}\n{(cand['raw_text'] or '')[:4000]}\n\n"
        f"Scores: {json.dumps(scores)}"
    )
    try:
        return _ask(system, user, 400)
    except Exception:
        return None


def chat(question: str, context: str) -> str:
    if not enabled():
        return (
            "The AI assistant is off. Set ANTHROPIC_API_KEY in your .env file and restart the server "
            "to ask free-form questions about candidates and jobs."
        )
    system = (
        "You are a recruiting assistant. Answer using only the context provided; say so if the answer "
        "isn't there. Evaluate on job-relevant criteria only, never on protected characteristics."
    )
    try:
        return _ask(system, f"Context:\n{context[:20000]}\n\nQuestion: {question}", 800)
    except Exception as e:
        return f"AI request failed: {e}"
