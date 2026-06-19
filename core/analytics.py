# ============================================================
#   core/analytics.py — Class-level insight helpers
#   Pure functions over db.results_for_paper(paper_id) output.
#   - question_breakdown: which questions the class struggled with
#   - find_similar_pairs: simple copy/plagiarism flagging
# ============================================================

import re


def question_breakdown(results: list) -> list:
    """For each question, average % the class scored and how many got it fully right.
    Returns list of dicts sorted by weakest first."""
    agg = {}  # qnum -> {"pct_sum":, "n":, "full":, "text":}
    for r in results:
        for qnum, q in (r.get("question_results") or {}).items():
            mx = q.get("max_marks", 0) or 0
            sc = q.get("score", 0) or 0
            pct = (sc / mx * 100) if mx else 0
            a = agg.setdefault(str(qnum), {"pct_sum": 0.0, "n": 0, "full": 0, "text": ""})
            a["pct_sum"] += pct
            a["n"] += 1
            if mx and sc >= mx - 1e-6:
                a["full"] += 1
            if not a["text"]:
                a["text"] = (q.get("question_text", "") or "")[:80]

    out = []
    for qnum, a in agg.items():
        n = a["n"] or 1
        out.append({
            "qnum": qnum,
            "avg_pct": round(a["pct_sum"] / n, 1),
            "got_full": a["full"],
            "total": a["n"],
            "full_rate": round(a["full"] / n * 100, 1),
            "text": a["text"],
        })
    # Sort numerically by question number when possible
    def _key(d):
        m = re.sub(r"[^0-9]", "", d["qnum"])
        return int(m) if m else 9999
    return sorted(out, key=_key)


def _student_text(r: dict) -> str:
    """Concatenate all of a student's answers into one normalized string."""
    parts = []
    for q in (r.get("question_results") or {}).values():
        parts.append(str(q.get("student_answer", "") or ""))
    text = " ".join(parts).lower()
    return re.sub(r"[^a-z0-9؀-ۿ ]", " ", text)


def _similarity(a: str, b: str) -> float:
    """Word-overlap (Jaccard) similarity, 0..1. Cheap and language-agnostic."""
    wa = set(w for w in a.split() if len(w) > 2)
    wb = set(w for w in b.split() if len(w) > 2)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def find_similar_pairs(results: list, threshold: float = 0.65) -> list:
    """Flag pairs of students whose answers are suspiciously similar.
    Returns list of dicts sorted by similarity (highest first)."""
    texts = []
    for r in results:
        t = _student_text(r)
        if len(t.split()) >= 8:   # ignore near-empty sheets
            texts.append((r.get("student_name", "—") or "—",
                          r.get("student_roll", "") or "", t))
    pairs = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            sim = _similarity(texts[i][2], texts[j][2])
            if sim >= threshold:
                pairs.append({
                    "a_name": texts[i][0], "a_roll": texts[i][1],
                    "b_name": texts[j][0], "b_roll": texts[j][1],
                    "similarity": round(sim * 100, 1),
                })
    return sorted(pairs, key=lambda p: p["similarity"], reverse=True)
