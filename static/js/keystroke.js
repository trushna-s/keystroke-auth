// ── Keystroke Capture Engine ──────────────────────────────────────

const keystrokes   = [];
let keydownTimes   = {};
let backspaceCount = 0;
const windowSize   = 25;

// REDUCED from 5 → 2. With only 1-2 bad windows needed,
// a different person's typing gets flagged almost immediately
// instead of needing 75+ keystrokes of sustained deviation.
const scoreHistory = [];
const historyLimit = 2;

let lastTrustScore = 100;

document.addEventListener('keydown', function(e) {
    const key  = e.key;
    const time = performance.now();
    keydownTimes[key] = time;
    if (key === 'Backspace') backspaceCount++;
});

document.addEventListener('keyup', function(e) {
    const key      = e.key;
    const upTime   = performance.now();
    const downTime = keydownTimes[key];
    if (!downTime) return;

    const dwell  = upTime - downTime;
    const flight = keystrokes.length > 0
        ? downTime - keystrokes[keystrokes.length - 1].downTime
        : null;

    keystrokes.push({
        key, downTime, upTime, dwell, flight
    });

    if (keystrokes.length >= windowSize) {
        sendKeystrokeData([...keystrokes]);
        keystrokes.length = 0;
        backspaceCount    = 0;
    }
});

// ── Send Data ─────────────────────────────────────────────────────
function sendKeystrokeData(data) {
    fetch('/analyze_keystrokes', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
            keystrokes:      data,
            backspace_count: backspaceCount,
            timestamp:       Date.now()
        })
    })
    .then(r => r.json())
    .then(result => {
        console.log(
            'Trust:', result.trust_score,
            '| Status:', result.status
        );

        lastTrustScore = result.trust_score;

        if (result.explanation &&
            typeof updateExplanation === 'function') {
            updateExplanation(
                result.explanation,
                result.trust_score
            );
        }

        processTrustScore(result);

        // Only update profile if trust is high —
        // prevents a different typist from poisoning
        // the legitimate user's baseline.
        if (result.trust_score >= 75) {
            updateProfile(data, backspaceCount,
                          result.trust_score);
        } else {
            console.log(
                '⚠️ Profile update skipped — trust: ' +
                result.trust_score + '%'
            );
        }
    })
    .catch(err => console.error('Error:', err));
}

// ── Update Profile (only when trust is high) ──────────────────────
function updateProfile(ks, bc, trustScore) {
    fetch('/update_profile', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
            keystrokes:      ks,
            backspace_count: bc,
            trust_score:     trustScore
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            console.log('✅ Profile updated');
        } else {
            console.log('⚠️ Profile update skipped:', data.reason);
        }
    });
}

// ── Rolling Window ────────────────────────────────────────────────
function processTrustScore(result) {
    const score  = Math.min(100, Math.max(0,
                   parseFloat(result.trust_score)));
    const status = result.status;

    scoreHistory.push({ score, status });
    if (scoreHistory.length > historyLimit) {
        scoreHistory.shift();
    }

    const avgScore   = scoreHistory.reduce(
        (sum, s) => sum + s.score, 0
    ) / scoreHistory.length;
    const roundedAvg = Math.round(avgScore);

    const lowCount = scoreHistory.filter(
        s => s.status !== 'allow'
    ).length;

    console.log(
        `Avg: ${roundedAvg}% | Low: ${lowCount}/${historyLimit}`
    );

    // CHANGED: require ALL recent windows to be low
    // (was: 60% of a 5-window history — too slow).
    // With historyLimit=2, this means 2 consecutive
    // suspicious/risky windows (50 keystrokes) triggers
    // action — fast enough to catch a different typist
    // within a few seconds, but still avoids 1-window flukes.
    if (scoreHistory.length >= historyLimit &&
        lowCount >= historyLimit) {

        const hasTerminate = scoreHistory.some(
            s => s.status === 'terminate');
        const hasOTP       = scoreHistory.some(
            s => s.status === 'otp');
        const hasSuspicious = scoreHistory.some(
            s => s.status === 'suspicious');

        const finalStatus =
            hasTerminate  ? 'terminate'  :
            hasOTP        ? 'otp'        :
            hasSuspicious ? 'suspicious' : 'allow';

        if (finalStatus === 'otp' &&
            !window.otpModalShowing) {
            fetch('/send_otp', { method: 'POST' })
            .then(r => r.json())
            .then(d => console.log('OTP:', d.message));
        }

        handleTrustUpdate(roundedAvg, finalStatus);

    } else {
        // Even if not triggering an action yet, reflect
        // the CURRENT single-window status visually if it's
        // already risky — this is what fixes "always shows
        // secure" even on the very first suspicious window.
        if (status !== 'allow') {
            handleTrustUpdate(score, status === 'terminate'
                ? 'suspicious' : status);
        } else {
            handleTrustUpdate(roundedAvg, 'allow');
        }
    }
}

// ── Handle Update ─────────────────────────────────────────────────
function handleTrustUpdate(score, status) {
    if (typeof updateCharts === 'function') {
        updateCharts(score);
    }

    if (status === 'suspicious') {
        if (typeof addActivity === 'function') {
            addActivity('⚠️ Unusual typing detected', 'warning');
        }
    } else if (status === 'otp') {
        if (typeof showOTPModal === 'function') {
            showOTPModal();
        }
    } else if (status === 'terminate') {
        if (typeof addActivity === 'function') {
            addActivity('🚫 Session terminated', 'danger');
        }

        fetch('/log_incident', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                reason: 'Trust score critically low',
                score:  score
            })
        })
        .then(r => r.json())
        .then(data => {
            if (data.auto_blocked) {
                alert(
                    '🚨 Your account has been temporarily ' +
                    'blocked due to multiple suspicious ' +
                    'login attempts. Contact your admin.'
                );
            }
        })
        .finally(() => {
            setTimeout(() => {
                window.location.href = '/logout';
            }, 2000);
        });
    }
}

function updateTrustDisplay(score, status) {
    handleTrustUpdate(score, status);
}