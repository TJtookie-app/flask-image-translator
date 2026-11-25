"""翻訳まわりの API（文字・PDF・別の言い方・解説）"""

from flask import jsonify, request
from helpers import (
    MAX_TEXT_LEN, SUMMARY_MIN_CHARS, api_error, clean_context, clean_glossary,
    get_ui, get_ui_lang, guard, read_pdf_upload,
    track,
)
from languages import AUTO, is_supported, normalize_language_name
import translator
from translator import TranslationError


def register(app):
    @app.route("/api/translate-text", methods=["POST"])
    def api_translate_text():
        ui = get_ui()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()
        source, target = data.get("source"), data.get("target")

        def fail(key, status=None):
            track("api", key) if key not in ("err_empty", "err_too_long") else None
            return api_error(ui, key, status)

        if not text:
            return fail("err_empty", 400)
        if len(text) > MAX_TEXT_LEN:
            return fail("err_too_long", 400)
        if not is_supported(target) or not is_supported(source, allow_auto=True):
            return fail("err_failed", 400)
        try:
            guard()
            result = translator.translate_text(
                text, source, target,
                context=clean_context(data.get("context")),
                glossary=clean_glossary(data.get("glossary")),
                formality=translator.clean_formality(data.get("formality")),
                pronunciation=bool(data.get("pron")),
            )
        except TranslationError as e:
            return fail(e.key)
        track("api")
        return jsonify(
            translation=result["translation"] or result["source_text"],
            detected=normalize_language_name(result["detected_language"]) or result["detected_language"],
            pronunciation=result.get("pronunciation") or "",
        )

    @app.route("/api/translate-pdf", methods=["POST"])
    def api_translate_pdf():
        """PDF を数ページずつ翻訳する。クライアントが start/end をずらして繰り返し呼ぶ"""
        ui = get_ui()

        def fail(key, status=None):
            track("pdf", key) if key not in ("err_pdf", "err_pdf_big") else None
            return api_error(ui, key, status)

        target = request.form.get("target")
        if not is_supported(target):
            return fail("err_failed", 400)
        try:
            start = max(1, int(request.form.get("start") or 1))
            end = int(request.form.get("end") or start + translator.PDF_CHUNK - 1)
        except ValueError:
            return fail("err_failed", 400)
        try:
            data = read_pdf_upload()
            total = translator.pdf_page_count(data)
            limit = min(total, translator.PDF_MAX_PAGES)
            end = min(end, limit, start + translator.PDF_CHUNK - 1)
            if start > end:
                return fail("err_pdf", 400)
            guard()
            pages = translator.translate_pdf_pages(
                data, target, start, end, formality=translator.clean_formality(request.form.get("formality")))
        except TranslationError as e:
            return fail(e.key)
        track("pdf")
        return jsonify(pages=pages, total=total, limit=limit, max_pages=translator.PDF_MAX_PAGES)

    @app.route("/api/alternatives", methods=["POST"])
    def api_alternatives():
        """「別の言い方」: 同じ原文の言い換えを最大3つ返す"""
        ui = get_ui()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()
        current = str(data.get("translation") or "").strip()
        source, target = data.get("source"), data.get("target")

        def fail(key, status=None):
            track("alt", key) if key not in ("err_empty", "err_too_long") else None
            return api_error(ui, key, status)

        if not text or not current:
            return fail("err_empty", 400)
        if len(text) > MAX_TEXT_LEN or len(current) > MAX_TEXT_LEN:
            return fail("err_too_long", 400)
        if not is_supported(target) or not is_supported(source or AUTO, allow_auto=True):
            return fail("err_failed", 400)
        try:
            guard()
            items = translator.alternative_translations(
                text, current, source or AUTO, target,
                formality=translator.clean_formality(data.get("formality")),
            )
        except TranslationError as e:
            return fail(e.key)
        track("alt")
        return jsonify(alternatives=items)

    @app.route("/api/tones", methods=["POST"])
    def api_tones():
        """「口調を変える」: 同じ原文の訳を、丁寧・標準・くだけたの3つで1回の呼び出しで返す"""
        ui = get_ui()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()
        current = str(data.get("translation") or "").strip()
        source, target = data.get("source"), data.get("target")

        def fail(key, status=None):
            track("tone", key) if key not in ("err_empty", "err_too_long") else None
            return api_error(ui, key, status)

        if not text or not current:
            return fail("err_empty", 400)
        if len(text) > MAX_TEXT_LEN or len(current) > MAX_TEXT_LEN:
            return fail("err_too_long", 400)
        if not is_supported(target) or not is_supported(source or AUTO, allow_auto=True):
            return fail("err_failed", 400)
        try:
            guard()
            tones = translator.tone_translations(text, current, source or AUTO, target)
        except TranslationError as e:
            return fail(e.key)
        track("tone")
        return jsonify(tones=tones)

    @app.route("/api/summarize", methods=["POST"])
    def api_summarize():
        """長文の「要約」: 原文を、いまの画面の言語で要約する（ボタンを押したときだけ呼ばれる）"""
        ui = get_ui()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()

        def fail(key, status=None):
            track("summary", key) if key not in ("err_empty", "err_too_long") else None
            return api_error(ui, key, status)

        if len(text) < SUMMARY_MIN_CHARS:
            return fail("err_empty", 400)
        if len(text) > MAX_TEXT_LEN:
            return fail("err_too_long", 400)
        try:
            guard()
            summary = translator.summarize_text(text, get_ui_lang() or "English")
        except TranslationError as e:
            return fail(e.key)
        track("summary")
        return jsonify(summary=summary)

    @app.route("/api/explain", methods=["POST"])
    def api_explain():
        ui = get_ui()
        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()

        def fail(key, status=None):
            track("api", key) if key not in ("err_empty", "err_too_long") else None
            return api_error(ui, key, status)

        if not text:
            return fail("err_empty", 400)
        if len(text) > 1000:
            return fail("err_too_long", 400)
        lang = data.get("lang")
        explain_in = data.get("explain_in")
        try:
            guard()
            explanation = translator.explain_text(
                text,
                lang if is_supported(lang) else "",
                explain_in if is_supported(explain_in) else (get_ui_lang() or "English"),
            )
        except TranslationError as e:
            return fail(e.key)
        track("explain")
        return jsonify(explanation=explanation)
