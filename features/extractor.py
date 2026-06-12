import numpy as np


def extract_features_from_raw(keystrokes, backspace_count):
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
        'dd_mean':     np.mean(dd_times)
                       if dd_times else 0,
        'dd_std':      np.std(dd_times)
                       if dd_times else 0,
        'ud_mean':     np.mean(ud_times)
                       if ud_times else 0,
        'ud_std':      np.std(ud_times)
                       if ud_times else 0,
        'wpm':         wpm,
        'error_rate':  error_rate,
        'pause_count': pause_count,
    }


def compare_to_profile(features, profile):
    if not profile or not features:
        return 75.0, {}

    def score_feature(val, mean, std,
                      weight=1.0, tolerance=1.0):
        """
        Strict scoring:
        tolerance=1.0 means within 1 std dev = full score
        Beyond that drops fast
        """
        if std is None or std < 0.001:
            std = max(abs(mean) * 0.2, 0.005)

        z = abs(val - mean) / std

        if z <= tolerance:
            score = 100.0
        else:
            excess = z - tolerance
            # Drops 35 points per std dev beyond tolerance
            score  = max(0, 100 - (excess * 35))

        return score * weight

    # Strict weights — dwell and dd are most important
    dwell_score = score_feature(
        features['dwell_mean'],
        profile['dwell_mean'],
        profile['dwell_std'],
        weight=2.5,
        tolerance=1.0
    )

    dd_score = score_feature(
        features['dd_mean'],
        profile['dd_mean'],
        profile['dd_std'],
        weight=2.0,
        tolerance=1.0
    )

    ud_score = score_feature(
        features['ud_mean'],
        profile['ud_mean'],
        profile['ud_std'],
        weight=1.0,
        tolerance=1.5
    )

    wpm_score = score_feature(
        features['wpm'],
        profile['wpm_mean'],
        max(profile['wpm_std'], 3.0),
        weight=1.5,
        tolerance=1.5
    )

    error_score = score_feature(
        features['error_rate'],
        profile['error_rate_mean'],
        0.08,
        weight=0.5,
        tolerance=2.0
    )

    weights     = [2.5, 2.0, 1.0, 1.5, 0.5]
    scores      = [dwell_score, dd_score,
                   ud_score, wpm_score, error_score]
    total_w     = sum(weights)
    weighted    = sum(s * w for s, w
                      in zip(scores, weights))
    final_score = min(100, max(0, weighted / total_w))

    explanation = {
        'dwell_time': {
            'score':    round(
                min(100, dwell_score / 2.5), 1),
            'value':    round(
                features['dwell_mean'] * 1000, 1),
            'baseline': round(
                profile['dwell_mean'] * 1000, 1),
            'unit':     'ms',
            'label':    'Key Hold Time',
            'status':   _get_status(
                dwell_score / 2.5)
        },
        'flight_time': {
            'score':    round(
                min(100, dd_score / 2.0), 1),
            'value':    round(
                features['dd_mean'] * 1000, 1),
            'baseline': round(
                profile['dd_mean'] * 1000, 1),
            'unit':     'ms',
            'label':    'Time Between Keys',
            'status':   _get_status(dd_score / 2.0)
        },
        'typing_speed': {
            'score':    round(min(100, wpm_score), 1),
            'value':    round(features['wpm'], 1),
            'baseline': round(profile['wpm_mean'], 1),
            'unit':     'WPM',
            'label':    'Typing Speed',
            'status':   _get_status(wpm_score)
        },
        'error_rate': {
            'score':    round(
                min(100, error_score / 0.5), 1),
            'value':    round(
                features['error_rate'] * 100, 1),
            'baseline': round(
                profile['error_rate_mean'] * 100, 1),
            'unit':     '%',
            'label':    'Error Rate',
            'status':   _get_status(error_score / 0.5)
        },
        'pause_pattern': {
            'score':    round(min(100, ud_score), 1),
            'value':    features['pause_count'],
            'baseline': round(
                profile['pause_count_mean'], 1),
            'unit':     'pauses',
            'label':    'Pause Pattern',
            'status':   _get_status(ud_score)
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
    Strict thresholds:
    > 75  → Safe
    50-75 → Suspicious (warning shown)
    25-50 → OTP triggered
    < 25  → Session terminated
    """
    if trust_score >= 75:
        return 'allow', 'Low'
    elif trust_score >= 50:
        return 'suspicious', 'Medium'
    elif trust_score >= 25:
        return 'otp', 'High'
    else:
        return 'terminate', 'Critical'