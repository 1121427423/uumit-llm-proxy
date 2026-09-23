# 工具链（tools/）

本项目**不依赖系统 ffmpeg**（沙箱的 apt 源里没有 ffmpeg），全部二进制来自可安装包，并固化在本目录。

## 内容

| 文件 | 说明 |
|---|---|
| `packages/imageio_ffmpeg-0.6.0-py3-none-manylinux2014_x86_64.whl` | **软件安装包**（28.1 MB）：内含 `ffmpeg 7.0.2-static` 二进制 |
| `toolchain.lock.json` | 版本与 **sha256 校验和** 锁文件（含未入库的 ffprobe 包） |
| `install-toolchain.sh` | 一键安装 + 校验（离线优先用仓库内 wheel） |
| `fetch_assets.sh` | 一键获取全部免版权素材（3 支视频 + 1 首 CC0 音乐）并逐个校验 sha256 |

## 安装

```bash
bash tools/install-toolchain.sh
# 产物：
#   ~/.local/share/citynight/ffmpeg     <- 7.0.2-static
#   ~/.local/share/citynight/ffprobe    <- 5.2.0-static
```

安装脚本会：
1. 优先从仓库内 wheel 解出 ffmpeg（**离网可用**），否则回退 `pip install imageio-ffmpeg==0.6.0`；
2. 从 npm registry 下载 `@ffprobe-installer/linux-x64 5.2.0`（29 MB，因体积未入库）并用锁文件里的 sha256 校验；
3. 检查 numpy；
4. 校验解出的可执行文件 sha256。

## 在构建脚本中使用

`build.py` / `verify.py` / `review_agent.py` 按以下顺序查找二进制：

1. 环境变量 `FFMPEG` / `FFPROBE`
2. `PATH` 中的同名命令
3. 已知的 pip/npm 安装位置（本沙箱使用）

所以只要：

```bash
export FFMPEG=~/.local/share/citynight/ffmpeg
export FFPROBE=~/.local/share/citynight/ffprobe
cd .. && python3 build.py --stage all && python3 verify.py
```

## 校验和（与 toolchain.lock.json 一致）

```
wheel              c7e46fcec401dd990405049d2e2f475e2b397779df2519b544b8aab515195282
解出的 ffmpeg      e7e7fb30477f717e6f55f9180a70386c62677ef8a4d4d1a5d948f4098aa3eb99
ffprobe 包(tgz)    8b6b2e34bad5ea7cfbe1914185145f514f620f24203a1a421e8d00a698bf8e61
解出的 ffprobe     576c21674291ec1948d507ea8ab0d78eb6621a0be8c6f1a6db0f50c5fcb1e0f9
```

## 为什么 ffprobe 的安装包没有入库？

视频成片占 63 MB，平台单次快照预算约 128 MB；再加 29 MB 会逼近上限。ffmpeg（真正决定“能不能把片子编出来”的那一个）已入库保证离网可构建。

`ffprobe` 用于**探测与校验**（`verify.py` / `review_agent.py` / `build.py` 的素材探测），是 QC 环节的硬依赖——因此在没有网络的环境里请手动放入离线包：

```bash
cp ffprobe-installer-linux-x64-5.2.0.tgz ~/.local/share/citynight/
bash tools/install-toolchain.sh          # 会用锁文件里的 sha256 校验后解包
```

`build.py` 的查找顺序为：`$FFMPEG/$FFPROBE` → `PATH` → `~/.local/share/citynight/` → 已知发行包位置。

## 素材获取（fetch_assets.sh）

```bash
bash tools/fetch_assets.sh                 # 默认 → /tmp/foot 与 /tmp/music
bash tools/fetch_assets.sh 素材目录 音乐目录   # 自定义落盘位置
```

走 `api.github.com` 的 blobs 接口（raw 域名在受限网络下不可达），每个文件下载后与脚本内固化的 sha256 比对，
不匹配立即报错退出。实测结果：

```
216-speed-night-city-cars.mp4   78,957,165 B  73753c68b2aedc6b…
233-eagle-drone-roundabout.mp4  30,613,178 B  28437f6f64048b43…
211-speed-city.mp4               4,249,788 B  c524bb8e1eb3ad3e…
Shenzhen Nightlife.mp3          10,659,995 B  d341e5b295429e71…
```

> 两首视频/音乐均免版权（Pexels License / CC0 1.0），可直接用于构建：`python3 build.py --stage all`。
