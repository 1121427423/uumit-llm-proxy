#!/usr/bin/env bash
# =============================================================================
# 素材获取脚本 —— 用 GitHub API 拉取本项目使用的免版权素材并校验
#   视频（Pexels 免费素材，转载仓库 sugianand/11planner）
#   音乐（FreePD / Kevin MacLeod，CC0 1.0；仓库 SoundSafari/CC0-1.0-Music）
# 依赖: gh (已登录) 或 curl+token；用法:
#   bash tools/fetch_assets.sh [目标目录]     # 默认 /tmp/foot 与 /tmp/music
# =============================================================================
set -euo pipefail
DEST_FOOT="${1:-/tmp/foot}"
DEST_MUSIC="${2:-/tmp/music}"
mkdir -p "$DEST_FOOT" "$DEST_MUSIC"

SPECS=(
  "sugianand/11planner|frontend/public/city/216-speed-night-city-cars.mp4|$DEST_FOOT/night_city_cars.mp4|73753c68b2aedc6b8920f22f255119b120f1fc9a97433727bfa13e6101436963"
  "sugianand/11planner|frontend/public/city/233-eagle-drone-roundabout.mp4|$DEST_FOOT/233-eagle-drone-roundabout.mp4|28437f6f64048b435467a4589d1b52398c5e681ad0846024ef928a63d92bd254"
  "sugianand/11planner|frontend/public/city/211-speed-city.mp4|$DEST_FOOT/211-speed-city.mp4|c524bb8e1eb3ad3ebe9d1d7ec74487d2d7a71da1126fb1497a063a62c2a23fa5"
  "SoundSafari/CC0-1.0-Music|freepd.com/Shenzhen Nightlife.mp3|$DEST_MUSIC/m_shenzhen.mp3|d341e5b295429e71ff78c96862f5dd6bd2aa06bab81cb66e9080bb583d764f96"
)

gh_get() { # repo path out
  local repo="$1" path="$2" out="$3"
  if command -v gh >/dev/null 2>&1; then
    local sha; sha=$(gh api "repos/$repo/contents/$path" --jq '.sha')
    gh api "repos/$repo/git/blobs/$sha" --jq '.content' | base64 -d > "$out"
  else
    echo "需要 gh CLI（已登录）或手动下载 $repo/$path"; return 1
  fi
}

for spec in "${SPECS[@]}"; do
  IFS='|' read -r repo path out expect <<< "$spec"
  echo "→ $repo : $path"
  gh_get "$repo" "$path" "$out"
  got=$(sha256sum "$out" | awk '{print $1}')
  if [ "$expect" != "PLACEHOLDER"* ] && [ "$got" != "$expect" ]; then
    echo "  ✗ 校验不一致：期望 $expect 实际 $got"; exit 1
  fi
  echo "  ✓ $(stat -c%s "$out") 字节  sha256=${got:0:16}…"
done
echo "素材就绪。横版：python3 build.py --stage all"
