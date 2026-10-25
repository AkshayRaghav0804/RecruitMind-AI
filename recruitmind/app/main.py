"""FastAPI app: resume upload, jobs, matching, recruiter assistant."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from . import ai_pipeline, db, matcher, pdf_processor  # noqa: E402

MAX_BYTES = 10 * 1024 * 1024
STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="RecruitMind-AI")
db.init()


class JobIn(BaseModel):
    title: str
    description: str
    required_skills: list[str] = []
    min_experience: float = 0


class ChatIn(BaseModel):
    question: str
    candidate_id: int | None = None
    job_id: int | None = None


def _candidate_public(c: dict, full: bool = False) -> dict:
    if not full:
        c = {k: v for k, v in c.items() if k != "raw_text"}
    return c


@app.get("/api/status")
def status():
    return {"database": True, "pdf_processor": True, "ai_pipeline": ai_pipeline.enabled()}


# ---------- candidates ----------
@app.post("/api/candidates/upload")
async def upload_resume(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large (max 10MB).")
    try:
        text = pdf_processor.extract_text(data)
    except Exception:
        raise HTTPException(400, "Could not read this PDF.")
    if len(text) < 30:
        raise HTTPException(422, "No extractable text found (scanned PDF?). Upload a text-based resume.")

    parsed = ai_pipeline.parse_resume(text) or {}
    base = pdf_processor.heuristic_parse(text)
    # AI result wins where present; heuristic fills gaps; skills are unioned
    merged = {**base, **{k: v for k, v in parsed.items() if v not in ("", None, [], 0)}}
    merged["skills"] = sorted(
        {pdf_processor.normalize_skill(s) for s in base["skills"] + parsed.get("skills", [])}
    )
    with db.conn() as c:
        cur = c.execute(
            "INSERT INTO candidates(filename,name,email,phone,skills,years_experience,education,summary,raw_text)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (file.filename, merged["name"], merged["email"], merged["phone"], json.dumps(merged["skills"]),
             merged["years_experience"], merged["education"], merged["summary"], text),
        )
        new = db.row(c.execute("SELECT * FROM candidates WHERE id=?", (cur.lastrowid,)).fetchone())
    return _candidate_public(new)


@app.get("/api/candidates")
def list_candidates():
    with db.conn() as c:
        rows = c.execute("SELECT * FROM candidates ORDER BY id DESC").fetchall()
    return [_candidate_public(db.row(r)) for r in rows]


@app.get("/api/candidates/{cid}")
def get_candidate(cid: int):
    with db.conn() as c:
        r = db.row(c.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone())
    if not r:
        raise HTTPException(404, "Candidate not found")
    return _candidate_public(r, full=True)


@app.delete("/api/candidates/{cid}")
def delete_candidate(cid: int):
    with db.conn() as c:
        c.execute("DELETE FROM candidates WHERE id=?", (cid,))
        c.execute("DELETE FROM matches WHERE candidate_id=?", (cid,))
    return {"ok": True}


# ---------- jobs ----------
@app.post("/api/jobs")
def create_job(job: JobIn):
    skills = [pdf_processor.normalize_skill(s) for s in job.required_skills if s.strip()]
    if not skills:
        skills = pdf_processor.find_skills(f"{job.title}\n{job.description}")
    with db.conn() as c:
        cur = c.execute(
            "INSERT INTO jobs(title,description,required_skills,min_experience) VALUES(?,?,?,?)",
            (job.title.strip(), job.description.strip(), json.dumps(skills), job.min_experience),
        )
        return db.row(c.execute("SELECT * FROM jobs WHERE id=?", (cur.lastrowid,)).fetchone())


@app.get("/api/jobs")
def list_jobs():
    with db.conn() as c:
        return [db.row(r) for r in c.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()]


@app.delete("/api/jobs/{jid}")
def delete_job(jid: int):
    with db.conn() as c:
        c.execute("DELETE FROM jobs WHERE id=?", (jid,))
        c.execute("DELETE FROM matches WHERE job_id=?", (jid,))
    return {"ok": True}


# ---------- matching ----------
def _matches_for(jid: int):
    with db.conn() as c:
        rows = c.execute(
            "SELECT m.*, c.name, c.email, c.years_experience, c.filename FROM matches m "
            "JOIN candidates c ON c.id=m.candidate_id WHERE m.job_id=? ORDER BY m.score DESC",
            (jid,),
        ).fetchall()
    return [db.row(r) for r in rows]


@app.post("/api/jobs/{jid}/match")
def run_match(jid: int, explain_top: int = 5):
    with db.conn() as c:
        job = db.row(c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone())
        cands = [db.row(r) for r in c.execute("SELECT * FROM candidates").fetchall()]
    if not job:
        raise HTTPException(404, "Job not found")
    if not cands:
        raise HTTPException(400, "Upload at least one resume first.")

    results = matcher.score_candidates(job, cands)
    by_id = {c["id"]: c for c in cands}
    for i, r in enumerate(results):
        if i < explain_top:  # only spend AI calls on the top candidates
            ai = ai_pipeline.explain_match(job, by_id[r["candidate_id"]], {k: r[k] for k in ("score", "skill_score", "text_score", "exp_score")})
            if ai:
                r["explanation"] = ai
    with db.conn() as c:
        c.execute("DELETE FROM matches WHERE job_id=?", (jid,))
        c.executemany(
            "INSERT INTO matches(job_id,candidate_id,score,skill_score,text_score,exp_score,matched_skills,missing_skills,explanation)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            [(jid, r["candidate_id"], r["score"], r["skill_score"], r["text_score"], r["exp_score"],
              json.dumps(r["matched_skills"]), json.dumps(r["missing_skills"]), r["explanation"]) for r in results],
        )
    return _matches_for(jid)


@app.get("/api/jobs/{jid}/matches")
def get_matches(jid: int):
    return _matches_for(jid)


# ---------- assistant ----------
@app.post("/api/chat")
def chat(body: ChatIn):
    parts = []
    with db.conn() as c:
        if body.job_id:
            j = db.row(c.execute("SELECT * FROM jobs WHERE id=?", (body.job_id,)).fetchone())
            if j:
                parts.append(f"JOB {j['title']}:\n{j['description']}\nRequired: {j['required_skills']}, min exp {j['min_experience']}")
        if body.candidate_id:
            r = db.row(c.execute("SELECT * FROM candidates WHERE id=?", (body.candidate_id,)).fetchone())
            if r:
                parts.append(f"CANDIDATE {r['name']}:\n{r['raw_text']}")
        elif body.job_id:
            for m in _matches_for(body.job_id)[:5]:
                parts.append(f"Top match {m['name']} score {m['score']}: {m['explanation']}")
    return {"answer": ai_pipeline.chat(body.question, "\n\n".join(parts) or "No context selected.")}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
