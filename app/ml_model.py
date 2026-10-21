import logging
import joblib
import numpy as np
import pandas as pd
from app.config import MODEL_PATH
from app.features import build_row

log = logging.getLogger(__name__)
_model = None
_model_mtime = None


def load_model():
    """Load the model, reloading automatically when the file on disk is retrained."""
    global _model, _model_mtime
    if not MODEL_PATH.exists():
        _model, _model_mtime = None, None
        return None
    mtime = MODEL_PATH.stat().st_mtime
    if _model is None or mtime != _model_mtime:
        try:
            _model, _model_mtime = joblib.load(MODEL_PATH), mtime
        except Exception:
            log.exception("Could not load win-probability model from %s; using heuristic fallback", MODEL_PATH)
            _model, _model_mtime = None, None
    return _model


def win_probability(features: dict) -> tuple[float, str]:
    """Return (probability, source) where source is 'model' or 'heuristic'."""
    price = float(features.get("price", 1))
    list_price = features.get("list_price")
    competitor = features.get("competitor_price")
    model = load_model()
    if model is not None:
        try:
            row = build_row(price=price, list_price=list_price, competitor_price=competitor,
                            quantity=features.get("quantity", 1), segment=features.get("segment"),
                            product_id=features.get("product_id"), customer_id=features.get("customer_id"),
                            credit_hold=features.get("credit_hold", False))
            return float(np.clip(model.predict_proba(pd.DataFrame([row]))[0][1], .01, .99)), "model"
        except Exception:
            log.exception("Win-probability model failed on input; using heuristic fallback")
    # Transparent fallback heuristic; not a trained or calibrated model.
    ref = competitor if competitor else (list_price or price)
    rel = (price - ref) / max(float(ref), .01)
    p = .62 - 2.1 * rel
    if features.get("credit_hold", False):
        p -= .12
    return float(np.clip(p, .05, .95)), "heuristic"


def predict_win_probability(features: dict) -> float:
    return win_probability(features)[0]
