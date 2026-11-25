// 単位変換（通貨タブの中）: 長さ・重さ・温度・体積・面積。計算は端末の中だけ（API なし・オフラインで動く）
// f = 基準の単位に直す倍率（温度だけは式）。名前は記号なので、どの言語でもそのまま読める
const UNIT_SETS = {
    length: { def: ['km', 'mi'], units: { mm: 0.001, cm: 0.01, m: 1, km: 1000, in: 0.0254, ft: 0.3048, yd: 0.9144, mi: 1609.344 } },
    weight: { def: ['kg', 'lb'], units: { g: 0.001, kg: 1, oz: 0.028349523125, lb: 0.45359237 } },
    temp: { def: ['°C', '°F'], v: 20 },
    volume: { def: ['L', 'gal'], units: { mL: 0.001, L: 1, 'fl oz': 0.0295735295625, cup: 0.2365882365, gal: 3.785411784 } },
    area: { def: ['m²', 'ft²'], units: { 'm²': 1, 'km²': 1e6, ha: 1e4, 'ft²': 0.09290304, acre: 4046.8564224, tsubo: 400 / 121 } },
};
const UNIT_TEMP = {   // 温度: セ氏を基準に、行き来する式
    '°C': { to: (x) => x, from: (x) => x },
    '°F': { to: (x) => (x - 32) * 5 / 9, from: (x) => x * 9 / 5 + 32 },
    K: { to: (x) => x - 273.15, from: (x) => x + 273.15 },
};
let unitCat = 'length';

function unitNames(cat) { return cat === 'temp' ? Object.keys(UNIT_TEMP) : Object.keys(UNIT_SETS[cat].units); }

// 全角の数字・カンマ・小数点を読めるようにする
function unitParse(s) {
    let t = String(s || '').replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xFEE0)).replace(/[．。]/g, '.').replace(/[，、]/g, ',').replace(/\s/g, '');
    t = /^-?\d+,\d{1,2}$/.test(t) ? t.replace(',', '.') : t.replace(/,/g, '');
    return /^-?(\d+\.?\d*|\.\d+)$/.test(t) ? parseFloat(t) : NaN;
}

function unitFormat(x) {
    if (!isFinite(x)) return '—';
    return new Intl.NumberFormat(document.documentElement.lang || undefined, { maximumSignificantDigits: 7 }).format(Math.abs(x) < 1e-12 ? 0 : x);
}

function unitCalc(cat, v, from, to) {
    if (cat === 'temp') return UNIT_TEMP[to].from(UNIT_TEMP[from].to(v));
    const u = UNIT_SETS[cat].units;
    return v * u[from] / u[to];
}

function unitConvert() {
    const v = unitParse($('unit-amount').value), from = $('unit-from').value, to = $('unit-to').value, out = $('unit-result');
    out.textContent = isNaN(v) ? '—' : unitFormat(unitCalc(unitCat, v, from, to)) + ' ' + to;
}

function unitFill(sel, names, pick) {
    sel.replaceChildren();
    names.forEach(n => { const o = document.createElement('option'); o.value = n; o.textContent = n; sel.appendChild(o); });
    sel.value = pick;
}

function unitSetCat(cat) {
    unitCat = cat;
    const names = unitNames(cat), def = UNIT_SETS[cat].def;
    unitFill($('unit-from'), names, def[0]);
    unitFill($('unit-to'), names, def[1]);
    if (UNIT_SETS[cat].v) $('unit-amount').value = UNIT_SETS[cat].v; else if (!unitParse($('unit-amount').value)) $('unit-amount').value = 1;
    document.querySelectorAll('#unit-cats button').forEach(b => {
        const on = b.dataset.cat === cat;
        b.setAttribute('aria-selected', on ? 'true' : 'false');
        b.classList.toggle('on', on);
    });
    unitConvert();
}

function unitSwap() {
    const a = $('unit-from'), b = $('unit-to'), t = a.value;
    a.value = b.value; b.value = t;
    unitConvert();
}

document.addEventListener('DOMContentLoaded', () => {
    const box = $('unit-cats');
    if (!box) return;
    Object.keys(UNIT_SETS).forEach(cat => {
        const b = document.createElement('button');
        b.type = 'button'; b.dataset.cat = cat; b.className = 'unit-cat'; b.setAttribute('role', 'tab');
        b.textContent = UI['unit_' + cat];
        b.addEventListener('click', () => unitSetCat(cat));
        box.appendChild(b);
    });
    unitSetCat('length');
});
