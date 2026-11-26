"""V12.10: routes.py と translator.py を分けただけで、動きは変わっていないことの確認"""
import glob
import json
import os

from conftest import ROOT

# 分ける前（V12.9.1）の URL の一覧。[URL, メソッド, 関数名(endpoint)]
ROUTES = [["/", ["GET", "POST"], "index"], ["/api/alternatives", ["POST"], "api_alternatives"], ["/api/clear-session", ["POST"], "api_clear_session"], ["/api/explain", ["POST"], "api_explain"], ["/api/quota", ["GET"], "quota"], ["/api/rates", ["GET"], "api_rates"], ["/api/stats", ["GET"], "api_stats"], ["/api/translate-pdf", ["POST"], "api_translate_pdf"], ["/api/translate-text", ["POST"], "api_translate_text"], ["/favicon.ico", ["GET"], "favicon"], ["/healthz", ["GET"], "healthz"], ["/manifest.webmanifest", ["GET"], "manifest"], ["/offline", ["GET"], "offline"], ["/privacy", ["GET"], "privacy"], ["/select-language", ["GET"], "select_language"], ["/set-display-language", ["POST"], "set_display_language"], ["/set-language", ["POST"], "set_language"], ["/start", ["GET"], "start"], ["/static/<path:filename>", ["GET"], "static"], ["/sw.js", ["GET"], "service_worker"], ["/swap-language", ["POST"], "swap_language"]]


def test_route_table_unchanged(env):
    app, *_ = env
    rows = [[r.rule, sorted(r.methods - {"HEAD", "OPTIONS"}), r.endpoint] for r in app.url_map.iter_rules()]
    missing = [r for r in ROUTES if r not in rows]
    assert not missing, missing                            # URL・メソッド・関数名（url_for で使う名前）が1つも変わっていない
    # （ほかのテストが試験用の URL を足すことがあるので、「分ける前の一覧が全部ある」で確かめる）
    assert len([r for r in rows if r[0].startswith(("/api/", "/static"))]) >= len([r for r in ROUTES if r[0].startswith(("/api/", "/static"))])
    assert 413 in app.error_handler_spec[None]            # 413（大きすぎる）の処理も残っている


def test_routes_is_a_package_with_four_groups():
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "routes", "*.py")))
    assert names == ["__init__.py", "api_assist.py", "api_translate.py", "pages.py", "pwa.py", "system.py"]
    assert not os.path.exists(os.path.join(ROOT, "routes.py"))
    for p in glob.glob(os.path.join(ROOT, "routes", "*.py")):
        assert len(open(p, encoding="utf-8").read().splitlines()) <= 200, p   # 1ファイルが長くなりすぎない


def test_translator_keeps_every_public_name():
    """translator.xxx で今まで使っていた名前は、分けた後も同じ物が使える（呼ぶ側・テストの差し替えが壊れない）"""
    import gemini_errors, json_reply, prompts, translator
    same = {
        "TranslationError": gemini_errors, "classify_exception": gemini_errors, "_block_reason": gemini_errors,
        "_parse": json_reply, "_loads_object": json_reply, "clean_blocks": json_reply, "MAX_BLOCKS": json_reply,
        "SYSTEM_INSTRUCTION": prompts, "FORMALITY_HINTS": prompts, "VALID_FORMALITY": prompts, "PRON_HINT": prompts,
        "EXPLAIN_SYSTEM": prompts, "LABEL_SYSTEM": prompts, "ALT_SYSTEM": prompts, "OVERLAY_SYSTEM": prompts,
        "PDF_SYSTEM": prompts, "clean_formality": prompts,
    }
    for name, mod in same.items():
        assert getattr(translator, name) is getattr(mod, name), name
    for name in ("_call", "_generate", "_thinking_config", "_get_client", "_pdf_reader", "_pdf_slice", "pdf_page_count",
                 "translate_text", "translate_image", "translate_image_blocks", "translate_pdf_pages", "explain_text",
                 "translate_labels", "alternative_translations", "RETRY_WAIT", "ATTEMPTS", "MODEL", "FALLBACK_MODEL",
                 "PDF_MAX_PAGES", "PDF_MAX_BYTES", "PDF_CHUNK"):
        assert hasattr(translator, name), name


def test_translator_is_shorter_and_has_no_prompt_text():
    src = open(os.path.join(ROOT, "translator.py"), encoding="utf-8").read()
    assert len(src.splitlines()) <= 450
    assert "You are a translation engine" not in src and "You are an OCR" not in src   # 指示文は prompts.py にある
    p = open(os.path.join(ROOT, "prompts.py"), encoding="utf-8").read()
    assert "You are a translation engine" in p and "You are an OCR and translation engine" in p
