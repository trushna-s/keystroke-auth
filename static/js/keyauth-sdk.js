/**
 * KeyAuth External Website SDK
 * Continuous keystroke authentication
 * for external websites
 *
 * Usage:
 * <script
 *   src="http://your-server/static/js/keyauth-sdk.js"
 *   data-company-code="TCS-X7K9"
 *   data-user-token="your-token">
 * </script>
 */

(function() {
    'use strict';

    const script      = document.currentScript;
    const companyCode = script?.getAttribute(
        'data-company-code') || '';
    const userToken   = script?.getAttribute(
        'data-user-token') || '';
    const serverUrl   = script?.src
        .replace('/static/js/keyauth-sdk.js', '') ||
        'http://localhost:5000';

    if (!companyCode || !userToken) {
        console.warn(
            'KeyAuth SDK: Missing credentials'
        );
        return;
    }

    const keystrokes   = [];
    let keydownTimes   = {};
    let backspaceCount = 0;
    const windowSize   = 25;

    document.addEventListener('keydown', (e) => {
        keydownTimes[e.key] = performance.now();
        if (e.key === 'Backspace') backspaceCount++;
    });

    document.addEventListener('keyup', (e) => {
        const upTime   = performance.now();
        const downTime = keydownTimes[e.key];
        if (!downTime) return;

        const dwell  = upTime - downTime;
        const flight = keystrokes.length > 0
            ? downTime -
              keystrokes[keystrokes.length-1].downTime
            : null;

        keystrokes.push({
            key: e.key, downTime, upTime,
            dwell, flight
        });

        if (keystrokes.length >= windowSize) {
            sendToKeyAuth([...keystrokes]);
            keystrokes.length = 0;
            backspaceCount    = 0;
        }
    });

    function sendToKeyAuth(data) {
        fetch(`${serverUrl}/api/external/analyze`, {
            method:  'POST',
            headers: {
                'Content-Type':   'application/json',
                'X-Company-Code': companyCode,
                'X-User-Token':   userToken
            },
            body: JSON.stringify({
                keystrokes:      data,
                backspace_count: backspaceCount,
                page_url:        window.location.href,
                timestamp:       Date.now()
            })
        })
        .then(r => r.json())
        .then(result => {
            console.log(
                'KeyAuth Trust Score:',
                result.trust_score + '%'
            );

            window.dispatchEvent(
                new CustomEvent('keyauth-score', {
                    detail: result
                })
            );

            if (result.status === 'terminate') {
                window.dispatchEvent(
                    new CustomEvent('keyauth-blocked',
                    { detail: result })
                );
            }
        })
        .catch(err => {
            console.warn('KeyAuth SDK error:', err);
        });
    }

    console.log(
        '🛡️ KeyAuth monitoring active —',
        companyCode
    );

})();