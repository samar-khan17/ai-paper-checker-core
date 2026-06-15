# core/question_parser.py
import re
from typing import List, Dict

class QuestionParser:
    PATTERNS = [
        r'Q\.?\s*(\d+)[\.:\)]\s*(.*?)(?=Q\.?\s*\d+[\.:\)]|\Z)',
        r'Question\s+(\d+)[\.:\)]\s*(.*?)(?=Question\s+\d+[\.:\)]|\Z)',
        r'^(\d+)[\.:\)]\s*(.*?)(?=^\d+[\.:\)]|\Z)',
    ]

    def parse_questions(self, text: str) -> List[Dict]:
        for pattern in self.PATTERNS:
            matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
            if matches:
                questions = []
                for num, content in matches:
                    questions.append({
                        "number": int(num),
                        "text": content.strip(),
                        "marks": self._extract_marks(content),
                        "sub_questions": self._extract_sub(content)
                    })
                return sorted(questions, key=lambda x: x['number'])
        return self._fallback_parse(text)

    def parse_answer_key(self, text: str) -> Dict:
        questions = self.parse_questions(text)
        return {q['number']: {"model_answer": q['text'], "marking_notes": "Standard marking."} for q in questions}

    def _extract_marks(self, text: str) -> int:
        m = re.search(r'\[(\d+)\s*marks?\]', text, re.IGNORECASE)
        if m: return int(m.group(1))
        m = re.search(r'\((\d+)\s*marks?\)', text, re.IGNORECASE)
        if m: return int(m.group(1))
        return 10

    def _extract_sub(self, text: str) -> List[Dict]:
        subs = []
        for m in re.finditer(r'\(([a-z])\)\s*(.*?)(?=\([a-z]\)|\Z)', text, re.DOTALL):
            subs.append({"label": m.group(1), "text": m.group(2).strip()})
        return subs

    def _fallback_parse(self, text: str) -> List[Dict]:
        paras = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 20]
        return [{"number": i+1, "text": p, "marks": 10, "sub_questions": []} for i, p in enumerate(paras)]
