// ── Keystroke Capture Engine ──────────────────────────────────────

const keystrokes   = [];
let keydownTimes   = {};
let backspaceCount = 0;
const windowSize   = 25;

// Only 2 consecutive bad windows → logout
const scoreHistory = [];
const historyLimit = 2;

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
        ? downTime -
          keystrokes[keystrokes.length - 1].downTime
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

        if (result.explanation &&
            typeof updateExplanation === 'function') {
            updateExplanation(
                result.explanation,
                result.trust_score
            );
        }

        processTrustScore(result);
    })
    .catch(err => console.error('Error:', err));
}

// ── Rolling Window — 2 strikes and out ───────────────────────────
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
        `Avg: ${roundedAvg}% | ` +
        `Low: ${lowCount}/${historyLimit}`
    );

    // Both windows must be low to trigger
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
        handleTrustUpdate(roundedAvg, 'allow');
    }
}

// ── Handle Update ─────────────────────────────────────────────────
function handleTrustUpdate(score, status) {
    if (typeof updateCharts === 'function') {
        updateCharts(score);
    }

    if (status === 'suspicious') {
        if (typeof addActivity === 'function') {
            addActivity(
                '⚠️ Unusual typing detected',
                'warning'
            );
        }
    } else if (status === 'otp') {
        if (typeof showOTPModal === 'function') {
            showOTPModal();
        }
    } else if (status === 'terminate') {
        if (typeof addActivity === 'function') {
            addActivity(
                '🚫 Session terminated — logging out',
                'danger'
            );
        }
        fetch('/log_incident', {
            method:  'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                reason: 'Trust score critically low',
                score:  score
            })
        }).finally(() => {
            setTimeout(() => {
                window.location.href = '/logout';
            }, 2000);
        });
    }
}

function updateTrustDisplay(score, status) {
    handleTrustUpdate(score, status);
}