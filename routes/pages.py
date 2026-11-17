"""画面（トップ・言語選択・言語の切り替え）のルート。フォームの POST（text/voice/image/camera の翻訳）もここ"""

import json

from flask import redirect, render_template, request, session, url_for
from helpers import (
    ERROR_STATUS, MAX_TEXT_LEN, VALID_MODES, clean_glossary,
    client_ip, get_langs, get_ui, get_ui_lang,
    guard, read_camera_data, read_upload, remember_recent,
    render_main, track,
)
from limits import limiter
from languages import (
    AUTO, LANGUAGES, get_lang_code, is_rtl,
    is_supported, normalize_language_name, language_badge,
)
import translator
from translator import TranslationError
from ui_i18n import ensure_async, ensure_ui_labels, has_labels


def register(app):
    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "GET":
            if not get_ui_lang():
                return redirect(url_for("start"))
            ensure_async(get_ui_lang())
            return render_main()

        source_lang, target_lang = get_langs()
        mode = request.form.get("mode", "text")
        if mode not in VALID_MODES:
            mode = "text"
        ctx = {"active_mode": mode}
        formality = translator.clean_formality(request.form.get("formality"))
        want_pron = request.form.get("pron") == "1"

        try:
            if mode in ("text", "voice"):
                field = "direct_text" if mode == "text" else "voice_text"
                text = (request.form.get(field) or "").strip()
                ctx["input_text"] = text
                if not text:
                    raise TranslationError("err_empty")
                if len(text) > MAX_TEXT_LEN:
                    raise TranslationError("err_too_long")
                try:
                    glossary = clean_glossary(json.loads(request.form.get("glossary") or "[]"))
                except ValueError:
                    glossary = []
                guard()
                result = translator.translate_text(
                    text, source_lang, target_lang, glossary=glossary,
                    formality=formality, pronunciation=want_pron)
            else:
                if mode == "image":
                    data, mime = read_upload()
                else:
                    data, mime = read_camera_data(request.form.get("camera_data"))
                guard()
                if request.form.get("overlay") == "1":
                    result = translator.translate_image_blocks(data, mime, target_lang, formality=formality)
                    ctx["overlay_blocks"] = result["blocks"]
                else:
                    result = translator.translate_image(data, mime, target_lang, pronunciation=want_pron)
            track(mode)

            detected = normalize_language_name(result["detected_language"])
            if detected:
                session["last_detected"] = detected
            show_detected = mode in ("image", "camera") or source_lang == AUTO
            badge = language_badge(result["detected_language"]) if show_detected else {"label": "", "tag": "", "native": ""}
            ctx.update(
                translated_text=result["translation"] or result["source_text"],
                original_text=result["source_text"] if mode in ("image", "camera") else None,
                detected_lang=badge["label"] or None,
                detected_tag=badge["tag"] or None,
                detected_native=badge["native"] or None,
                pronunciation=result.get("pronunciation") or None,
                same_detected=bool(detected and detected == target_lang),
            )
            if ctx["translated_text"]:
                ctx["result_entry"] = {
                    "mode": mode,
                    "src": ctx.get("input_text") or result["source_text"],
                    "out": ctx["translated_text"],
                    "srcLang": detected or (source_lang if source_lang != AUTO else "") or result["detected_language"],
                    "tgt": target_lang,
                    "tcode": get_lang_code(target_lang),
                    "pron": result.get("pronunciation") or "",
                }
        except TranslationError as e:
            if e.key not in ("err_empty", "err_too_long", "err_image"):
                track(mode, e.key)
            ctx["error"] = get_ui().get(e.key, e.key)
            return render_main(status=ERROR_STATUS.get(e.key, 502) if e.key in ("err_rate", "err_busy", "err_daily") else 200, **ctx)

        return render_main(**ctx)

    @app.errorhandler(413)
    def too_large(_e):
        return render_main(status=413, active_mode="image", error=get_ui()["err_too_big"])

    @app.route("/select-language")
    def select_language():
        lang_type = "source" if request.args.get("type") == "source" else "target"
        source_lang, target_lang = get_langs()
        current = source_lang if lang_type == "source" else target_lang
        return render_template(
            "select_language.html",
            languages=LANGUAGES,
            lang_type=lang_type,
            current=current,
            recent=[n for n in session.get("recent", []) if is_supported(n)],
            auto=AUTO,
            ui=get_ui(),
            ui_code=get_lang_code(get_ui_lang() or "English"),
            ui_rtl=is_rtl(get_ui_lang() or "English"),
        )

    @app.route("/start")
    def start():
        current = get_ui_lang()
        return render_template("start.html", languages=LANGUAGES, current=current, can_close=bool(current))

    @app.route("/set-display-language", methods=["POST"])
    def set_display_language():
        lang = request.form.get("ui_lang")
        if not is_supported(lang):
            return redirect(url_for("start"))
        if not has_labels(lang) and not limiter.check(client_ip()):
            ensure_ui_labels(lang)  # 未生成の言語はここで文言を自動翻訳（失敗時は英語表示）
        session.permanent = True
        session["ui_lang"] = lang
        session["target_lang"] = lang

        if session.get("source_lang") == lang:
            session["source_lang"] = "English" if lang != "English" else "Japanese"

        remember_recent(lang)
        if request.form.get("network_mode") == "offline":   # スタート画面で「オフライン」を選んだ
            return redirect(url_for("offline"))
        return redirect(url_for("index"))

    @app.route("/set-language", methods=["POST"])
    def set_language():
        selected = request.form.get("target_lang", "English")
        lang_type = "source" if request.form.get("lang_type") == "source" else "target"
        if lang_type == "source" and selected == AUTO:
            session["source_lang"] = AUTO
        elif is_supported(selected):
            session["source_lang" if lang_type == "source" else "target_lang"] = selected
            remember_recent(selected)
        return redirect(url_for("index"))

    @app.route("/swap-language", methods=["POST"])
    def swap_language():
        source, target = get_langs()
        if source == AUTO:
            detected = session.get("last_detected")
            new_target = detected if is_supported(detected) and detected != target else (
                "English" if target != "English" else "Japanese")
            session["source_lang"], session["target_lang"] = target, new_target
        else:
            session["source_lang"], session["target_lang"] = target, source
        return redirect(url_for("index"))
