"""
Main processing pipeline — orchestrates OCR → parsing → AI grading → report.
Called by the application layer; returns a fully populated result dict.
"""

from .ocr import extract_text
from .question_parser import QuestionParser
from .ai_grader import NvidiaGrader
from .report import ReportGenerator
from database.db_manager import DatabaseManager


class PaperProcessingPipeline:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.parser = QuestionParser()
        self.grader = NvidiaGrader()
        self.reporter = ReportGenerator()

    def process_submission(self, submission_id: int) -> dict:
        """
        Full pipeline: load submission → OCR → grade → save → generate report.
        Returns result dict with keys: score, grade, feedback, report_path.
        """
        submission = self.db.get_submission(submission_id)
        paper = self.db.get_paper(submission["paper_id"])

        # Step 1: Extract text from student answer file via OCR
        student_text, ocr_confidence = extract_text(submission["answer_file_path"])

        # Step 2: Parse the question paper structure
        questions = self.parser.parse(paper["question_paper_path"])
        answer_key = self.parser.parse(paper["answer_key_path"])

        # Step 3: AI grading
        grading_result = self.grader.grade_paper(
            questions=questions,
            answer_key=answer_key,
            student_answers=student_text,
            subject=paper["subject"],
        )

        # Step 4: Persist result
        result_id = self.db.save_result(
            submission_id=submission_id,
            total_score=grading_result["total_score"],
            grade=grading_result["grade"],
            confidence=grading_result["confidence"],
            feedback=grading_result["feedback"],
            red_flags=grading_result["red_flags"],
            ocr_confidence=ocr_confidence,
        )

        # Step 5: Generate PDF report
        report_path = self.reporter.generate_pdf({
            "submission": submission,
            "paper": paper,
            "result": grading_result,
            "ocr_confidence": ocr_confidence,
        })

        self.db.set_status(submission_id, "graded")

        return {
            "result_id": result_id,
            "score": grading_result["total_score"],
            "grade": grading_result["grade"],
            "confidence": grading_result["confidence"],
            "feedback": grading_result["feedback"],
            "red_flags": grading_result["red_flags"],
            "report_path": report_path,
        }
