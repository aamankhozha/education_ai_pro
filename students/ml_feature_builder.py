from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Dict, Any

from django.db.models import Avg

from .models import Submission, AIAnalysis


QUIZ_TYPE_MAP = {
    "manual": 0,
    "ai": 1,
    "remedial": 2,
}


@dataclass
class FeatureRow:
    x: List[float]
    y_pass: int
    y_score: float


def _safe_quiz_type_value(quiz_type: str) -> int:
    return QUIZ_TYPE_MAP.get(quiz_type or "manual", 0)


def _count_weak_topics_before(student, quiz_id=None) -> int:
    qs = AIAnalysis.objects.filter(student=student)
    if quiz_id is not None:
        qs = qs.filter(quiz_id__lte=quiz_id)

    count = 0
    for row in qs:
        if row.weak_topics_json:
            try:
                topics = json.loads(row.weak_topics_json)
                count += len(topics)
            except Exception:
                pass
    return count


def build_features_from_history(history_submissions) -> Dict[str, float]:
    """
    history_submissions: student-тің target submission-ге дейінгі history-сы
    """
    history = list(history_submissions)
    total_quizzes = len(history)

    if total_quizzes == 0:
        return {
            "avg_last_3": 0.0,
            "avg_all": 0.0,
            "fail_count": 0.0,
            "remedial_count": 0.0,
            "pass_rate": 0.0,
            "last_percent": 0.0,
            "last_attempt_no": 0.0,
            "last_quiz_type": 0.0,
            "trend_last_2": 0.0,
            "total_quizzes": 0.0,
        }

    percents = [float(s.percent or 0.0) for s in history]
    avg_all = sum(percents) / total_quizzes
    avg_last_3 = sum(percents[-3:]) / min(3, total_quizzes)

    fail_count = sum(1 for s in history if (s.percent or 0) < 80)
    remedial_count = sum(1 for s in history if getattr(s.quiz, "quiz_type", "") == "remedial")
    pass_count = sum(1 for s in history if (s.percent or 0) >= 80)
    pass_rate = pass_count / total_quizzes if total_quizzes else 0.0

    last_sub = history[-1]
    last_percent = float(last_sub.percent or 0.0)
    last_attempt_no = float(getattr(last_sub, "attempt_no", 1) or 1)
    last_quiz_type = float(_safe_quiz_type_value(getattr(last_sub.quiz, "quiz_type", "manual")))

    trend_last_2 = 0.0
    if total_quizzes >= 2:
        trend_last_2 = percents[-1] - percents[-2]

    return {
        "avg_last_3": round(avg_last_3, 4),
        "avg_all": round(avg_all, 4),
        "fail_count": float(fail_count),
        "remedial_count": float(remedial_count),
        "pass_rate": round(pass_rate, 4),
        "last_percent": round(last_percent, 4),
        "last_attempt_no": round(last_attempt_no, 4),
        "last_quiz_type": round(last_quiz_type, 4),
        "trend_last_2": round(trend_last_2, 4),
        "total_quizzes": float(total_quizzes),
    }


def feature_dict_to_vector(feature_dict: Dict[str, float]) -> List[float]:
    return [
        feature_dict["avg_last_3"],
        feature_dict["avg_all"],
        feature_dict["fail_count"],
        feature_dict["remedial_count"],
        feature_dict["pass_rate"],
        feature_dict["last_percent"],
        feature_dict["last_attempt_no"],
        feature_dict["last_quiz_type"],
        feature_dict["trend_last_2"],
        feature_dict["total_quizzes"],
    ]


def feature_names() -> List[str]:
    return [
        "avg_last_3",
        "avg_all",
        "fail_count",
        "remedial_count",
        "pass_rate",
        "last_percent",
        "last_attempt_no",
        "last_quiz_type",
        "trend_last_2",
        "total_quizzes",
    ]


def build_training_rows() -> List[FeatureRow]:
    """
    Әр студенттің submission history-сына қарап:
    current history -> next submission нәтижесін болжауға dataset құрады.

    y_pass  = келесі тест >= 80 болса 1
    y_score = келесі тест пайызы
    """
    rows: List[FeatureRow] = []

    student_ids = (
        Submission.objects.filter(submitted_at__isnull=False)
        .values_list("student_id", flat=True)
        .distinct()
    )

    for student_id in student_ids:
        subs = list(
            Submission.objects.select_related("quiz", "student")
            .filter(student_id=student_id, submitted_at__isnull=False)
            .order_by("submitted_at", "id")
        )

        # Кемінде 2 submission керек: history -> next target
        if len(subs) < 2:
            continue

        for idx in range(1, len(subs)):
            history = subs[:idx]
            target = subs[idx]

            fdict = build_features_from_history(history)

            # weak topic count-ты history scope-қа қосамыз
            weak_topic_count = _count_weak_topics_before(
                target.student,
                quiz_id=history[-1].quiz_id if history else None,
            )
            fdict["weak_topic_count"] = float(weak_topic_count)

            x = feature_dict_to_vector_with_weak(fdict)

            y_score = float(target.percent or 0.0)
            y_pass = 1 if y_score >= 80.0 else 0

            rows.append(FeatureRow(x=x, y_pass=y_pass, y_score=y_score))

    return rows


def feature_names_with_weak() -> List[str]:
    return feature_names() + ["weak_topic_count"]


def feature_dict_to_vector_with_weak(feature_dict: Dict[str, float]) -> List[float]:
    return feature_dict_to_vector(feature_dict) + [float(feature_dict.get("weak_topic_count", 0.0))]


def build_live_features_for_student(student) -> Dict[str, float]:
    """
    Қазіргі студенттің барлық completed submission-дары бойынша feature құрады.
    """
    subs = list(
        Submission.objects.select_related("quiz")
        .filter(student=student, submitted_at__isnull=False)
        .order_by("submitted_at", "id")
    )

    fdict = build_features_from_history(subs)
    fdict["weak_topic_count"] = float(_count_weak_topics_before(student))
    return fdict