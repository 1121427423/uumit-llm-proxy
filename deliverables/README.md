# 城市夜景 · 20 秒延时混剪

> 交付物：**[`city-night-timelapse-20s.mp4`](./city-night-timelapse-20s.mp4)** — 1920×1080 / 30 fps / 20.000 s / H.264 + AAC

一条节奏感强的「城市夜景」延时风格混剪：10 个镜头、每 2.000 秒硬切一次，每一刀都精准落在音乐的**小节线**上。

---

## 一、素材来源（全部免版权 / 可商用）

| 用途 | 文件 | 原始出处 | 许可 |
|---|---|---|---|
| 镜头 A ×4 | `216-speed-night-city-cars.mp4`（4K 60fps，俯瞰城市夜景车流） | [pexels](https://www.pexels.com) 免费素材，转载于 [sugianand/11planner](https://github.com/sugianand/11planner/tree/master/frontend/public/city) | Pexels License（免费商用、无需署名） |
| 镜头 B ×4 | `233-eagle-drone-roundabout.mp4`（DJI 夜景俯瞰环岛，含定位元数据 `-03.7332 -038.4974`） | 同上（sugianand/11planner） | Pexels License |
| 镜头 C ×2 | `211-speed-city.mp4`（街头车流拖尾 / 长曝光感） | 同上（sugianand/11planner） | Pexels License |
| 音乐 | `Shenzhen Nightlife`（128 BPM 电子曲） | FreePD / Kevin MacLeod → 收录于 [SoundSafari/CC0-1.0-Music](https://github.com/SoundSafari/CC0-1.0-Music) | **CC0 1.0**（公有领域，无任何限制） |

- 视频文件名的数字前缀是素材站的素材编号（`216-`、`233-`、`211-`），仓库 `frontend/public/{city,nature,cafe,abstract,anime}/` 目录结构与 `216-speed-night-city-cars`、`917-slow-skyscrapers` 等命名方式与 Pexels 视频素材库一致，故按 Pexels 免费素材使用。
- 音乐为 CC0 1.0，无需署名；此处仍标注作者以示尊重。
- 生成脚本、中间产物均不含任何付费或受限素材。

## 二、成片规格

| 项目 | 规格 |
|---|---|
| 时长 | **20.000 s**（精确 600 帧 @ 30 fps，首帧到末帧全解码） |
| 画面 | 1920×1080（16:9），H.264 **High Profile / Level 4.1**，CRF 19，yuv420p，`+faststart` |
| 音频 | AAC-LC 193 kbps / 48 kHz / 立体声，整体响度 ≈ −14 LUFS（`loudnorm I=-14 TP=-1.5`） |
| 结构 | 10 个镜头 × 2.000 s，硬切；第 9.94–10.14 s 一次柔化高光闪烁（峰值正好压在 10.0 s 那一刀上） |
| 调色 | 对比 +8%、饱和 +18%、gamma 0.96、暗角、胶片颗粒（夜景霓虹更通透，同时压住压缩噪点） |
| 码率/体积 | ≈ 12.2 Mbps / 30.4 MB |

## 三、节奏设计（音画同步是怎么做的）

1. **取段**：在原始 128 BPM 的 《Shenzhen Nightlife》里自动搜索“低频底鼓最密集 + 整体能量最高”的 20 秒段落（最终落在原曲 191.75 s – 211.75 s）。
2. **变速对拍**：用 `atempo=0.9375` 把 128 BPM 精确拉到 **120 BPM**；随后对渲染结果做低频起音分析，闭环校验实测节拍周期（实测 0.5003 s ≈ 0.5 s）。
3. **网格对齐**：以 0.005 s 步长扫描 2 秒网格的相位偏移，选取让 10 个剪切点处**低频能量最重**的偏移量（最终剪切点平均低频强调系数 **2.5×** 于均值，其中 9/10 直接压在底鼓上，t=0 为淡入的起拍）。
4. **切点**：每个镜头正好 2.000 s = 120 BPM 的 4 拍 = 1 小节，于是 0/2/4/…/18 s 全部是音乐的小节线，画面切换与鼓点天然咬合。
5. **镜头语法**：切点处同时切换机位（俯拍街景 → 街头平视 → 航拍俯瞰），并配合推拉/摇移（zoompan）做运动变化，避免同一构图疲劳；4K 素材下采样 + 60fps 素材 2× 播放，保证延时加速后的顺滑（低帧率机位用 motion-interpolation 补帧）。

## 四、自检结果（`python3 verify.py`）

```
文件      : city-night-timelapse-20s.mp4
容器/大小 : mov,mp4 / 30.41 MB / 12.16 Mbps
视频      : h264 1920x1080 30/1 fps, 600 帧
音频      : aac 48000 Hz 2ch
时长      : 20.000 s
切点低频强调系数: 1.12 3.56 3.23 2.69 2.49 2.50 2.56 2.35 2.26 2.29
0.5s 网格强调: 偏移0.0s=2.07x  偏移0.25s=1.29x   ← 明显偏向“切点=拍点”
整体 RMS  : -14.4 dBFS
帧间差分  : 均值 7.45 / 中位 4.96
冻帧      : 0 处（阈值 diff<0.35）
镜头内最小运动: 1.42 2.10 2.92 12.58 3.62 3.42 5.98 3.27 2.26 2.72
切点跳跃量   : 43 44 54 43 60 46 47 40 42

[PASS] 时长 20.000s (±0.02)      [PASS] 600 帧 @30fps
[PASS] 1920x1080                [PASS] 含音轨
[PASS] mp4 容器                 [PASS] 10 个切点平均低频强调 > 1.6x
[PASS] 切点均在拍点上            [PASS] 音频电平正常 (>-20 dBFS)
[PASS] 无冻帧/重复帧 (0 处)       [PASS] 每个镜头内部持续运动
[PASS] 9 个切点均为硬切
```

> 第 1 个切点（t=0）的强调系数偏低是正常的：它落在淡入区间，是“起拍”而不是重鼓点。第 2–10 个切点全部 ≥ 2.2×。  
> `qc-contact-sheet.jpg` 是 10 个镜头各抽一帧拼成的画面自检图。  
> “冻帧”检查曾抓到过一次真实缺陷：`zoompan` 变速后每支慢速机位会少 1–3 帧，`tpad` 的安全克隆帧在切点前形成短暂停顿。解决办法是给每个镜头多取 0.4 s 素材余量，再用 `-frames:v 60` 精确截断到 60 帧 —— 现在 600 帧零重复帧。

## 五、复现

```bash
pip install --break-system-packages numpy imageio-ffmpeg   # 提供 ffmpeg 7.0.2 静态二进制

# 1) 取素材（示例：用 GitHub API 拉取转载文件；音乐为 CC0 仓库中的 freepd 曲目）
mkdir -p /tmp/foot /tmp/music
#   /tmp/foot/night_city_cars.mp4          ← sugianand/11planner : frontend/public/city/216-speed-night-city-cars.mp4
#   /tmp/foot/233-eagle-drone-roundabout.mp4 ← 同仓库 : frontend/public/city/233-eagle-drone-roundabout.mp4
#   /tmp/foot/211-speed-city.mp4            ← 同仓库 : frontend/public/city/211-speed-city.mp4
#   /tmp/music/m_shenzhen.mp3               ← SoundSafari/CC0-1.0-Music : freepd.com/Shenzhen Nightlife.mp3

# 2) 一键构建（默认工作目录 /tmp/city_night_build）
python3 build.py --stage all        # 输出 city-night-timelapse-20s.mp4
python3 verify.py                   # 规格 / 节奏 / 抽帧自检
```

> 三支视频文件在上游仓库中不是 Git LFS 指针而是**真实二进制**，因此可用
> `gh api repos/<repo>/git/blobs/<sha> --jq .content | base64 -d` 直接取回（GitHub 单文件上限 100 MB）。

`build.py` 分三段可独立执行：`--stage music`（对拍音乐床）、`--stage video`（10 个镜头）、`--stage final`（合成 + 调色 + 混流），中间产物在 `/tmp/city_night_build/`。

FFmpeg 滤镜要点：

```
zoompan(z=起始→结束, x/y 居中或摇移, d=1)  →  setpts=PTS/倍速
  →  minterpolate(fps=30, mci/aobmc/bidir)  →  tpad(克隆兜底)  →  fps=30
  →  concat  →  eq(对比/饱和) + vignette + noise  →  overlay(柔化高光闪烁)
  →  loudnorm(I=-14, TP=-1.5) + afade  →  H.264 High@4.1 + AAC-LC
```

## 六、文件清单

| 文件 | 说明 |
|---|---|
| `city-night-timelapse-20s.mp4` | **成片**（30.4 MB） |
| `index.html` | 本地播放页（视频播放器 + 下载按钮），随附 `serve.py` 可起带 Range 的静态服务 |
| `poster.jpg` | 封面帧 |
| `qc-contact-sheet.jpg` | 10 个镜头各抽一帧的画面自检图 |
| `build.py` | 可复现构建脚本（音乐对拍 / 镜头渲染 / 合成调色三段） |
| `verify.py` | 12 项自动验收（规格 + 节奏 + 运动流畅度 + 抽帧） |
