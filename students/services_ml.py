from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler

from .ml_feature_builder import (
    build_live_features_for_student,
    feature_dict_to_vector_with_weak,
)

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "ml_models" / "saved"

CLASSIFIER_PATH = MODEL_DIR / "next_pass_classifier.pkl"
REGRESSOR_PATH = MODEL_DIR / "next_score_regressor.pkl"
SCALER_PATH = MODEL_DIR / "submission_scaler.pkl"
METRICS_PATH = MODEL_DIR / "metrics.json"


def model_ready() -> bool:
    return (
        CLASSIFIER_PATH.exists()
        and REGRESSOR_PATH.exists()
        and SCALER_PATH.exists()
        and METRICS_PATH.exists()
    )


def load_metrics():
    if not METRICS_PATH.exists():
        return {}
    with open(METRICS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_scaler():
    return joblib.load(SCALER_PATH)


def _load_classifier():
    return joblib.load(CLASSIFIER_PATH)


def _load_regressor():
    return joblib.load(REGRESSOR_PATH)


def score_to_label(score: float) -> str:
    if score >= 80:
        return "Жоғары"
    elif score >= 60:
        return "Орташа"
    return "Төмен"


def risk_from_prob_and_score(pass_probability: float, predicted_score: float) -> str:
    if pass_probability < 0.35 or predicted_score < 55:
        return "Жоғары тәуекел"
    elif pass_probability < 0.65 or predicted_score < 75:
        return "Орташа тәуекел"
    return "Қалыпты"


def predict_next_quiz_success(student) -> dict:
    if not model_ready():
        raise FileNotFoundError("ML модель файлдары табылмады.")

    fdict = build_live_features_for_student(student)
    x = np.array([feature_dict_to_vector_with_weak(fdict)], dtype=float)

    scaler = _load_scaler()
    clf = _load_classifier()

    x_scaled = scaler.transform(x)
    prob = clf.predict_proba(x_scaled)[0]

    # class 1 = pass_next
    pass_probability = float(prob[1]) if len(prob) > 1 else float(prob[0])
    pred_class = int(clf.predict(x_scaled)[0])

    return {
        "pass_next": bool(pred_class == 1),
        "pass_probability": round(pass_probability, 4),
        "features": fdict,
    }


def predict_next_score(student) -> dict:
    if not model_ready():
        raise FileNotFoundError("ML модель файлдары табылмады.")

    fdict = build_live_features_for_student(student)
    x = np.array([feature_dict_to_vector_with_weak(fdict)], dtype=float)

    scaler = _load_scaler()
    reg = _load_regressor()

    x_scaled = scaler.transform(x)
    score = float(reg.predict(x_scaled)[0])

    score = max(0.0, min(100.0, score))

    return {
        "predicted_score": round(score, 2),
        "features": fdict,
    }


def predict_student_summary(student) -> dict:
    """
    A + C бірге:
    - pass_next (classification)
    - predicted_score (regression)
    """
    pass_info = predict_next_quiz_success(student)
    score_info = predict_next_score(student)

    predicted_score = score_info["predicted_score"]
    pass_probability = pass_info["pass_probability"]

    label = score_to_label(predicted_score)
    risk = risk_from_prob_and_score(pass_probability, predicted_score)

    return {
        "predicted_score": predicted_score,
        "pass_next": pass_info["pass_next"],
        "pass_probability": pass_probability,
        "label": label,
        "risk": risk,
        "features": score_info["features"],
    }


def recommend_difficulty_from_prediction(predicted_score: float) -> str:
    """
    predicted_score бойынша remedial difficulty анықтайды.
    """
    if predicted_score < 50:
        return "easy"
    elif predicted_score < 80:
        return "medium"
    return "hard"