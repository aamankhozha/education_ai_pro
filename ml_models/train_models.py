from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import django
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

import os
import sys

# Django setup
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "education_ai.settings")
django.setup()

from students.ml_feature_builder import build_training_rows, feature_names_with_weak  # noqa: E402

SAVE_DIR = BASE_DIR / "ml_models" / "saved"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

CLASSIFIER_PATH = SAVE_DIR / "next_pass_classifier.pkl"
REGRESSOR_PATH = SAVE_DIR / "next_score_regressor.pkl"
SCALER_PATH = SAVE_DIR / "submission_scaler.pkl"
METRICS_PATH = SAVE_DIR / "metrics.json"


def main():
    rows = build_training_rows()

    if len(rows) < 20:
        raise ValueError(
            f"ML train үшін дерек аз. Қазір тек {len(rows)} training row бар. "
            f"Алдымен көбірек completed submissions жинаңыз."
        )

    X = np.array([r.x for r in rows], dtype=float)
    y_pass = np.array([r.y_pass for r in rows], dtype=int)
    y_score = np.array([r.y_score for r in rows], dtype=float)

    X_train, X_test, y_pass_train, y_pass_test, y_score_train, y_score_test = train_test_split(
        X, y_pass, y_score, test_size=0.2, random_state=42
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        random_state=42,
        class_weight="balanced",
    )

    reg = RandomForestRegressor(
        n_estimators=200,
        max_depth=8,
        random_state=42,
    )

    clf.fit(X_train_scaled, y_pass_train)
    reg.fit(X_train_scaled, y_score_train)

    y_pass_pred = clf.predict(X_test_scaled)
    y_score_pred = reg.predict(X_test_scaled)

    cls_acc = float(accuracy_score(y_pass_test, y_pass_pred))
    reg_mae = float(mean_absolute_error(y_score_test, y_score_pred))
    reg_r2 = float(r2_score(y_score_test, y_score_pred))

    joblib.dump(clf, CLASSIFIER_PATH)
    joblib.dump(reg, REGRESSOR_PATH)
    joblib.dump(scaler, SCALER_PATH)

    metrics = {
        "best_model": "RandomForest (next_pass + next_score)",
        "best_accuracy": round(cls_acc, 4),
        "trained_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "training_rows": int(len(rows)),
        "feature_names": feature_names_with_weak(),
        "all_results": [
            {
                "name": "RandomForestClassifier",
                "accuracy": round(cls_acc, 4),
            },
            {
                "name": "RandomForestRegressor",
                "mae": round(reg_mae, 4),
                "r2": round(reg_r2, 4),
            },
        ],
    }

    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print("✅ ML training completed")
    print(f"Rows: {len(rows)}")
    print(f"Classifier accuracy: {cls_acc:.4f}")
    print(f"Regressor MAE: {reg_mae:.4f}")
    print(f"Regressor R2: {reg_r2:.4f}")


if __name__ == "__main__":
    main()