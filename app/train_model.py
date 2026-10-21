"""Train the win-probability model.

Champion: logistic regression. It is monotonic in price by construction, well calibrated,
explainable, and reaches the achievable ceiling on ~1k quotes. LightGBM (with a monotonic
price constraint) is cross-validated as a challenger and reported, but not saved.
"""
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score, average_precision_score, brier_score_loss, log_loss
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from app.config import DATA_DIR, MODEL_PATH
from app.features import NUMERIC, CATEGORICAL, build_frame

PRICE_FEATURES = ["price_vs_list", "price_vs_competitor", "price_vs_list_no_competitor"]


def preprocessor():
    return ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])


def champion():
    return Pipeline([("preprocess", preprocessor()), ("model", LogisticRegression(C=1.0, max_iter=2000))])


def challenger(n_features: int):
    try:
        from lightgbm import LGBMClassifier
    except ImportError:
        return None
    # -1 = win probability may only fall as price rises (price features come first in NUMERIC).
    constraints = [-1 if f in PRICE_FEATURES else 0 for f in NUMERIC] + [0] * (n_features - len(NUMERIC))
    return Pipeline([("preprocess", preprocessor()), ("model", LGBMClassifier(
        n_estimators=300, learning_rate=0.03, num_leaves=4, min_child_samples=40, reg_lambda=5.0,
        monotone_constraints=constraints, verbosity=-1, random_state=42))])


def main():
    path = DATA_DIR / "quote_history.csv"
    if not path.exists():
        from app.seed_data import main as seed
        seed()
    quotes = pd.read_csv(path)
    products = pd.read_csv(DATA_DIR / "products.csv")
    if "list_price" not in products:
        raise ValueError("products.csv has no list_price column; re-run `python -m app.seed_data`.")
    if "credit_hold" not in quotes:
        quotes = quotes.merge(pd.read_csv(DATA_DIR / "customers.csv")[["customer_id", "credit_hold"]], on="customer_id", how="left")
    X = build_frame(quotes, products)
    y = quotes["won"].astype(int)
    if y.nunique() < 2:
        raise ValueError("Training requires both won and lost quote outcomes.")

    # 5-fold CV gives a far steadier estimate than one holdout on ~1k rows.
    cv = StratifiedKFold(5, shuffle=True, random_state=42)
    scoring = ["roc_auc", "neg_brier_score"]
    cv_champ = cross_validate(champion(), X, y, cv=cv, scoring=scoring)
    n_feat = champion().named_steps["preprocess"].fit(X).transform(X[:1]).shape[1]
    ch = challenger(n_feat)
    cv_chall = cross_validate(ch, X, y, cv=cv, scoring=scoring) if ch is not None else None

    # The synthetic generator randomizes quote dates, so a stratified holdout is used here.
    # For real customer data, replace this with a strictly time-based holdout.
    tr, te = train_test_split(np.arange(len(X)), test_size=0.25, random_state=42, stratify=y)
    holdout = champion().fit(X.iloc[tr], y.iloc[tr])
    prob = holdout.predict_proba(X.iloc[te])[:, 1]
    base_rate = float(y.iloc[tr].mean())

    # Final model on all rows.
    model = champion().fit(X, y)
    names = model.named_steps["preprocess"].get_feature_names_out()
    coefs = dict(zip(names, model.named_steps["model"].coef_[0]))
    price_coefs = {f: round(float(coefs[f"num__{f}"]), 4) for f in PRICE_FEATURES}
    scale = model.named_steps["preprocess"].named_transformers_["num"].scale_
    raw = {f: float(coefs[f"num__{f}"]) / scale[NUMERIC.index(f)] for f in PRICE_FEATURES}
    slopes = {"with_competitor": raw["price_vs_list"] + raw["price_vs_competitor"],
              "without_competitor": raw["price_vs_list"] + raw["price_vs_list_no_competitor"]}
    if any(v >= 0 for v in slopes.values()):
        raise ValueError(f"Price coefficients must be negative (higher price -> lower win odds); got {slopes}. "
                         "Model not saved - check the data.")

    yt = y.iloc[te]
    metrics = {
        "model": "LogisticRegression",
        "n_rows": int(len(X)), "positive_rate": round(float(y.mean()), 4),
        "competitor_observed_rate": round(float(X["has_competitor"].mean()), 4),
        "cv5_roc_auc": f"{cv_champ['test_roc_auc'].mean():.4f} ± {cv_champ['test_roc_auc'].std():.4f}",
        "cv5_brier": round(float(-cv_champ["test_neg_brier_score"].mean()), 4),
        "holdout_n": int(len(te)),
        "holdout_roc_auc": round(float(roc_auc_score(yt, prob)), 4),
        "holdout_average_precision": round(float(average_precision_score(yt, prob)), 4),
        "holdout_brier": round(float(brier_score_loss(yt, prob)), 4),
        "holdout_brier_base_rate_baseline": round(float(brier_score_loss(yt, np.full(len(yt), base_rate))), 4),
        "holdout_log_loss": round(float(log_loss(yt, prob)), 4),
        "holdout_accuracy_at_0_5": round(float(accuracy_score(yt, prob >= 0.5)), 4),
        "holdout_accuracy_always_win_baseline": round(float(yt.mean()), 4),
        "price_coefficients_standardized": price_coefs,
        "log_odds_per_100pct_price_premium": {k: round(v, 2) for k, v in slopes.items()},
        "challenger_lightgbm_monotonic_cv5_roc_auc": (f"{cv_chall['test_roc_auc'].mean():.4f} ± {cv_chall['test_roc_auc'].std():.4f}"
                                                      if cv_chall is not None else "lightgbm not installed"),
        "evaluation_note": "Synthetic-data diagnostic only; not evidence of real-world predictive performance.",
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    (DATA_DIR / "model_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"Saved LogisticRegression to {MODEL_PATH}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
