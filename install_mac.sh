#!/bin/bash
set -e

APP_NAME="sudaeng_pet.app"
ZIP_URL="https://github.com/todtnwater/sudang/releases/latest/download/sudaeng_pet_mac.zip"

echo "수댕이 설치를 시작합니다..."

if [ "$(uname -s)" != "Darwin" ]; then
    echo "맥에서만 실행할 수 있습니다."
    exit 1
fi

if [ "$(uname -m)" != "arm64" ]; then
    echo "Apple Silicon(M1 이상) 맥만 지원합니다. 인텔 맥은 지원하지 않습니다."
    exit 1
fi

if [ -w "/Applications" ]; then
    DEST="/Applications"
else
    DEST="$HOME/Applications"
    mkdir -p "$DEST"
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "다운로드 중..."
curl -fL --progress-bar -o "$TMP_DIR/sudaeng_pet_mac.zip" "$ZIP_URL"

pkill -f "$APP_NAME/Contents/MacOS/sudaeng_pet" 2>/dev/null || true
sleep 1

echo "설치 중..."
rm -rf "$DEST/$APP_NAME"
ditto -x -k "$TMP_DIR/sudaeng_pet_mac.zip" "$DEST"
xattr -cr "$DEST/$APP_NAME" 2>/dev/null || true

echo "설치 완료! 수댕이를 실행합니다."
echo "다음부터는 $DEST 폴더의 sudaeng_pet을 더블클릭하면 됩니다."
open "$DEST/$APP_NAME"
