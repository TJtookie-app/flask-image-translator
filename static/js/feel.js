// 操作の手ごたえ（v1.7.3）: コピー・お気に入り・録音の開始で、端末が対応していれば、ごく短く振動する（iPhone の Safari は未対応なので何も起きない）。
// 動きを減らす設定のときは振動しない。
function haptic(ms) {
    try {
        if (!navigator.vibrate) return;
        if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        navigator.vibrate(ms || 12);
    } catch (e) {}
}

(function () {
    if (typeof copyResult === 'function') {
        const orig = copyResult;
        copyResult = function () { haptic(12); return orig.apply(this, arguments); };
    }
    if (typeof toggleFavCurrent === 'function') {
        const orig = toggleFavCurrent;
        toggleFavCurrent = function () { haptic(16); return orig.apply(this, arguments); };
    }
    if (typeof toggleVoiceRecording === 'function') {
        const orig = toggleVoiceRecording;
        toggleVoiceRecording = function () { haptic(20); return orig.apply(this, arguments); };
    }
})();
