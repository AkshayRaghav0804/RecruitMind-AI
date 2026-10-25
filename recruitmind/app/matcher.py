"""Candidate <-> job scoring engine (local, deterministic)."""
import math
import re
from collections import Counter

from .pdf_processor import find_skills, normalize_skill

W_SKILL, W_TEXT, W_EXP = 0.55, 0.30, 0.15
STOP = set(
    "a an the and or of to in for on with as at by is are was were be this that from it its we you our your "
    "will can have has had not but if their they them he she his her i my me us about into more than such "
    "work working experience years year team using use used strong ability skills".split()
)


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z][a-z+#.\-]{1,}", text.lower()) if t not in STOP]


def _tfidf_vectors(docs: list[str]) -> list[dict[str, float]]:
    toks = [_tokens(d) for d in docs]
    df = Counter(t for ts in toks for t in set(ts))
    n = len(docs)
    vecs = []
    for ts in toks:
        tf = Counter(ts)
        vecs.append({t: (c / max(len(ts), 1)) * (math.log((1 + n) / (1 + df[t])) + 1) for t, c in tf.items()})
    return vecs


def _cos(a: dict, b: dict) -> float:
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def score_candidates(job: dict, candidates: list[dict]) -> list[dict]:
    job_text = f"{job['title']}\n{job['description']}"
    required = [normalize_skill(s) for s in job.get("required_skills", [])] or find_skills(job_text)
    required = list(dict.fromkeys(required))
    min_exp = float(job.get("min_experience") or 0)

    vecs = _tfidf_vectors([job_text] + [c["raw_text"] or "" for c in candidates])
    jv, cvs = vecs[0], vecs[1:]

    results = []
    for c, cv in zip(candidates, cvs):
        cskills = {normalize_skill(s) for s in c["skills"]}
        matched = [s for s in required if s in cskills]
        missing = [s for s in required if s not in cskills]
        skill_score = len(matched) / len(required) if required else 0.5
        # TF-IDF cosine tends to be small in absolute terms; rescale so ~0.35 counts as a strong match
        text_score = min(_cos(jv, cv) / 0.35, 1.0)
        exp_score = 1.0 if min_exp <= 0 else min((c["years_experience"] or 0) / min_exp, 1.0)
        total = W_SKILL * skill_score + W_TEXT * text_score + W_EXP * exp_score
        results.append(
            {
                "candidate_id": c["id"],
                "score": round(total * 100, 1),
                "skill_score": round(skill_score * 100, 1),
                "text_score": round(text_score * 100, 1),
                "exp_score": round(exp_score * 100, 1),
                "matched_skills": matched,
                "missing_skills": missing,
                "explanation": template_explanation(c, job, matched, missing, min_exp),
            }
        )
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def template_explanation(c: dict, job: dict, matched: list, missing: list, min_exp: float) -> str:
    parts = [f"Matches {len(matched)} of {len(matched) + len(missing)} required skills"]
    if matched:
        parts[0] += f" ({', '.join(matched[:5])})"
    if missing:
        parts.append(f"missing: {', '.join(missing[:5])}")
    yrs = c.get("years_experience") or 0
    if min_exp:
        parts.append(f"{yrs:g} yrs experience vs {min_exp:g} required")
    return "; ".join(parts) + "."
