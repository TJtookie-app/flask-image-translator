"""v1.10.2: 電波がないとき（機内モード）に、保存済みのオフライン画面を出す。Web／ホーム画面のアプリは SW、Android の殻は起動画面から。"""
import os

from conftest import ROOT


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_version():
    import app as appmod
    assert tuple(int(x) for x in appmod.APP_VERSION.split(".")) >= (1, 10, 2)


def test_sw_falls_back_to_the_offline_page_only_for_a_failed_root_navigation(env):
    app, *_ = env
    js = app.test_client().get("/sw.js").get_data(as_text=True)
    nav = js.split("async function navigate")[1].split("async function cacheFirst")[0]
    online_branch = nav.split("!== 'offline') {")[1].split("\n  }\n")[0]
    assert "req.method === 'GET'" in online_branch and "u.pathname === '/'" in online_branch and "catch (e) { return offlinePage(); }" in online_branch
    assert "return fetch(req);" in nav                         # それ以外（POST・他の画面）は、今までどおり差し替えない


def test_android_launcher_goes_to_the_saved_offline_page_when_there_is_no_signal():
    h = _read("app-shell", "index.html")
    assert 'location.replace(TARGET + "offline")' in h
    assert h.count("goOffline();") == 2 and "navigator.onLine === false) { go();" not in h
    assert "http://" not in h and "cdn." not in h
