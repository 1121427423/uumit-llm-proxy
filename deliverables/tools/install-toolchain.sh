#!/usr/bin/env bash
# =============================================================================
#  城市夜景混剪 · 工具链安装脚本
#  按 toolchain.lock.json 安装 ffmpeg / ffprobe / python 依赖，并校验 sha256。
#
#  用法：
#    bash tools/install-toolchain.sh              # 优先用仓库内自带的 wheel
#    bash tools/install-toolchain.sh --no-verify  # 跳过校验和比对（不建议）
#    FFMPEG_BIN=/path/to/ffmpeg FFPROBE_BIN=/path/to/ffprobe bash tools/install-toolchain.sh
#  安装后可用环境变量指定二进制位置：
#    export FFMPEG=$HOME/.local/share/citynight/ffmpeg
#    export FFPROBE=$HOME/.local/share/citynight/ffprobe
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
DEST="${TOOLCHAIN_DIR:-$HOME/.local/share/citynight}"
VERIFY=1
[[ "${1:-}" == "--no-verify" ]] && VERIFY=0

WHEEL="$HERE/packages/imageio_ffmpeg-0.6.0-py3-none-manylinux2014_x86_64.whl"
FFPROBE_TGZ_URL="https://registry.npmjs.org/@ffprobe-installer/linux-x64/-/linux-x64-5.2.0.tgz"

SHA_WHEEL="c7e46fcec401dd990405049d2e2f475e2b397779df2519b544b8aab515195282"
SHA_FFPROBE_TGZ="8b6b2e34bad5ea7cfbe1914185145f514f620f24203a1a421e8d00a698bf8e61"
SHA_FFMPEG_BIN="e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99"
SHA_FFPROBE_BIN="576c21674291ec1948d507ea8ab0d78eb6621a0be8c6f1a6db0f50c5fcb1e0f9"

say() { printf '\033[36m[toolchain]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[toolchain:error]\033[0m %s\n' "$*" >&2; exit 1; }

check_sha() {  # check_sha <file> <expected>
  [[ "$VERIFY" == "1" ]] || return 0
  local got; got="$(sha256sum "$1" | awk '{print $1}')"
  [[ "$got" == "$2" ]] || die "校验和不匹配：$1
   期望 $2
   实际 $got"
  say "校验通过 $(basename "$1")"
}

mkdir -p "$DEST"

# ---------------------------------------------------------------- ffmpeg
if [[ -n "${FFMPEG_BIN:-}" && -x "${FFMPEG_BIN}" ]]; then
  cp -f "$FFMPEG_BIN" "$DEST/ffmpeg"; say "使用已有 ffmpeg：$FFMPEG_BIN"
else
  # 1) 优先安装仓库自带的 wheel（离网可用）
  if [[ -f "$WHEEL" ]]; then
    check_sha "$WHEEL" "$SHA_WHEEL"
    say "从仓库自带 wheel 解出 ffmpeg …"
    python3 - "$WHEEL" "$DEST" <<'PY'
import sys, zipfile, os, stat, shutil
whl, dest = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(whl) as z:
    name = [n for n in z.namelist() if n.startswith("imageio_ffmpeg/binaries/ffmpeg-")][0]
    with z.open(name) as src, open(os.path.join(dest, "ffmpeg"), "wb") as out:
        shutil.copyfileobj(src, out)
os.chmod(os.path.join(dest, "ffmpeg"), 0o755)
print("  解出:", name)
PY
  # 2) 退而求其次：pip 安装 imageio-ffmpeg 后取其二进制
  else
    say "仓库不含 wheel，改用 pip 安装 imageio-ffmpeg==0.6.0 …"
    pip install --break-system-packages --quiet imageio-ffmpeg==0.6.0 \
      || pip install --quiet imageio-ffmpeg==0.6.0
    python3 -c "import imageio_ffmpeg,shutil,sys;shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(),sys.argv[1])" "$DEST/ffmpeg"
  fi
fi
chmod +x "$DEST/ffmpeg"
check_sha "$DEST/ffmpeg" "$SHA_FFMPEG_BIN"
"$DEST/ffmpeg" -version | head -1

# ---------------------------------------------------------------- ffprobe
if [[ -n "${FFPROBE_BIN:-}" && -x "${FFPROBE_BIN}" ]]; then
  cp -f "$FFPROBE_BIN" "$DEST/ffprobe"; say "使用已有 ffprobe：$FFPROBE_BIN"
else
  TGZ="$DEST/ffprobe-installer-linux-x64-5.2.0.tgz"
  if [[ ! -f "$TGZ" ]]; then
    say "下载 ffprobe 安装包（npm registry，29 MB）…"
    curl -fsSL "$FFPROBE_TGZ_URL" -o "$TGZ" \
      || die "下载失败；若网络受限，请手动把该 tgz 放到 $TGZ"
  fi
  check_sha "$TGZ" "$SHA_FFPROBE_TGZ"
  tar -xzf "$TGZ" -C "$DEST" package/ffprobe
  mv -f "$DEST/package/ffprobe" "$DEST/ffprobe" && rm -rf "$DEST/package"
fi
chmod +x "$DEST/ffprobe"
check_sha "$DEST/ffprobe" "$SHA_FFPROBE_BIN"
"$DEST/ffprobe" -version 2>&1 | head -1

# ---------------------------------------------------------------- python 依赖
say "安装 python 依赖（numpy）…"
python3 -c "import numpy" 2>/dev/null || \
  (pip install --break-system-packages --quiet numpy || pip install --quiet numpy)

# ---------------------------------------------------------------- 收尾
cat <<EOF

安装完成：
  ffmpeg  : $DEST/ffmpeg
  ffprobe : $DEST/ffprobe

在构建脚本中使用：
  export FFMPEG=$DEST/ffmpeg
  export FFPROBE=$DEST/ffprobe
  cd $ROOT && python3 build.py --stage all && python3 verify.py
EOF
