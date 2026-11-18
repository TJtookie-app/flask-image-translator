# 対応言語リスト（name はフォーム値・Geminiへの指示に使う英語名、code は音声認識用 BCP-47）
# 言語を増やすときは LANGUAGES に1行足すだけでOK
import re

AUTO = "Auto"  # 翻訳元の自動判定（翻訳元にだけ指定できる）

# name: フォーム値・Geminiへの指示に使う英語名 / code: 音声認識・読み上げ用 BCP-47 / rtl: 右から左へ書く言語
_RAW = [
    ("Japanese", "ja-JP", "日本語", False),
    ("English", "en-US", "English", False),
    ("Chinese (Simplified)", "zh-CN", "简体中文", False),
    ("Chinese (Traditional)", "zh-TW", "繁體中文", False),
    ("Korean", "ko-KR", "한국어", False),
    ("Spanish", "es-ES", "Español", False),
    ("French", "fr-FR", "Français", False),
    ("German", "de-DE", "Deutsch", False),
    ("Italian", "it-IT", "Italiano", False),
    ("Portuguese", "pt-BR", "Português", False),
    ("Russian", "ru-RU", "Русский", False),
    ("Arabic", "ar-SA", "العربية", True),
    ("Hindi", "hi-IN", "हिन्दी", False),
    ("Bengali", "bn-BD", "বাংলা", False),
    ("Tamil", "ta-IN", "தமிழ்", False),
    ("Urdu", "ur-PK", "اردو", True),
    ("Persian", "fa-IR", "فارسی", True),
    ("Hebrew", "he-IL", "עברית", True),
    ("Turkish", "tr-TR", "Türkçe", False),
    ("Indonesian", "id-ID", "Bahasa Indonesia", False),
    ("Malay", "ms-MY", "Bahasa Melayu", False),
    ("Filipino", "fil-PH", "Filipino", False),
    ("Thai", "th-TH", "ไทย", False),
    ("Vietnamese", "vi-VN", "Tiếng Việt", False),
    ("Dutch", "nl-NL", "Nederlands", False),
    ("Polish", "pl-PL", "Polski", False),
    ("Ukrainian", "uk-UA", "Українська", False),
    ("Czech", "cs-CZ", "Čeština", False),
    ("Slovak", "sk-SK", "Slovenčina", False),
    ("Hungarian", "hu-HU", "Magyar", False),
    ("Romanian", "ro-RO", "Română", False),
    ("Bulgarian", "bg-BG", "Български", False),
    ("Greek", "el-GR", "Ελληνικά", False),
    ("Croatian", "hr-HR", "Hrvatski", False),
    ("Serbian", "sr-RS", "Српски", False),
    ("Swedish", "sv-SE", "Svenska", False),
    ("Norwegian", "nb-NO", "Norsk", False),
    ("Danish", "da-DK", "Dansk", False),
    ("Finnish", "fi-FI", "Suomi", False),
    ("Catalan", "ca-ES", "Català", False),
    ("Swahili", "sw-KE", "Kiswahili", False),
]
LANGUAGES = [{"name": n, "code": c, "native": nat, "rtl": rtl} for n, c, nat, rtl in _RAW]

SUPPORTED_LANGUAGES = [l["name"] for l in LANGUAGES]
_BY_NAME = {l["name"]: l for l in LANGUAGES}
_BY_LOWER = {l["name"].lower(): l["name"] for l in LANGUAGES}


def is_supported(name, allow_auto=False):
    return name in _BY_NAME or (allow_auto and name == AUTO)


# AIが英語名の代わりに言語コードで返してきたときのための対応表（2文字・3文字・旧コード）
_BY_CODE = {}
for _l in LANGUAGES:
    _BY_CODE.setdefault(_l["code"].split("-")[0].lower(), _l["name"])
