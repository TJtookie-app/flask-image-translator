"""v1.6のブラウザ確認: 返信を提案／辞書・文法（結果カードの「…」メニュー）。使い方: python tests/e2e_v160.py"""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import translator
from werkzeug.serving import make_server
from app import app

calls = []
def fake(parts, system=None):
    p = parts[0] if parts and isinstance(parts[0], str) else ""
    calls.append((system or "", p))
    if system and '"replies"' in system:
        return json.dumps({"replies": [
            {"kind": "了解", "text": "Sounds good, see you at 7!", "meaning": "いいね、7時に会おう！"},
            {"kind": "断る", "text": "Sorry, I can't make it tonight.", "meaning": "ごめん、今夜は行けない。"},
            {"kind": "聞き返す", "text": "Where should we meet?", "meaning": "どこで待ち合わせる？"}]})
    if system and '"words"' in system:
        return json.dumps({"words": [
            {"word": "grab", "reading": "", "pos": "動詞", "meaning": "さっと取る", "example": "Let's grab a bite.", "origin": "古英語に由来"},
            {"word": "bite", "reading": "", "pos": "名詞", "meaning": "ひと口", "example": "", "origin": ""}],
            "grammar": [{"point": "Let's + 動詞", "note": "〜しよう、と誘う言い方。"}]})
    if "dinner" in p.lower():
        return '{"detected_language":"English","source_text":"Dinner tonight?","translation":"今夜、夕食どう？","pronunciation":""}'
    return '{"detected_language":"Japanese","source_text":"おはよう","translation":"Good morning","pronunciation":""}'
translator._generate = fake
srv = make_server("127.0.0.1", 5096, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5096"
fails, errs = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)
cnt = lambda pg, sel: pg.evaluate(f"document.querySelectorAll('{sel}').length")

def openmenu(pg):
    pg.click("#tab-text .rc-more"); pg.wait_for_selector("#tab-text .rc-menu:not(.hidden)", timeout=3000)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    for width in (320, 390):
        ctx = br.new_context(viewport={"width": width, "height": 800}, permissions=["clipboard-read", "clipboard-write"])
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
        ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__spoken=[];Object.defineProperty(window,'speechSynthesis',{value:{speak(u){window.__spoken.push(u.text)},cancel(){},getVoices(){return[]}},configurable:true});window.SpeechSynthesisUtterance=function(t){this.text=t}")
        pg.goto(B + "/", wait_until="domcontentloaded")
        tag = f"{width}px"
        # ---- 外国語を読む（英語 → 日本語） ----
        pg.fill("textarea[name=direct_text]", "Dinner tonight at 7?"); pg.click("#tab-text button[type=submit]"); pg.wait_for_selector("#resultText-text"); pg.wait_for_load_state("load"); pg.wait_for_timeout(300)
        openmenu(pg)
        items = pg.evaluate("[...document.querySelectorAll('#tab-text .rc-item')].filter(b => getComputedStyle(b).display !== 'none').map(b => b.textContent.trim())")
        check(f"{tag}: menu has 返信を提案 and 辞書・文法 {items}", "返信を提案" in items and "辞書・文法" in items)
        m = pg.evaluate("(() => { const r = document.querySelector('#tab-text .rc-menu').getBoundingClientRect(); return [r.top, r.bottom, innerHeight, r.left, r.right, innerWidth]; })()")
        check(f"{tag}: menu stays inside the screen {m}", m[0] >= 0 and m[1] <= m[2] + 1 and m[3] >= 0 and m[4] <= m[5] + 1)
        n0 = len(calls)
        pg.click("#tab-text .rc-reply"); pg.wait_for_selector("#replies-text .as-card")
        check(f"{tag}: 3 reply cards, one API call", cnt(pg, "#replies-text .as-card") == 3 and len(calls) == n0 + 1)
        txt = pg.inner_text("#replies-text")
        check(f"{tag}: reply text + kind + meaning shown", "Sounds good, see you at 7!" in txt and "断る" in txt and "いいね、7時に会おう！" in txt)
        check(f"{tag}: the request carried the original and its language", any('"replies"' in s and "Dinner tonight at 7?" in q and "English" in q for s, q in calls))
        pg.click("#replies-text .as-card >> nth=0 >> text=コピー"); pg.wait_for_timeout(150)
        check(f"{tag}: copy copies the reply in the other person's language", pg.evaluate("navigator.clipboard.readText()") == "Sounds good, see you at 7!")
        pg.click("#replies-text .as-card >> nth=1 >> text=読み上げ")
        check(f"{tag}: speak reads the reply", pg.evaluate("window.__spoken.at(-1)") == "Sorry, I can't make it tonight.")
        check(f"{tag}: no horizontal scroll with replies", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
        # ---- 辞書・文法 ----
        openmenu(pg); pg.click("#tab-text .rc-dict"); pg.wait_for_selector("#dict-text .as-card")
        check(f"{tag}: replies closed, dictionary open", pg.evaluate("document.getElementById('replies-text').classList.contains('hidden')") and cnt(pg, "#dict-text .as-card") == 3)
        d = pg.inner_text("#dict-text")
        check(f"{tag}: words (reading/pos/meaning/example/origin) and grammar shown", all(s in d for s in ("grab", "動詞", "さっと取る", "Let's grab a bite.", "語源・成り立ち: 古英語に由来", "文法のポイント", "Let's + 動詞")))
        check(f"{tag}: dictionary request used the original English", any('"words"' in s and "Dinner tonight at 7?" in q for s, q in calls))
        pg.click("#dict-text .as-card >> nth=0 >> text=単語帳に保存"); pg.wait_for_timeout(150)
        v = pg.evaluate("loadVocab()[0]")
        check(f"{tag}: word saved to the vocabulary book {v and (v['src'], v['out'])}", v and v["src"] == "grab" and v["out"] == "さっと取る" and v["srcLang"] == "English")
        check(f"{tag}: save button shows saved + disabled", pg.evaluate("(() => { const b = document.querySelector('#dict-text .as-card .as-row .as-btn:nth-child(2)'); return b.disabled; })()"))
        check(f"{tag}: no horizontal scroll with dictionary", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
        # ---- 自分の言語で入力 → 返信は隠れ、辞書は訳文（相手に言う側）を調べる ----
        pg.fill("textarea[name=direct_text]", "おはよう"); pg.click("#tab-text button[type=submit]"); pg.wait_for_selector("#resultText-text"); pg.wait_for_load_state("load"); pg.wait_for_timeout(300)
        openmenu(pg)
        hidden_reply = pg.evaluate("getComputedStyle(document.querySelector('#tab-text .rc-reply')).display") == "none"
        check(f"{tag}: own-language input hides 返信を提案", hidden_reply)
        pg.click("#tab-text .rc-dict"); pg.wait_for_selector("#dict-text .as-card")
        check(f"{tag}: dictionary looks up the translation (the thing you will say)", any('"words"' in s and "Good morning" in q for s, q in calls[-2:]))
        ctx.close()
    br.close()
check("no page errors " + str(errs), not errs)
print("FAILS:", fails)
sys.exit(1 if fails else 0)
