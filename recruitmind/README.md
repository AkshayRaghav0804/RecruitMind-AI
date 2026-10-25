# RecruitMind-AI — Resume Screening & Candidate Matching

Upload resume PDFs, define a job, and get ranked, explainable candidate matches.
Same layout and green theme as your DocMind-AI screen.

## Run it

```bash
cd recruitmind
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # optional: add ANTHROPIC_API_KEY for AI features
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## How it works

| Layer | File | What it does |
|---|---|---|
| Database | `app/db.py` | SQLite tables: candidates, jobs, matches |
| PDF Processor | `app/pdf_processor.py` | pypdf text extraction + local parser (name, email, phone, skills, years, education) |
| Matching engine | `app/matcher.py` | Score = 55% skill overlap + 30% TF-IDF text similarity + 15% experience fit |
| AI Pipeline | `app/ai_pipeline.py` | Optional Claude: better resume parsing, match explanations, recruiter chat |
| API | `app/main.py` | FastAPI endpoints + serves the UI |
| UI | `static/index.html` | Single-page Tailwind app |

**Without an API key** everything works locally (heuristic parsing, template explanations);
only the free-form chat assistant needs the key. With a key, Claude parses resumes, explains
the top 5 matches per run, and answers questions about a candidate or job.

## API

- `POST /api/candidates/upload` (PDF, max 10MB) · `GET /api/candidates` · `GET/DELETE /api/candidates/{id}`
- `POST /api/jobs` · `GET /api/jobs` · `DELETE /api/jobs/{id}`
- `POST /api/jobs/{id}/match` · `GET /api/jobs/{id}/matches`
- `POST /api/chat` `{question, job_id?, candidate_id?}`
- `GET /api/status`

## Known limits / next steps

- Scanned (image-only) PDFs aren't supported; add OCR (e.g. `ocrmypdf`) if you need them.
- The local skill list in `pdf_processor.py` (`SKILLS`) is a starting taxonomy — extend it for your domain.
- No authentication yet; add it before exposing this beyond localhost, since resumes contain personal data.
- Hiring is a regulated area (bias, data-protection laws). Treat scores as decision support with a human
  reviewing every shortlist, and consider anonymizing names before screening.
