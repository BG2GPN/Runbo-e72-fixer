#!/bin/bash
# 构建 placeholder.apk（授权引导组件，包名 runbo.android.poc）
#
# 需要的环境（可通过环境变量覆盖）:
#   BT     Android SDK build-tools 目录（含 aapt2.exe / zipalign.exe / apksigner.bat）
#   AJAR   android.jar 路径（platforms/android-xx/android.jar）
#   JHOME  JDK/JRE 17 目录
#   SMALI  smali-fat.jar 路径
#   KS     签名用的 keystore（缺省会自动生成 debug.keystore）
set -e
BT="${BT:-/d/Android SDK/build-tools/36.0.0}"
AJAR="${AJAR:-/d/Android SDK/platforms/android-33/android.jar}"
JHOME="${JHOME:-$(dirname "$(command -v java)")/..}"
SMALI="${SMALI:-$HOME/smali-fat.jar}"
KS="${KS:-debug.keystore}"
KSPASS="${KSPASS:-android}"
cd "$(dirname "$0")"

rm -rf dexout build && mkdir -p dexout build

echo "[1/5] aapt2 link"
"$BT/aapt2.exe" link -o build/base.apk -I "$AJAR" --manifest AndroidManifest.xml \
    --min-sdk-version 24 --target-sdk-version 26

echo "[2/5] smali -> dex"
java -jar "$SMALI" a smali -o dexout/classes.dex --api 26

echo "[3/5] 组装 apk"
python - <<'PY'
import zipfile, shutil, os
shutil.copy('build/base.apk', 'build/unsigned.apk')
with zipfile.ZipFile('build/unsigned.apk', 'a', zipfile.ZIP_DEFLATED) as z:
    z.write('dexout/classes.dex', 'classes.dex')
print('  dex added:', os.path.getsize('dexout/classes.dex'), 'bytes')
PY

echo "[4/5] zipalign"
"$BT/zipalign.exe" -f 4 build/unsigned.apk build/aligned.apk

echo "[5/5] apksigner 签名"
if [ ! -f "$KS" ]; then
    keytool -genkeypair -keystore "$KS" -alias androiddebugkey \
        -keyalg RSA -keysize 2048 -validity 10000 \
        -storepass "$KSPASS" -keypass "$KSPASS" \
        -dname "CN=Android Debug,O=Android,C=US"
fi
"$BT/apksigner.bat" sign --ks "$KS" --ks-pass "pass:$KSPASS" --key-pass "pass:$KSPASS" \
    --out placeholder.apk build/aligned.apk
"$BT/apksigner.bat" verify placeholder.apk && echo "OK -> placeholder.apk"
