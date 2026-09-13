"""Readiness assessor service (ADR-001, ADR-009).

Computes per-dimension and overall readiness from scores and bench results.
"""
from ..domain.cert_models import BenchResult, ReadinessAssessment, ScoreInput
from ..events.cert_events import OutboxPublisher, readiness_assessed


class ReadinessAssessor:
    def __init__(self, repository, publisher: OutboxPublisher | None = None,
                 collector=None):
        self._repo = repository
        self._publisher = publisher or OutboxPublisher()
        self._collector = collector

    def assess(self, target: str, scores: list, threshold: float = 0.7) -> ReadinessAssessment:
        score_objs = [ScoreInput(**s) if isinstance(s, dict) else s for s in scores]
        assessment = ReadinessAssessment(
            target=target, dimension_scores=score_objs, threshold=threshold
        )
        self._repo.save_assessment(assessment)
        self._publisher.publish(readiness_assessed(assessment))
        if self._collector:
            self._collector.collect_event(
                "readiness.assessed",
                {"target": target, "assessment_id": assessment.id,
                 "level": assessment.level.value, "overall_score": assessment.overall_score},
                correlation_id=assessment.id,
            )
        return assessment

    def assess_from_bench_results(self, target: str, results: list,
                                  threshold: float = 0.7) -> ReadinessAssessment:
        by_dimension: dict[str, list[float]] = {}
        for r in results:
            result = r if isinstance(r, BenchResult) else BenchResult(**r)
            by_dimension.setdefault(result.dimension, []).append(result.score)
        scores = [
            ScoreInput(dimension=dim, value=sum(vals) / len(vals))
            for dim, vals in by_dimension.items()
        ]
        return self.assess(target, scores, threshold)

    def get_assessment(self, assessment_id: str) -> ReadinessAssessment | None:
        return self._repo.get_assessment(assessment_id)

    def list_assessments(self, target: str | None = None) -> list:
        return self._repo.list_assessments(target=target)
