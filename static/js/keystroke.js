// ── Keystroke Capture Engine ──────────────────────────────────────

const keystrokes   = [];
let keydownTimes   = {};
let backspaceCount = 0;
const windowSize   = 25;

// Need 2 consecutive non-allow windows before acting.
// This is the security grace period — kept as-is.
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

    // Always show the CURRENT real-time score immediately,
    // regardless of confirmation state. This fixes the
    // "Verifying..." text disagreeing with the actual score —
    // the displayed number now always matches what the backend
    // just computed for THIS window.
    updateCharts(score);

    scoreHistory.push({ score, status });
    if (scoreHistory.length > historyLimit) {
        scoreHistory.shift();
    }

    const lowCount = scoreHistory.filter(
        s => s.status !== 'allow'
    ).length;

    console.log(
        `Current: ${score}% | Low: ${lowCount}/${historyLimit}`
    );

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

        // OPTION B: report the score from the FIRST risky
        // window in this confirmed sequence, not the latest
        // (possibly lower) one. This reflects "when risk
        // actually started" instead of "where it ended up
        // after the 2-window grace period."
        const firstRiskyWindow = scoreHistory.find(
            s => s.status !== 'allow'
        );
        const reportedScore = firstRiskyWindow
            ? firstRiskyWindow.score
            : score;

        if (finalStatus === 'otp' &&
            !window.otpModalShowing) {
            fetch('/send_otp', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({
                    trust_score: reportedScore
                })
            })
            .then(r => r.json())
            .then(d => console.log('OTP:', d.message));
        }

        handleTrustUpdate(reportedScore, finalStatus);

    }
    // No "else" branch needed anymore — updateCharts(score)
    // above already reflects the live number on every window,
    // confirmed or not.
}

// ── Handle Update ─────────────────────────────────────────────────
function handleTrustUpdate(score, status) {
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