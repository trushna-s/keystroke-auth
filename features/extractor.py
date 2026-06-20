import numpy as np


def extract_features_from_raw(keystrokes, backspace_count):
    """
    Extract timing features from raw JS keystroke events.
    """
    if len(keystrokes) < 5:
        return None

    dwell_times = []
    dd_times    = []
    ud_times    = []

    for i, ks in enumerate(keystrokes):
        if ks.get('dwell') and ks['dwell'] > 0:
            dwell_times.append(ks['dwell'] / 1000)

        if i > 0:
            prev = keystrokes[i - 1]
            if ks.get('downTime') and prev.get('downTime'):
                dd = (ks['downTime'] -
                      prev['downTime']) / 1000
                if 0 < dd < 5:
                    dd_times.append(dd)
            if ks.get('downTime') and prev.get('upTime'):
                ud = (ks['downTime'] -
                      prev['upTime']) / 1000
                if abs(ud) < 5:
                    ud_times.append(ud)

    if not dwell_times:
        return None

    total_time = (keystrokes[-1]['upTime'] -
                  keystrokes[0]['downTime']) / 1000 / 60
    wpm = (len(keystrokes) / 5) / total_time \
          if total_time > 0 else 0

    pause_count = sum(1 for d in dd_times if d > 0.3)
    error_rate  = backspace_count / len(keystrokes) \
                  if keystrokes else 0

    return {
        'dwell_mean':  np.mean(dwell_times),
        'dwell_std':   np.std(dwell_times),
        'dd_mean':     np.mean(dd_times)   if dd_times else 0,
        'dd_std':      np.std(dd_times)    if dd_times else 0,
        'ud_mean':     np.mean(ud_times)   if ud_times else 0,
        'ud_std':      np.std(ud_times)    if ud_times else 0,
        'wpm':         wpm,
        'error_rate':  error_rate,
        'pause_count': pause_count,
    }


def compare_to_profile(features, profile):
    """
    Compare extracted features to stored user profile.
    Returns (trust_score, explanation).

    STRICT MODE: tolerance lowered to 1.0 std dev so that
    a different person's typing rhythm is reliably flagged
    within the first window or two, instead of needing
    several minutes of sustained deviation.
    """
    if not profile or not features:
        return 75.0, {}

    def score_feature(val, mean, std,
                      weight=1.0, tolerance=1.0):
        """
        tolerance: how many std devs are acceptable
        before the score starts dropping.
        Lower tolerance = stricter detection.
        Returns a 0-100 score WITHOUT weight applied
        (weight is applied separately in the weighted
        average so explanation values aren't double-scaled).
        """
        if std is None or std < 0.001:
            std = max(abs(mean) * 0.15, 0.005)

        z = abs(val - mean) / std

        if z <= tolerance:
            score = 100.0
        else:
            excess = z - tolerance
            # Drop 40 points per std dev beyond tolerance
            # (was 20 — too gentle to flag impostors quickly)
            score = max(0, 100 - (excess * 40))

        return score

    # Raw 0-100 scores per feature (NOT weight-multiplied)
    dwell_raw = score_feature(
        features['dwell_mean'],
        profile['dwell_mean'],
        profile['dwell_std'],
        tolerance=1.0
    )

    dd_raw = score_feature(
        features['dd_mean'],
        profile['dd_mean'],
        profile['dd_std'],
        tolerance=1.0
    )

    ud_raw = score_feature(
        features['ud_mean'],
        profile['ud_mean'],
        profile['ud_std'],
        tolerance=1.3
    )

    wpm_raw = score_feature(
        features['wpm'],
        profile['wpm_mean'],
        max(profile['wpm_std'], 3.0),
        tolerance=1.3
    )

    error_raw = score_feature(
        features['error_rate'],
        profile['error_rate_mean'],
        0.08,
        tolerance=1.8
    )

    # Weights used ONLY for the combined trust score
    weights = {
        'dwell': 2.5,
        'dd':    2.0,
        'ud':    1.0,
        'wpm':   1.5,
        'error': 0.5
    }
    raws = {
        'dwell': dwell_raw,
        'dd':    dd_raw,
        'ud':    ud_raw,
        'wpm':   wpm_raw,
        'error': error_raw
    }

    total_w  = sum(weights.values())
    weighted = sum(raws[k] * weights[k] for k in weights)
    final_score = min(100, max(0, weighted / total_w))

    # Explanation uses the RAW (unweighted) per-feature score
    # so each bar correctly shows 0-100% for that feature alone
    explanation = {
        'dwell_time': {
            'score':    round(dwell_raw, 1),
            'value':    round(features['dwell_mean'] * 1000, 1),
            'baseline': round(profile['dwell_mean'] * 1000, 1),
            'unit':     'ms',
            'label':    'Key Hold Time',
            'status':   _get_status(dwell_raw)
        },
        'flight_time': {
            'score':    round(dd_raw, 1),
            'value':    round(features['dd_mean'] * 1000, 1),
            'baseline': round(profile['dd_mean'] * 1000, 1),
            'unit':     'ms',
            'label':    'Time Between Keys',
            'status':   _get_status(dd_raw)
        },
        'typing_speed': {
            'score':    round(wpm_raw, 1),
            'value':    round(features['wpm'], 1),
            'baseline': round(profile['wpm_mean'], 1),
            'unit':     'WPM',
            'label':    'Typing Speed',
            'status':   _get_status(wpm_raw)
        },
        'error_rate': {
            'score':    round(error_raw, 1),
            'value':    round(features['error_rate'] * 100, 1),
            'baseline': round(
                profile['error_rate_mean'] * 100, 1),
            'unit':     '%',
            'label':    'Error Rate',
            'status':   _get_status(error_raw)
        },
        'pause_pattern': {
            'score':    round(ud_raw, 1),
            'value':    features['pause_count'],
            'baseline': round(
                profile['pause_count_mean'], 1),
            'unit':     'pauses',
            'label':    'Pause Pattern',
            'status':   _get_status(ud_raw)
        }
    }

    return round(final_score, 2), explanation


def _get_status(score):
    if score >= 70:
        return 'normal'
    elif score >= 45:
        return 'warning'
    else:
        return 'anomaly'


def get_risk_level(trust_score):
    """
    >=75   → allow      (Safe)
    50-75  → suspicious (Medium) — warning shown
    25-50  → otp        (High)  — OTP triggered
    <25    → terminate  (Critical) — session ended
    """
    if trust_score >= 75:
        return 'allow', 'Low'
    elif trust_score >= 50:
        return 'suspicious', 'Medium'
    elif trust_score >= 25:
        return 'otp', 'High'
    else:
        return 'terminate', 'Critical'