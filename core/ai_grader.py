# ============================================================
#   core/nvidia_grader.py — NVIDIA NIM AI Grading Engine
#   Uses NVIDIA's API (OpenAI-compatible) for paper grading.
#   Falls back to keyword matching if API unavailable.
# ============================================================

import json
import base64
import logging
import re
from pathlib import Path
from openai import OpenAI
from config import (NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL,
                    NVIDIA_VISION_MODEL, AI_TEMPERATURE)

logger = logging.getLogger("nvidia_grader")

# Strictness modes → minimum semantic match (%) to count an answer as fully correct.
MODE_THRESHOLDS = {
    "lenient": 60,
    "normal":  75,
    "hard":    85,
    "insane":  95,
}

def _mode_rule(mode: str) -> str:
    mode = (mode or "normal").lower()
    thr = MODE_THRESHOLDS.get(mode, 75)
    return (f"CHECKING MODE: {mode.upper()} (acceptance threshold {thr}%).\n"
            f"- Judge by MEANING, not exact words. A written answer is FULLY correct when it "
            f"conveys at least {thr}% of the model answer's key concepts; award partial credit "
            f"proportionally below that. For MCQ/one-word answers the option must match exactly.\n")


GRADING_SYSTEM_PROMPT = """You are a strict, fair, and highly experienced university professor \
and examiner. You grade student answers in Pakistani/South Asian university contexts. \
You understand academic writing standards, partial credit, and constructive feedback. \
You are grading for the subject: {subject}.

GRADING PHILOSOPHY:
- First decide the answer type:
  * MCQ / one-word / option answer (the answer key is something like "B" or "True"):
    award FULL marks ONLY if the student's choice matches the correct option,
    otherwise award 0. No partial credit for MCQs.
  * Written / descriptive answer: award partial credit proportionally for
    correct concepts even if the wording differs.
- Deduct marks for missing key points, not for writing style
- Be consistent — same quality answer = same marks
- Never give more than maximum marks; never give negative marks
- If the student's answer is blank, award 0
- Flag verbatim copying from model answers as suspicious

You MUST respond ONLY with a valid JSON object. No explanation outside JSON. No markdown fences."""


GRADING_USER_PROMPT = """SUBJECT: {subject}
QUESTION NUMBER: {qnum}
QUESTION TEXT: {question}

MODEL ANSWER (correct answer by teacher):
{model_answer}

MARKING SCHEME NOTES:
{marking_notes}

STUDENT'S ANSWER:
{student_answer}

MAXIMUM MARKS FOR THIS QUESTION: {max_marks}

Grade this answer and return ONLY this JSON:
{{
  "score": <number, 0 to {max_marks}, decimals allowed>,
  "percentage": <0 to 100>,
  "feedback": "<2-3 sentences of specific, constructive feedback for the student>",
  "correct_concepts": ["<concept correctly mentioned>", "..."],
  "missing_concepts": ["<important concept missing>", "..."],
  "partial_credit_justification": "<why you gave this score>",
  "confidence": <0.0 to 1.0, how certain you are about this grade>,
  "difficulty_assessment": <1 to 5>,
  "red_flags": ["<any suspicious patterns, or empty list>"]
}}"""


