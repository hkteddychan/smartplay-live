"""Build the layer-level driver APK without Gradle.

javac -> d8 -> aapt2 -> zip -> zipalign -> apksigner -> adb install

Usage:
    python driver/build.py            # build + install + start
    python driver/build.py --install-only
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
SDK = Path(os.environ.get("ANDROID_HOME") or
           Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk")
BT = SDK / "build-tools" / "34.0.0"
ANDROID_JAR = SDK / "platforms" / "android-34" / "android.jar"
PKG = "com.opencode.pgodrive"
OUT = ROOT / "build"
KEYSTORE = ROOT / "debug.keystore"


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(f"failed: {cmd[0]}")
    return r.stdout


def ensure_keystore():
    if KEYSTORE.exists():
        return
    run(["keytool", "-genkeypair", "-v", "-keystore", str(KEYSTORE),
         "-storepass", "android", "-keypass", "android", "-alias", "pgdrive",
         "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
         "-dname", "CN=pgdrive, OU=dev, O=opencode, L=HK, ST=HK, C=HK"])


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "classes").mkdir(parents=True)
    (OUT / "gen").mkdir(parents=True)

    # 1. compile java
    srcs = sorted(str(p) for p in (ROOT / "java").rglob("*.java"))
    run(["javac", "-nowarn", "-source", "11", "-target", "11",
         "-classpath", str(ANDROID_JAR),
         "-d", str(OUT / "classes"), *srcs])

    # 2. dex
    dex_files = list((OUT / "classes").rglob("*.class"))
    run([str(BT / "d8.bat"), "--min-api", "28", "--lib", str(ANDROID_JAR),
         "--output", str(OUT), *dex_files])

    # 3. resources + manifest -> apk
    run([str(BT / "aapt2.exe"), "compile", "--dir", str(ROOT / "res"),
         "-o", str(OUT / "res.zip")]) if (ROOT / "res").exists() else None

    apkz = OUT / "base.apk"
    run([str(BT / "aapt2.exe"), "link",
         "-I", str(ANDROID_JAR),
         "--manifest", str(ROOT / "AndroidManifest.xml"),
         "-o", str(apkz)])

    # 4. add classes.dex
    with zipfile.ZipFile(apkz, "a") as z:
        z.write(OUT / "classes.dex", "classes.dex")

    # 5. align + sign
    aligned = OUT / "aligned.apk"
    run([str(BT / "zipalign.exe"), "-f", "4", str(apkz), str(aligned)])
    ensure_keystore()
    signed = OUT / "pgdrive.apk"
    run([str(BT / "apksigner.bat"), "sign", "--ks", str(KEYSTORE),
         "--ks-pass", "pass:android", "--key-pass", "pass:android",
         "--ks-key-alias", "pgdrive", "--out", str(signed), str(aligned)])
    print(f"[build] {signed}")
    return signed


def install(apk: Path):
    run(["adb", "-s", "1bbd5689", "install", "-r", "-g", str(apk)])


def start():
    run(["adb", "-s", "1bbd5689", "shell", "am", "instrument", "-w",
         "-e", "nop", "0", f"{PKG}/{PKG}.Driver"])


if __name__ == "__main__":
    apk = build()
    if "--install-only" not in sys.argv:
        install(apk)
        print("[build] installed")
