"""Android の殻（npx cap add android で作られる android/ フォルダ）に、このアプリに必要な設定を足すツール。

  python tools/android_patch.py          許可（カメラ・マイク・位置情報）を AndroidManifest.xml に足し、対象 API を確認する
  python tools/android_patch.py --check  何も書き換えず、足りないものがないかだけ確認する（足りなければ終了コード 1）

何度実行しても同じ結果になります（足りないものだけを足します）。"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "android", "app", "src", "main", "AndroidManifest.xml")
VARIABLES = os.path.join(ROOT, "android", "variables.gradle")
MIN_TARGET_SDK = 36   # Google Play は、2026年8月31日から新規・更新アプリに API 36（Android 16）以上を求める

PERMISSIONS = [
    "android.permission.INTERNET",
    "android.permission.CAMERA",
    "android.permission.RECORD_AUDIO",
    "android.permission.MODIFY_AUDIO_SETTINGS",
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.ACCESS_FINE_LOCATION",
]
# 端末にカメラやマイクがなくても入れられるように、必須にはしない
FEATURES = [
    "android.hardware.camera",
    "android.hardware.microphone",
    "android.hardware.location",
]


def missing(xml):
    perms = [p for p in PERMISSIONS if f'android:name="{p}"' not in xml]
    feats = [f for f in FEATURES if f'android:name="{f}"' not in xml]
    return perms, feats


def patch_manifest(xml):
    """足りない <uses-permission> と <uses-feature> を、</manifest> の直前に足して返す"""
    perms, feats = missing(xml)
    if not perms and not feats:
        return xml
    lines = [f'    <uses-permission android:name="{p}" />' for p in perms]
    lines += [f'    <uses-feature android:name="{f}" android:required="false" />' for f in feats]
    block = "\n".join(lines) + "\n"
    i = xml.rfind("</manifest>")
    if i < 0:
        raise ValueError("AndroidManifest.xml に </manifest> が見つかりません")
    return xml[:i] + block + xml[i:]


def target_sdk(text):
    m = re.search(r"targetSdkVersion\s*=\s*(\d+)", text)
    return int(m.group(1)) if m else None


def run(argv):
    check_only = "--check" in argv
    if not os.path.exists(MANIFEST):
        print("android/ フォルダが見つかりません。先に  npm run android:add  （または npx cap add android）を実行してください。")
        return 2
    with open(MANIFEST, encoding="utf-8") as f:
        xml = f.read()
    perms, feats = missing(xml)
    code = 0
    if perms or feats:
        if check_only:
            print("足りない設定: " + ", ".join(perms + feats))
            code = 1
        else:
            with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
                f.write(patch_manifest(xml))
            print(f"AndroidManifest.xml に {len(perms)} 件の許可と {len(feats)} 件の機能指定を足しました。")
    else:
        print("AndroidManifest.xml: 許可の設定は、すべて入っています。")
    if os.path.exists(VARIABLES):
        with open(VARIABLES, encoding="utf-8") as f:
            sdk = target_sdk(f.read())
        if sdk is None:
            print("targetSdkVersion を読み取れませんでした（android/variables.gradle を見てください）。")
        elif sdk < MIN_TARGET_SDK:
            print(f"targetSdkVersion が {sdk} です。{MIN_TARGET_SDK} 以上にしてください（Google Play の条件）。")
            code = 1
        else:
            print(f"targetSdkVersion: {sdk}（{MIN_TARGET_SDK} 以上で OK）")
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(run(sys.argv[1:]))