class NvidiaGrader:
    def __init__(self):
        self.available = bool(NVIDIA_API_KEY)
        self.client = None
        
        if self.available:
            try:
                self.client = OpenAI(
                    base_url=NVIDIA_BASE_URL,
                    api_key=NVIDIA_API_KEY,
                    timeout=90.0,      # generous, but never hang forever
                    max_retries=0      # one attempt; fall back rather than double the wait
                )
                logger.info(f"NVIDIA NIM connected. Model: {NVIDIA_MODEL}")
            except Exception as e:
                logger.error(f"NVIDIA client init failed: {e}")
                self.available = False
        else:
            logger.warning("NVIDIA_API_KEY not found. Using keyword fallback.")

    # ── PUBLIC METHODS ────────────────────────────────────────

    def grade_single_answer(self, qnum: int, question: str, model_answer: str,
                             student_answer: str, max_marks: int, subject: str,
                             marking_notes: str = "Standard marking applies.",
                             mode: str = "normal") -> dict:
        """Grade one answer. Returns structured result dict."""

        if not student_answer or not student_answer.strip():
            return self._empty_answer_result(qnum, max_marks)

        if self.available and self.client:
            result = self._nvidia_grade(qnum, question, model_answer, student_answer,
                                        max_marks, subject, marking_notes, mode)
            if result:
                return result

        # Fallback
        return self._keyword_grade(qnum, model_answer, student_answer, max_marks)

    def grade_full_paper(self, paper_data: dict, student_answers: dict, subject: str,
                         mode: str = "normal") -> dict:
        """
        Grade entire paper question by question.
        
        paper_data = {
            "questions": [{"number": 1, "text": "...", "marks": 10}, ...],
            "answer_key": {1: {"model_answer": "...", "marking_notes": "..."}, ...}
        }
        student_answers = {1: "student answer text", 2: "...", ...}
        """
        question_results = {}
        total_score = 0
        total_max = 0
        questions = paper_data.get("questions", [])
        answer_key = paper_data.get("answer_key", {})

        # One batched API call for the whole paper (fast). Falls back per-question.
        batch = {}
        if self.available and self.client and questions:
            batch = self._nvidia_grade_batch(questions, answer_key, student_answers, subject, mode) or {}

        for q in questions:
            qnum = q["number"]
            max_marks = q.get("marks", 10)
            question_text = q.get("text", "")
            answer_key_entry = answer_key.get(qnum, {})
            model_answer = answer_key_entry.get("model_answer", "")
            marking_notes = answer_key_entry.get("marking_notes", "Standard marking applies.")
            student_ans = student_answers.get(qnum, "")

            result = batch.get(qnum)
            if not result:
                # missing from batch (or batch failed) → grade this one on its own
                result = self.grade_single_answer(
                    qnum, question_text, model_answer,
                    student_ans, max_marks, subject, marking_notes, mode)

            result["max_marks"] = max_marks
            result["score"] = max(0, min(result.get("score", 0), max_marks))
            sc = result.get("score", 0)
            result["question_text"] = question_text
            result["student_answer"] = student_ans
            result["model_answer"] = model_answer
            result["status"] = ("Correct" if max_marks and sc >= max_marks - 1e-6
                                else ("Incorrect" if sc <= 1e-6 else "Partially Correct"))
            result.setdefault("remark", result.get("feedback", ""))

            question_results[qnum] = result
            total_score += sc
            total_max += max_marks

        logger.info(f"Paper graded: {len(question_results)} question(s) [{mode}] "
                    f"score {round(total_score,1)}/{total_max}")

        percentage = round((total_score / total_max * 100), 1) if total_max > 0 else 0
        overall_confidence = self._average_confidence(question_results)

        return {
            "question_results": question_results,
            "total_score": round(total_score, 1),
            "total_max": total_max,
            "percentage": percentage,
            "grade": self._calculate_grade(percentage),
            "overall_confidence": overall_confidence,
            "needs_manual_review": overall_confidence < 0.75,
            "summary_feedback": self._local_summary(question_results, subject, percentage),
            "all_red_flags": self._collect_red_flags(question_results)
        }

    def _local_summary(self, results: dict, subject: str, percentage: float) -> str:
        """Build a summary without an extra API call (keeps checking fast)."""
        try:
            strong = [f"Q{q}" for q, r in results.items()
                      if r.get("max_marks") and r.get("score", 0) >= r["max_marks"] - 1e-6]
            weak = [f"Q{q}" for q, r in results.items() if r.get("score", 0) <= 1e-6]
            parts = [f"Overall score {percentage}% in {subject}."]
            if strong:
                parts.append(f"Fully correct: {', '.join(strong)}.")
            if weak:
                parts.append(f"Needs work: {', '.join(weak)}.")
            return " ".join(parts)
        except Exception:
            return f"Overall score {percentage}% in {subject}."

    # ── VISION: READ A STUDENT ANSWER SHEET FROM IMAGE(S) ─────

    def read_answer_sheet(self, image_paths: list, questions: list) -> dict:
        """
        Use the NVIDIA vision model to read a student's answer sheet image(s)
        and return {question_number: "student answer text"}.
        Returns {} if vision is unavailable or fails.
        """
        if not (self.available and self.client):
            return {}
        try:
            qlist = ", ".join(str(q.get("number")) for q in questions) or "all"
            content = [{
                "type": "text",
                "text": (
                    "This is a student's exam answer sheet (it may be handwritten). "
                    f"Read it carefully. The paper has these question numbers: {qlist}. "
                    "For each question the student attempted, transcribe their answer. "
                    "Respond with ONLY a JSON object mapping the question number (as a string) "
                    'to the student\'s answer, e.g. {"1":"B","2":"because ..."}. '
                    "If a question was not attempted, omit it. No markdown, no extra text."
                )
            }]
            for p in image_paths:
                b64 = base64.b64encode(Path(p).read_bytes()).decode()
                ext = Path(p).suffix.lower().lstrip(".") or "png"
                mime = "jpeg" if ext in ("jpg", "jpeg") else ext
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:image/{mime};base64,{b64}"}})

            resp = self.client.chat.completions.create(
                model=NVIDIA_VISION_MODEL,
                messages=[{"role": "user", "content": content}],
                temperature=0.0, max_tokens=1500, timeout=90.0
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r'^```json\s*|\s*```$', '', raw, flags=re.MULTILINE).strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                raw = m.group(0)
            data = json.loads(raw)
            answers = {}
            for k, v in data.items():
                try:
                    answers[int(re.sub(r'[^0-9]', '', str(k)))] = str(v).strip()
                except (ValueError, TypeError):
                    continue
            logger.info(f"Vision read {len(answers)} answers from {len(image_paths)} image(s).")
            return answers
        except Exception as e:
            logger.error(f"Vision read failed: {e}")
            return {}

    def _vision_json(self, image_paths: list, instruction: str, max_tokens=2000):
        if not (self.available and self.client):
            return None
        try:
            content = [{"type": "text", "text": instruction}]
            for p in image_paths:
                b64 = base64.b64encode(Path(p).read_bytes()).decode()
                ext = Path(p).suffix.lower().lstrip(".") or "png"
                mime = "jpeg" if ext in ("jpg", "jpeg") else ext
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:image/{mime};base64,{b64}"}})
            resp = self.client.chat.completions.create(
                model=NVIDIA_VISION_MODEL,
                messages=[{"role": "user", "content": content}],
                temperature=0.0, max_tokens=max_tokens, timeout=90.0)
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r'^```json\s*|\s*```$', '', raw, flags=re.MULTILINE).strip()
            m = re.search(r'(\{.*\}|\[.*\])', raw, re.DOTALL)
            return json.loads(m.group(0) if m else raw)
        except Exception as e:
            logger.error(f"Vision JSON failed: {e}")
            return None

    def read_questions_from_images(self, image_paths: list) -> list:
        """Extract questions (with marks) from a question-paper image/PDF page(s)."""
        data = self._vision_json(image_paths,
            "This is an exam QUESTION PAPER. Read every question in order. For each, give the "
            "question number, the question text, and its marks if written (e.g. '[10 marks]'). "
            'Respond with ONLY a JSON array like '
            '[{"number":1,"text":"...","marks":10}, ...]. If marks are not shown, use 10.')
        out = []
        if isinstance(data, list):
            for q in data:
                try:
                    out.append({"number": int(q.get("number")),
                                "text": str(q.get("text", "")).strip(),
                                "marks": int(q.get("marks", 10) or 10)})
                except (ValueError, TypeError):
                    continue
        return sorted(out, key=lambda x: x["number"])

    def read_answers_from_images(self, image_paths: list) -> dict:
        """Extract the official answer key from a solution image/PDF page(s)."""
        data = self._vision_json(image_paths,
            "This is the official ANSWER KEY / solution sheet. For each question give the correct "
            'answer. Respond with ONLY a JSON object like {"1":"B","2":"because ..."}.')
        ak = {}
        if isinstance(data, dict):
            for k, v in data.items():
                try:
                    ak[int(re.sub(r'[^0-9]', '', str(k)))] = {
                        "model_answer": str(v).strip(), "marking_notes": "Standard marking."}
                except (ValueError, TypeError):
                    continue
        return ak

    # ── BATCH GRADE: whole paper in ONE call (fast) ───────────

    def _nvidia_grade_batch(self, questions, answer_key, student_answers, subject, mode) -> dict:
        """Grade every question in a single API call. Returns {qnum: result} or {}."""
        try:
            blocks = []
            for q in questions:
                qn = q["number"]; mx = q.get("marks", 10)
                ak = answer_key.get(qn, {})
                blocks.append(
                    f"[Q{qn}] (max {mx} marks)\n"
                    f"QUESTION: {q.get('text','')}\n"
                    f"MODEL ANSWER: {ak.get('model_answer','')}\n"
                    f"MARKING NOTES: {ak.get('marking_notes','Standard marking.')}\n"
                    f"STUDENT ANSWER: {student_answers.get(qn,'') or '(blank)'}")
            system_msg = GRADING_SYSTEM_PROMPT.format(subject=subject) + "\n\n" + _mode_rule(mode)
            user_msg = (
                "Grade EVERY question below. Respond with ONLY this JSON (no markdown):\n"
                '{"results":[{"number":1,"score":<0..max>,"confidence":<0..1>,'
                '"feedback":"<1-2 sentence remark>","red_flags":[]}, ...]}\n'
                "Give one entry per question, scoring 0 for blank answers.\n\n"
                + "\n\n".join(blocks))
            resp = self.client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=[{"role": "system", "content": system_msg},
                          {"role": "user", "content": user_msg}],
                temperature=AI_TEMPERATURE,
                max_tokens=min(400 * max(1, len(questions)) + 300, 6000),
                top_p=0.9, timeout=120.0)
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r'^```json\s*|\s*```$', '', raw, flags=re.MULTILINE).strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(m.group(0) if m else raw)
            out = {}
            for item in data.get("results", []):
                try:
                    qn = int(item.get("number"))
                except (ValueError, TypeError):
                    continue
                out[qn] = {
                    "qnum": qn,
                    "score": float(item.get("score", 0) or 0),
                    "confidence": max(0.0, min(float(item.get("confidence", 0.85) or 0.85), 1.0)),
                    "feedback": str(item.get("feedback", "")).strip(),
                    "red_flags": item.get("red_flags", []) or [],
                    "graded_by": "nvidia_ai",
                }
            logger.info(f"Batch graded {len(out)} question(s) in one call.")
            return out
        except Exception as e:
            logger.error(f"Batch grade failed ({e}); will grade per question.")
            return {}

    # ── PRIVATE: NVIDIA CALL ──────────────────────────────────

    def _nvidia_grade(self, qnum, question, model_answer, student_answer,
                      max_marks, subject, marking_notes, mode="normal") -> dict | None:
        try:
            system_msg = GRADING_SYSTEM_PROMPT.format(subject=subject) + "\n\n" + _mode_rule(mode)
            user_msg = GRADING_USER_PROMPT.format(
                subject=subject, qnum=qnum, question=question,
                model_answer=model_answer, marking_notes=marking_notes,
                student_answer=student_answer, max_marks=max_marks
            )
            
            response = self.client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ],
                temperature=AI_TEMPERATURE,
                max_tokens=800,
                top_p=0.9,
                timeout=90.0
            )
            
            raw = response.choices[0].message.content.strip()
            # Strip markdown fences if model added them anyway
            raw = re.sub(r'^```json\s*|\s*```$', '', raw, flags=re.MULTILINE)
            
            result = json.loads(raw)
            result["qnum"] = qnum
            result["max_marks"] = max_marks
            result["graded_by"] = "nvidia_ai"
            
            # Enforce score bounds
            result["score"] = max(0, min(result.get("score", 0), max_marks))
            result["confidence"] = max(0.0, min(result.get("confidence", 0.7), 1.0))
            
            logger.info(f"NVIDIA graded Q{qnum}: {result['score']}/{max_marks} (conf: {result['confidence']})")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for Q{qnum}: {e}. Raw: {raw[:200]}")
            return None
        except Exception as e:
            logger.error(f"NVIDIA API call failed for Q{qnum}: {e}")
            return None

    # ── PRIVATE: FALLBACK ─────────────────────────────────────

    def _keyword_grade(self, qnum, model_answer, student_answer, max_marks) -> dict:
        """Keyword overlap fallback when NVIDIA unavailable."""
        stop_words = {'the','a','an','is','are','was','were','in','on','at',
                      'to','for','of','and','or','it','this','that','with',
                      'by','from','be','has','have','do','does','will','can'}

        def norm(t):
            return re.sub(r'[^a-z0-9]', '', (t or "").lower())

        # MCQ / short-answer case: do an exact normalized match (e.g. "B" == "b)" == "(B)")
        if model_answer and len(norm(model_answer)) <= 3:
            ms, ss = norm(model_answer), norm(student_answer)
            correct = bool(ms) and (ms == ss or ms in ss.split() or ss.endswith(ms) or ss.startswith(ms))
            return {
                "qnum": qnum, "score": max_marks if correct else 0, "max_marks": max_marks,
                "percentage": 100 if correct else 0,
                "feedback": ("Correct option selected." if correct
                             else f"Incorrect. Correct answer: {model_answer}."),
                "correct_concepts": [], "missing_concepts": [],
                "partial_credit_justification": "Exact option match (offline fallback).",
                "confidence": 0.7, "difficulty_assessment": 2, "red_flags": [],
                "graded_by": "keyword_fallback"
            }

        def keywords(text):
            words = re.sub(r'[^\w\s]', '', text.lower()).split()
            return set(w for w in words if w not in stop_words and len(w) > 2)

        model_kw = keywords(model_answer)
        student_kw = keywords(student_answer)

        if not model_kw:
            return self._empty_answer_result(qnum, max_marks)
        
        matched = model_kw & student_kw
        missing = model_kw - student_kw
        coverage = len(matched) / len(model_kw)
        score = round(coverage * max_marks, 1)
        
        return {
            "qnum": qnum,
            "score": score,
            "max_marks": max_marks,
            "percentage": round(coverage * 100, 1),
            "feedback": f"Matched {len(matched)} of {len(model_kw)} key concepts. "
                        f"Missing: {', '.join(list(missing)[:5])}.",
            "correct_concepts": list(matched),
            "missing_concepts": list(missing),
            "partial_credit_justification": "Keyword overlap scoring (offline fallback mode)",
            "confidence": round(min(coverage + 0.15, 0.75), 2),  # Capped at 0.75 — always flag for review
            "difficulty_assessment": 3,
            "red_flags": [],
            "graded_by": "keyword_fallback"
        }

    def _empty_answer_result(self, qnum, max_marks) -> dict:
        return {
            "qnum": qnum, "score": 0, "max_marks": max_marks,
            "percentage": 0,
            "feedback": "No answer provided by student.",
            "correct_concepts": [], "missing_concepts": [],
            "partial_credit_justification": "Blank answer — zero marks awarded.",
            "confidence": 1.0,
            "difficulty_assessment": 0,
            "red_flags": ["BLANK_ANSWER"],
            "graded_by": "auto_zero"
        }

    # ── UTILITIES ─────────────────────────────────────────────

    def _calculate_grade(self, percentage: float) -> str:
        thresholds = [(90,"A+"),(85,"A"),(80,"A-"),(75,"B+"),(70,"B"),
                      (65,"B-"),(60,"C+"),(55,"C"),(50,"D"),(0,"F")]
        for threshold, grade in thresholds:
            if percentage >= threshold:
                return grade
        return "F"

    def _average_confidence(self, results: dict) -> float:
        confs = [r.get("confidence", 0.5) for r in results.values()]
        return round(sum(confs) / len(confs), 2) if confs else 0.5

    def _collect_red_flags(self, results: dict) -> list:
        flags = []
        for qnum, r in results.items():
            for flag in r.get("red_flags", []):
                flags.append({"question": qnum, "flag": flag})
        return flags

    def _generate_summary_feedback(self, results: dict, subject: str, percentage: float) -> str:
        if not self.available:
            return f"Overall score: {percentage}%. Manual review recommended."
        
        try:
            strong = [q for q, r in results.items() if r.get("percentage", 0) >= 70]
            weak = [q for q, r in results.items() if r.get("percentage", 0) < 50]
            
            prompt = f"""Student scored {percentage}% in {subject}.
Strong questions: {strong}. Weak questions: {weak}.
Write 2 sentences of overall feedback for the student report. Be specific and encouraging."""
            
            resp = self.client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=100,
                timeout=30.0
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return f"Overall score: {percentage}%. See question breakdown for details."


# ── COMPATIBILITY WRAPPER for main.py ─────────────────────────
# main.py calls: grader.grade_paper(questions, answer_key, student_answers, subject, mode)
def _grade_paper_compat(self, questions, answer_key, student_answers, subject, mode="normal"):
    paper_data = {"questions": questions, "answer_key": answer_key}
    return self.grade_full_paper(paper_data, student_answers, subject, mode)

NvidiaGrader.grade_paper = _grade_paper_compat

# Aliases
AIGrader = NvidiaGrader
