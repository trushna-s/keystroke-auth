# ── OPTIONAL: Add this near the top of app.py, after imports ──────
# Only include this if you want the .pkl models to genuinely
# contribute to the trust score as a secondary "human-likeness"
# check, separate from the personal z-score profile.

import joblib
import os

ML_MODELS_AVAILABLE = False
try:
    if os.path.exists('models/rf_model.pkl'):
        rf_model      = joblib.load('models/rf_model.pkl')
        svm_model     = joblib.load('models/svm_model.pkl')
        iso_model     = joblib.load('models/if_model.pkl')
        scaler_model  = joblib.load('models/scaler.pkl')
        feat_cols     = joblib.load('models/feature_cols.pkl')
        ML_MODELS_AVAILABLE = True
        print(f"✅ CMU-trained models loaded "
              f"({len(feat_cols)} features expected)")
except Exception as e:
    print(f"⚠️ CMU models not loaded: {e}")
    ML_MODELS_AVAILABLE = False


def get_human_likeness_score(features):
    """
    Secondary signal: uses the CMU-trained models to check
    whether typing rhythm looks human at all (not personal —
    just generically plausible). Returns 0-100 or None if
    models aren't available.
    """
    if not ML_MODELS_AVAILABLE:
        return None

    try:
        # Build a feature vector matching training format.
        # Since live features don't map 1:1 to CMU's 31
        # columns, we tile our 5 known stats across the
        # expected vector length as an approximation.
        base_vals = [
            features['dwell_mean'], features['dd_mean'],
            features['ud_mean'], features['wpm'],
            features['error_rate']
        ]
        vec = (base_vals * (len(feat_cols) // len(base_vals) + 1)
               )[:len(feat_cols)]

        sample = scaler_model.transform([vec])
        rf_prob = rf_model.predict_proba(sample)[0]
        classes = list(rf_model.classes_)
        genuine_prob = rf_prob[classes.index(1)] \
            if 1 in classes else 0.5

        svm_pred = svm_model.predict(sample)[0]
        iso_pred = iso_model.predict(sample)[0]

        svm_score = 1.0 if svm_pred == 1 else 0.0
        iso_score = 1.0 if iso_pred == 1 else 0.0

        blended = (genuine_prob * 0.5 +
                   svm_score * 0.3 +
                   iso_score * 0.2)
        return round(blended * 100, 2)
    except Exception as e:
        print(f"Human-likeness scoring error: {e}")
        return None


# ── Then in analyze_keystrokes route, AFTER computing
#    trust_score from compare_to_profile, optionally blend: ─────
#
#    human_score = get_human_likeness_score(features)
#    if human_score is not None:
#        # 85% personal profile, 15% generic human-likeness
#        trust_score = round(
#            trust_score * 0.85 + human_score * 0.15, 2)