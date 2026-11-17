// 単語帳と復習（忘れかけたころに出す簡易の間隔反復）。データはこの端末の localStorage のみ
let studyQueue = [];
let studyCurrent = null;
let studyTotal = 0;
// 復習の向き: 'fwd' = 原文を見て訳を思い出す（従来）/ 'rev' = 訳を見て原文を思い出す（逆引き）。向きごとに覚えた度合いを別に持つ
const SDIR_KEY = 'tl_study_dir_v1';
let studyDir = 'fwd';
try { if (localStorage.getItem(SDIR_KEY) === 'rev') studyDir = 'rev'; } catch (e) {}
const dueOf = (v) => (studyDir === 'rev' ? v.rdue : v.due) || 0;

function setStudyDir(d) {
    studyDir = d === 'rev' ? 'rev' : 'fwd';
    try { localStorage.setItem(SDIR_KEY, studyDir); } catch (e) {}
    if (studyCurrent) { studyCurrent = null; studyQueue = []; $('study-card').classList.add('hidden'); }
    $('study-msg').classList.add('hidden');
    renderStudy();
}

// 訳文の「しおり」ボタンから保存
function saveVocabEntry(entry, btn) {
    addVocab(entry);
    const icon = btn && btn.querySelector('i');
    if (icon) {
        icon.className = 'fa-solid fa-bookmark text-indigo-400';
        btn.title = UI.vocab_saved;
        const label = btn.querySelector('.rc-label');
        if (label) label.textContent = UI.vocab_saved;
        if (typeof closeResultMenus === 'function') closeResultMenus();
    }
}

function saveVocabCurrent(mode, btn) {
    const el = $('resultText-' + mode);
    if (!el || !RESULT) return;
    const pr = $('pron-' + mode);
    saveVocabEntry({
        src: RESULT.src || RESULT.out, out: el.innerText, srcLang: RESULT.srcLang, tgt: RESULT.tgt,
        tcode: RESULT.tcode, pron: pr && !pr.classList.contains('hidden') ? pr.innerText : '',
    }, btn);
}

const dueCards = () => loadVocab().filter(v => dueOf(v) <= Date.now()).sort((a, b) => dueOf(a) - dueOf(b));

function renderStudy() {
    const all = loadVocab(), due = dueCards();
    [['fwd', 'study-dir-fwd'], ['rev', 'study-dir-rev']].forEach(([d, id]) => {
        const b = $(id);
        if (!b) return;
        b.setAttribute('aria-pressed', String(studyDir === d));
        b.className = 'flex-1 px-3 py-2 rounded-xl text-xs font-semibold border border-slate-700 transition ' +
            (studyDir === d ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300');
    });
    $('study-stats').textContent = fmt(UI.study_total, { n: all.length }) + ' / ' + fmt(UI.study_due, { n: due.length });
    $('study-start').classList.toggle('hidden', !due.length || !!studyCurrent);
    const msg = $('study-msg');
    if (!studyCurrent) {
        msg.classList.toggle('hidden', !all.length || !!due.length);
        msg.textContent = UI.study_nodue;
    }
    $('study-empty').classList.toggle('hidden', all.length > 0);

    const box = $('study-list');
    box.replaceChildren();
    all.forEach(v => {
        const card = document.createElement('div');
        card.className = 'p-3 rounded-2xl bg-slate-950/60 border border-slate-800 space-y-1';
        const src = document.createElement('div');
        src.dir = 'auto';
        src.className = 'text-sm text-slate-100 whitespace-pre-wrap break-words';
        src.textContent = v.src;
        const out = document.createElement('div');
        out.dir = 'auto';
        out.className = 'text-sm text-indigo-200 font-medium whitespace-pre-wrap break-words';
        out.textContent = v.out;
        const row = document.createElement('div');
        row.className = 'flex gap-1 justify-end';
        row.append(
            iconBtn('fa-solid fa-volume-high', UI.speak, () => speak(v.out, v.tcode || codeOf(v.tgt))),
            iconBtn('fa-solid fa-trash', UI.delete, () => {
                const tid = trashAdd('vocab', [v]);
                saveVocab(loadVocab().filter(x => x.id !== v.id));
                if (studyCurrent && studyCurrent.id === v.id) endStudy();
                renderStudy();
                undoToast(tid);
            }),
        );
        card.append(src, out, row);
        box.appendChild(card);
    });
}

function startStudy() {
    studyQueue = dueCards().slice(0, 20);
    studyTotal = studyQueue.length;
    if (!studyQueue.length) { renderStudy(); return; }
    $('study-msg').classList.add('hidden');
    nextStudy();
}

// いまの向きでの「問題」と「答え」。逆引きは、訳を見て原文を思い出す
function studyFace(v) {
    return studyDir === 'rev'
        ? { q: v.out, a: v.src, qPron: v.pron || '', aPron: '', aLang: codeOf(v.srcLang), qLang: v.tcode || codeOf(v.tgt) }
        : { q: v.src, a: v.out, qPron: '', aPron: v.pron || '', aLang: v.tcode || codeOf(v.tgt), qLang: codeOf(v.srcLang) };
}

function nextStudy() {
    studyCurrent = studyQueue.shift() || null;
    if (!studyCurrent) { endStudy(true); return; }
    const f = studyFace(studyCurrent);
    $('study-card').classList.remove('hidden');
    $('study-start').classList.add('hidden');
    $('study-front').textContent = f.q;
    $('study-front-pron').textContent = f.qPron;
    $('study-front-pron').classList.toggle('hidden', !f.qPron);
    $('study-answer').textContent = f.a;
    $('study-pron').textContent = f.aPron;
    $('study-speak').onclick = () => speak(f.a, f.aLang);
    $('study-front-speak').onclick = () => speak(f.q, f.qLang);
    $('study-front-speak').classList.toggle('hidden', studyDir !== 'rev');   // 逆引きは、問題（訳）を先に聞ける
    $('study-left').textContent = fmt(UI.study_left, { n: studyQueue.length + 1 });
    $('study-back').classList.add('hidden');
    $('study-grade').classList.add('hidden');
    $('study-reveal').classList.remove('hidden');
}

function revealStudy() {
    if (!studyCurrent) return;
    const f = studyFace(studyCurrent);
    $('study-back').classList.remove('hidden');
    $('study-grade').classList.remove('hidden');
    $('study-reveal').classList.add('hidden');
    speak(f.a, f.aLang);
}

function endStudy(finished) {
    studyCurrent = null;
    studyQueue = [];
    $('study-card').classList.add('hidden');
    renderStudy();
    if (finished) {
        const msg = $('study-msg');
        msg.textContent = UI.study_done;
        msg.classList.remove('hidden');
    }
}

// 覚えた: 次の復習までの間隔を延ばす / もう一度: 最初からやり直し（今回のうちにもう一度出す）
function gradeStudy(good) {
    if (!studyCurrent) return;
    const list = loadVocab();
    const v = list.find(x => x.id === studyCurrent.id);
    if (v) {
        const bk = studyDir === 'rev' ? 'rbox' : 'box', dk = studyDir === 'rev' ? 'rdue' : 'due';
        if (good) {
            v[bk] = Math.min(SRS_DAYS.length - 1, (v[bk] || 0) + 1);
            v[dk] = Date.now() + SRS_DAYS[v[bk]] * 86400000;
        } else {
            v[bk] = 0;
            v[dk] = 0;
            studyQueue.push(v);
        }
        saveVocab(list);
    }
    nextStudy();
}