_BY_CODE.update({
    "iw": "Hebrew", "in": "Indonesian", "tl": "Filipino", "no": "Norwegian", "nn": "Norwegian",
    "jpn": "Japanese", "eng": "English", "kor": "Korean", "spa": "Spanish", "fra": "French", "fre": "French",
    "deu": "German", "ger": "German", "ita": "Italian", "por": "Portuguese", "rus": "Russian", "ara": "Arabic",
    "hin": "Hindi", "ben": "Bengali", "tam": "Tamil", "urd": "Urdu", "fas": "Persian", "per": "Persian",
    "heb": "Hebrew", "tur": "Turkish", "ind": "Indonesian", "msa": "Malay", "may": "Malay", "tgl": "Filipino",
    "tha": "Thai", "vie": "Vietnamese", "nld": "Dutch", "dut": "Dutch", "pol": "Polish", "ukr": "Ukrainian",
    "ces": "Czech", "cze": "Czech", "slk": "Slovak", "slo": "Slovak", "hun": "Hungarian", "ron": "Romanian",
    "rum": "Romanian", "bul": "Bulgarian", "ell": "Greek", "gre": "Greek", "hrv": "Croatian", "srp": "Serbian",
    "swe": "Swedish", "nob": "Norwegian", "nor": "Norwegian", "dan": "Danish", "fin": "Finnish", "cat": "Catalan",
    "swa": "Swahili",
})
_BY_NATIVE = {l["native"].lower(): l["name"] for l in LANGUAGES}
_ZH_TRAD_TAGS = {"tw", "hk", "mo", "hant"}


def normalize_language_name(name):
    """Geminiが返した言語名・言語コード（es, ja, zh-TW, spa など）を、対応言語の正式名に寄せる。見つからなければ None"""
    if not name:
        return None
    key = str(name).strip().lower()
    if not key:
        return None
    if key in _BY_LOWER:
        return _BY_LOWER[key]
    if key in _BY_NATIVE:                      # "español" "日本語" のような、その言語での名前
        return _BY_NATIVE[key]
    tag = key.replace("_", "-").split("-")
    # 中国語は簡体・繁体に分ける（既定は簡体）
    if "chinese" in key or tag[0] in ("zh", "zho", "chi", "cmn", "yue") or key in ("mandarin", "cantonese"):
        trad = "traditional" in key or key == "cantonese" or tag[0] == "yue" or bool(_ZH_TRAD_TAGS & set(tag[1:]))
        return "Chinese (Traditional)" if trad else "Chinese (Simplified)"
    if tag[0] in _BY_CODE:                     # es / es-ES / pt-BR / spa
        return _BY_CODE[tag[0]]
    for lower, canonical in _BY_LOWER.items():  # "Portuguese (Brazil)" のような揺れ
        if key.split(" (")[0] == lower.split(" (")[0]:
            return canonical
    first = key.split()[0]                     # "Norwegian Bokmål" のように、頭の単語が同じ
    for lower, canonical in _BY_LOWER.items():
        if first == lower.split()[0] and first != "chinese":
            return canonical
    return None


def intl_tag(code):
    """ブラウザの Intl.DisplayNames に渡す言語タグ（中国語は簡体・繁体、ノルウェー語は no）"""
    code = str(code or "")
    if code in ("zh-CN", "zh-SG"):
        return "zh-Hans"
    if code in ("zh-TW", "zh-HK"):
        return "zh-Hant"
    primary = code.split("-")[0]
    return "no" if primary == "nb" else primary


def language_badge(raw):
    """結果の「🌐 言語」バッジ用。label は JS が使えないときの表示、tag/native は画面で「Español（スペイン語）」にするために渡す"""
    canon = normalize_language_name(raw)
    if canon:
        l = _BY_NAME[canon]
        label = l["native"] if l["native"].lower() == canon.lower() else f'{l["native"]} ({canon})'
        return {"label": label, "tag": intl_tag(l["code"]), "native": l["native"]}
    raw = str(raw or "").strip()
    looks_like_code = bool(re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?", raw))   # 対応外の言語コード（eo など）も、画面で名前に直せる
    return {"label": raw, "tag": raw if looks_like_code else "", "native": ""}


def get_lang_code(name):
    if name == AUTO:
        return ""
    return _BY_NAME.get(name, _BY_NAME["English"])["code"]


def get_native_name(name):
    return _BY_NAME.get(name, {}).get("native", name)


def is_rtl(name):
    return bool(_BY_NAME.get(name, {}).get("rtl"))


# 各言語のUIラベル辞書（未登録の言語・キーは English で補完）
# 日本語・英語の中身は labels_ja.py / labels_en.py に分けてある
from labels_en import LABELS as _LABELS_EN  # noqa: E402
from labels_ja import LABELS as _LABELS_JA  # noqa: E402

UI_LABELS = {
    'Japanese': _LABELS_JA,
    'English': _LABELS_EN,
}


# どの表示言語でも固定する文言
FIXED_LABELS = {
    'source_label': 'From',
    'target_label': 'To',
    'target_label_short': 'To',
}


def get_ui_labels(lang):
    """指定言語のUIラベル。足りないキーは English で補完する"""
    labels = dict(UI_LABELS['English'])
    labels.update(UI_LABELS.get(lang, {}))
    labels.update(FIXED_LABELS)
    return labels
