from engine import ScoringEngine


class GradeProcessor:
    def assign_grade(self, total_score):
        if total_score >= 35:
            return "A"
        elif total_score >= 25:
            return "B"
        else:
            return "C"

    def evaluate(self, config_path, records):
        engine = ScoringEngine(config_path)
        results = []
        for rec in records:
            score = engine.score(rec)
            grade = self.assign_grade(score)
            results.append({"record": rec, "score": score, "grade": grade})
        return results
