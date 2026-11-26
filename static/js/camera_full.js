// 全画面のカメラ。カメラタブの「カメラで撮る」で開く。撮影するとカメラタブに戻ってプレビューが出て、「翻訳する」を押すと翻訳（camera-form を送る）。左上の矢印は、撮らずに戻る
let videoStream = null;
let camTorchOn = false;

function camStop() {
    if (videoStream) { videoStream.getTracks().forEach(t => t.stop()); videoStream = null; }
    camTorchOn = false;
    const v = $('camera-video');
    if (v) v.srcObject = null;   // 前の映像の大きさを残さない（次に開いたとき、準備できるまで撮影しない）
    const tb = $('cam-torch');
    if (tb) { tb.classList.add('hidden'); tb.setAttribute('aria-pressed', 'false'); }
}

function openCameraFull() {
    const box = $('cam-full');
    if (!box) return;
    const link = document.querySelector('#target-lang-container a');
    $('cam-pair').textContent = link ? '→ ' + link.textContent.trim() : '';
    box.classList.remove('hidden');
    document.documentElement.classList.add('cam-open');
    document.addEventListener('keydown', camKey);
}

function closeCameraFull() {
    camStop();
    const box = $('cam-full');
    if (box) box.classList.add('hidden');
    document.documentElement.classList.remove('cam-open');
    document.removeEventListener('keydown', camKey);
}
function camKey(ev) { if (ev.key === 'Escape') closeCameraFull(); }

async function startCamera() {
    openCameraFull();
    try {
        videoStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
        const video = $('camera-video');
        video.srcObject = videoStream;
        try {   // ライト（対応する端末だけ）
            const tr = videoStream.getVideoTracks()[0];
            const caps = tr && tr.getCapabilities ? tr.getCapabilities() : null;
            if (caps && caps.torch) $('cam-torch').classList.remove('hidden');
        } catch (e) {}
    } catch (err) {
        closeCameraFull();
        alert(UI.err_camera + ': ' + err.message);
    }
}

async function toggleTorch() {
    const tr = videoStream && videoStream.getVideoTracks()[0];
    if (!tr) return;
    try {
        await tr.applyConstraints({ advanced: [{ torch: !camTorchOn }] });
        camTorchOn = !camTorchOn;
        $('cam-torch').setAttribute('aria-pressed', camTorchOn ? 'true' : 'false');
    } catch (e) {}
}

// 撮った（選んだ）写真をカメラタブに出す。翻訳は「翻訳する」を押したときだけ（無料枠を使わない）
function camTake(dataUrl) {
    $('camera_data').value = dataUrl;
    if (typeof storeLastImage === 'function') storeLastImage(dataUrl, 'camera');   // 結果に写真を重ねて見せるため、端末に一時保持
    closeCameraFull();
    const pv = $('camera-preview');
    pv.src = dataUrl;
    pv.classList.remove('hidden');
    $('camera-placeholder').classList.add('hidden');
    $('camera-submit-btn').disabled = false;
    $('camera-open-btn').querySelector('.btn-label').textContent = UI.cam_retake;   // 「カメラで撮る」→「撮り直す」
}

function captureCamera() {
    const video = $('camera-video');
    if (!videoStream || !video.videoWidth) { alert(UI.err_camera_first); return; }
    const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
    const canvas = $('camera-canvas');
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    camTake(canvas.toDataURL('image/jpeg', 0.85));
}

// アルバムの写真を選んで、そのまま翻訳する
async function cameraFromFile(input) {
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;
    try {
        const blob = await downscaleImage(file);
        camTake(await blobToDataURL(blob || file));
    } catch (e) { alert(UI.err_camera_first); }
}

