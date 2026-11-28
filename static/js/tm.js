// 翻訳メモリー（v1.10.0）: オンラインで訳した文を端末に覚えておき、圏外のときに先に探す。この端末の localStorage のみ（外には送らない）。
// 手直しした訳（user）は、いつも優先し、古くなっても消さない。似た文は、数字が同じで、よく似ているときだけ使う。
const TMKEY = 'tl_tm_v1';
const TMMAX = 1500;          // 全体の上限（超えたら、使われていない古いものから消す）
const TMUSER_MAX = 500;      // 手直しした訳の上限
const TMSRC_MAX = 300;       // 長い文は覚えない（短い文・言い回しが中心）
const TM_SIMILAR = 0.9;      // 似た文とみなす近さ（0〜1）

function tmNorm(s) { return String(s || '').normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim(); }

function tmLoad() {
    try {
        const a = JSON.parse(localStorage.getItem(TMKEY) || '[]');
        return Array.isArray(a) ? a : [];
    } catch (e) { return []; }
}

function tmSave(list) {
    const users = list.filter(x => x.u).slice(0, TMUSER_MAX);
    const rest = list.filter(x => !x.u).slice(0, Math.max(0, TMMAX - users.length));
    let out = users.concat(rest).sort((a, b) => b.ts - a.ts);
    for (let i = 0; i < 3; i++) {
        try { localStorage.setItem(TMKEY, JSON.stringify(out)); return; } catch (e) { out = out.slice(0, Math.ceil(out.length / 2)); }
    }
}

function tmEnabled() { return loadSettings().tm !== false; }
function tmCount() { return tmLoad().length; }
function tmClear() { try { localStorage.removeItem(TMKEY); } catch (e) {} }

// 覚える。同じ原文・同じ翻訳先は、訳を新しくする（手直し済みのものは、手直しでないものでは上書きしない）
function tmAdd(src, out, tgt, user) {
    const raw = String(src || '').trim(), o = String(out || '').trim(), s = tmNorm(raw);
    if (!tmEnabled() || !s || !o || !tgt || raw.length > TMSRC_MAX || o.length > TMSRC_MAX * 4) return false;
    const list = tmLoad();
    const i = list.findIndex(x => x.s === s && x.t === tgt);
    if (i >= 0) {
        if (list[i].u && !user) return false;
        list.splice(i, 1);
    }
    list.unshift({ s, r: raw, o, t: tgt, u: user ? 1 : 0, ts: Date.now() });
    tmSave(list);
    return true;
}

function tmGrams(s) {
    const m = new Map();
    for (let i = 0; i < s.length - 1; i++) { const g = s.substr(i, 2); m.set(g, (m.get(g) || 0) + 1); }
    return m;
}

function tmDice(a, b) {
    const ga = tmGrams(a), gb = tmGrams(b);
    let hit = 0, total = 0;
    ga.forEach((n, g) => { total += n; hit += Math.min(n, gb.get(g) || 0); });
    gb.forEach((n) => { total += n; });
    return total ? (2 * hit) / total : 0;
}

// 似た文の比べ方では、空白と句読点・記号の違いは無視する（「駅はどこですか？」と「駅は、どこですか」）
const tmLoose = (s) => s.replace(/[\s、。，．,.!?！？「」『』"'・…~〜\-]/g, '');
const tmDigits = (s) => (s.match(/\d+/g) || []).join(',');

// 探す。{ out, kind: 'exact' | 'similar', src } か null。similar は同じ長さくらいで数字が同じものだけ
function tmFind(text, tgt, exactOnly) {
    if (!tmEnabled()) return null;
    const s = tmNorm(text);
    if (!s) return null;
    const list = tmLoad();
    const same = list.filter(x => x.t === tgt);
    const ex = same.filter(x => x.s === s).sort((a, b) => (b.u - a.u) || (b.ts - a.ts))[0];
    if (ex) return { out: ex.o, kind: 'exact', src: ex.r };
    const L = tmLoose(s);
    if (exactOnly || L.length < 5) return null;
    let best = null, bestScore = 0;
    for (const x of same) {
        const xl = tmLoose(x.s), r = xl.length / L.length;
        if (r < 0.8 || r > 1.25 || tmDigits(x.s) !== tmDigits(s)) continue;
        const d = tmDice(L, xl);
        if (d >= TM_SIMILAR && d > bestScore) { best = x; bestScore = d; }
    }
    return best ? { out: best.o, kind: 'similar', src: best.r } : null;
}
