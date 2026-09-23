#!/usr/bin/env python3
"""
「城市夜景」20 秒延时混剪 —— 可复现构建脚本
=================================================
素材（全部免版权）：
  视频 A : 216-speed-night-city-cars.mp4   —— 城市夜景车流（4K/60fps，Pexels 免费素材，可商用）
  视频 B : 233-eagle-drone-roundabout.mp4  —— 夜景俯瞰环岛航拍（DJI 实拍，Pexels 免费素材）
  视频 C : 211-speed-city.mp4              —— 街头车流拖尾（Pexels 免费素材）
  音乐   : Shenzhen Nightlife (freepd.com / Kevin MacLeod) —— CC0 1.0

流程：
  1. 音乐：截取 128 BPM 段落 → atempo 变速为精确 120 BPM → 用低频起音测量真实节拍周期并闭环修正 → 按拍点取 20 秒
  2. 视频：10 个镜头 × 2.000 秒（= 4 拍 = 1 小节），全部对齐到音乐的小节线 → 硬切
  3. 合成：调色 + 暗角 + 颗粒 + 半秒处白闪强调 + 音画合并，1920x1080 / 30fps / 精确 20.000s

用法: python3 build.py [--stage all|music|video|final]
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np

# ---------------------------------------------------------------- 路径
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("BUILD_WORKDIR", "/tmp/city_night_build")
SRC = os.environ.get("BUILD_SRCDIR", "/tmp/foot")
MUSIC_SRC = os.environ.get("BUILD_MUSIC", "/tmp/music/m_shenzhen.mp3")
OUT_MP4 = os.path.join(HERE, "city-night-timelapse-20s.mp4")


def find_exe(name: str) -> str:
    """按「环境变量 → PATH → 工具链安装目录 → 已知发行包位置」查找二进制。"""
    env = os.environ.get(name.upper())
    if env and os.path.exists(env):
        return env
    p = shutil.which(name)
    if p:
        return p
    toolchain = os.path.expanduser(f"~/.local/share/citynight/{name}")
    if os.path.exists(toolchain):
        return toolchain
    known = {
        "ffmpeg": (
            "/usr/local/lib/python3.11/dist-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2",
            "/tmp/npmtest/node_modules/@ffmpeg-installer/linux-x64/ffmpeg",
        ),
        "ffprobe": ("/tmp/npmtest/node_modules/@ffprobe-installer/linux-x64/ffprobe",),
    }[name]
    for cand in known:
        if os.path.exists(cand):
            return cand
    raise SystemExit(
        f"找不到 {name}。请先运行 `bash tools/install-toolchain.sh`，"
        f"或设置环境变量 {name.upper()}=<可执行文件路径>。")


FF = find_exe("ffmpeg")
FP = find_exe("ffprobe")

# ---------------------------------------------------------------- 参数
FPS = 30
W, H = 1920, 1080
TARGET_BPM = 120.0
BEAT = 60.0 / TARGET_BPM        # 0.5 s —— 切分的最小单位
BAR = 4 * BEAT                  # 2.0 s = 1 小节
SHOT = 2.0                      # 默认镜头长度（仅作参考值）

# 镜头表 v2： (源, 源起点秒, 播放倍速, 时长, 取景)
#   dur  : 1.0–3.5 s 的长短对比，制造张弛；全部是 0.5 s（=1 拍）的整数倍，
#          因此 9 个切点依旧全部落在节拍网格上（其中 t=10.0s 正好是闪烁强调点）。
#   zoom : (起始放大倍率, 结束放大倍率)；pan : 'l2r'/'r2l'/None
SHOTS = [
    # 1  A 城市全景 · 推近（基准镜头）
    dict(src="A", t=1.20, speed=1.60, dur=3.0, zoom=(1.00, 1.16), pan=None, cx=0.5, cy=0.5),
    # 2  B 航拍环岛 · 拉远 + 冷调
    dict(src="B", t=1.00, speed=1.30, dur=2.0, zoom=(1.24, 1.02), pan=None, cx=0.5, cy=0.5, tone="cool"),
    # 3  C 霓虹特写 · 水平镜像 + 高倍放大
    dict(src="C", t=0.30, speed=1.00, dur=1.5, zoom=(1.90, 2.02), pan=None, cx=0.42, cy=0.5,
         mirror=True, tone="warm"),
    # 4  B 左下区车灯细部 · 倒放 + 2.3× 特写（完全脱离环岛圆形构图）
    dict(src="B", t=6.20, speed=1.40, dur=2.0, zoom=(2.30, 2.45), pan=None, cx=0.18, cy=0.80,
         reverse=True, tone="cool"),
    # 5  A 车流局部 · 右→左横扫 + 冷调
    dict(src="A", t=10.20, speed=1.90, dur=1.5, zoom=(1.50, 1.50), pan="r2l", cx=0.5, cy=0.5,
         tone="cool"),
    # 6  C 街头宽景 · 拉远（与第 3 镜同源、尺度相反）
    dict(src="C", t=2.60, speed=1.05, dur=1.5, zoom=(1.15, 1.03), pan=None, cx=0.5, cy=0.5,
         tone="warm"),
    # 7  A 镜像 + 倒放 + 横扫（与第 10 镜的“镜像定窗拉远”在方向/运动/时间上全不同）
    dict(src="A", t=16.60, speed=1.70, dur=2.0, zoom=(1.40, 1.52), pan="l2r", cx=0.5, cy=0.5,
         mirror=True, reverse=True, tone="cool"),
    # 8  B 右上区高楼霓虹细部 · 2.15× 特写
    dict(src="B", t=13.20, speed=1.30, dur=1.5, zoom=(2.15, 2.35), pan=None, cx=0.84, cy=0.18,
         tone="warm"),
    # 9  C 最左取景窗 · 倒放 + 推近
    dict(src="C", t=4.20, speed=1.00, dur=1.5, zoom=(1.45, 1.56), pan=None, cx=0.22, cy=0.5,
         reverse=True),
    # 10 A 镜像 · 右侧窗口拉远（收尾）
    dict(src="A", t=18.90, speed=1.30, dur=3.5, zoom=(1.28, 1.02), pan=None, cx=0.68, cy=0.5,
         mirror=True),
]

DURS = [sh["dur"] for sh in SHOTS]
CUT_TIMES = [sum(DURS[:i]) for i in range(len(DURS))]     # 每个镜头起点（秒）
TOTAL = sum(DURS)                                          # 20.000 秒
N_SHOTS = len(SHOTS)
assert abs(TOTAL - 20.0) < 1e-9 and \
       all(abs(d / BEAT - round(d / BEAT)) < 1e-9 for d in DURS), \
    "镜头时长必须是 0.5s 的整数倍且总和为 20.000s"

SOURCES = {
    "A": os.path.join(SRC, "night_city_cars.mp4"),
    "B": os.path.join(SRC, "233-eagle-drone-roundabout.mp4"),
    "C": os.path.join(SRC, "211-speed-city.mp4"),
}

MUSIC_SECTION_START = 191.0     # 用于截取的能量最强的 20 秒段落附近
ATEMPO_ROUNDS = 3               # 节拍闭环修正轮数


# ---------------------------------------------------------------- 工具
def run(cmd, quiet=True):
    msg = " ".join(cmd) if isinstance(cmd, list) else cmd
    if not quiet:
        print("  $", msg[:200])
    r = subprocess.run(cmd, shell=isinstance(cmd, str),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode(errors="replace")[-4000:])
        raise SystemExit(f"命令失败: {msg[:300]}")
    return r


def probe(path, entries, allow_fail=False):
    """ffprobe 包装。allow_fail=True 时探测失败返回 None（用于断点续渲等容错场景）。"""
    try:
        r = run([FP, "-v", "error", "-show_entries", entries,
                 "-of", "json", path])
    except SystemExit:
        if allow_fail:
            return None
        raise
    return json.loads(r.stdout.decode())


def decode_audio(path, sr=22050):
    raw = run([FF, "-v", "error", "-i", path, "-ac", "1", "-ar", str(sr),
               "-f", "f32le", "-"]).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64), sr


def low_band_env(x, sr, lo=35, hi=150, hop=256, nfft=1024):
    """低频（底鼓/贝斯）能量包络。"""
    n = 1 + (len(x) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(n)[:, None]
    win = np.hanning(nfft)
    S = np.fft.rfft(x[idx] * win, axis=1)
    fr = np.fft.rfftfreq(nfft, 1 / sr)
    mask = ((fr >= lo) & (fr <= hi)).astype(float)
    y = np.fft.irfft(S * mask, axis=1)
    return np.sqrt((y ** 2).mean(axis=1)), sr / hop


def onset_env(x, sr, hop=256, nfft=1024):
    """宽带起音（音头）强度包络，用于整体节拍感知。"""
    n = 1 + (len(x) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(n)[:, None]
    win = np.hanning(nfft)
    S = np.abs(np.fft.rfft(x[idx] * win, axis=1))
    S = np.log1p(10 * S)
    flux = np.diff(S, axis=0)
    flux[flux < 0] = 0
    oe = flux.sum(axis=1)
    k = 64
    oe = np.maximum(oe - np.convolve(oe, np.ones(k) / k, mode="same"), 0)
    return oe, sr / hop


def measure_beat_period(x, sr, bpm_hint=(110, 140)):
    """在给定 BPM 范围内，用 0.01 BPM / 10 ms 网格搜索，找到让低频能量最强的
    节拍周期与相位，返回 (bpm, period, phase)。"""
    low, lfps = low_band_env(x, sr)
    onset, ofps = onset_env(x, sr)
    onset = onset / (onset.mean() + 1e-12)
    best = None
    for bpm in np.arange(*bpm_hint, 0.01):
        period = 60.0 / bpm
        # 相位用较粗步长定，再用细步长精修
        for coef in np.arange(0.0, period, 0.02):
            beats = np.arange(coef, len(low) / lfps - 1e-3, period)
            i = np.round(beats * lfps).astype(int)
            h = max(1, int(0.055 * lfps))
            lo = np.array([low[max(0, j - h):j + h + 1].max() for j in i])
            on = np.array([onset[max(0, j - h):j + h + 1].max() for j in i])
            score = lo.mean() * on.mean()
            if best is None or score > best[0]:
                best = (score, bpm, period, coef)
    _, bpm, period, phase = best
    return bpm, period, phase


def stretch_factor_fix(atempo_current, measured_period):
    """算出新的 atempo，使输出节拍周期精确等于 0.5 s。"""
    return atempo_current * (measured_period / BEAT)


# ---------------------------------------------------------------- 1. 音乐
def build_music():
    os.makedirs(WORK, exist_ok=True)
    bed = os.path.join(WORK, "bed.wav")
    # 首轮：固定 128 BPM 假设的粗略变速
    atempo = TARGET_BPM / 128.0
    for rnd in range(ATEMPO_ROUNDS):
        src = MUSIC_SRC
        ss = MUSIC_SECTION_START
        dur = 26.0
        chain = f"atempo={atempo:.9f}"
        if rnd > 0:
            # 用上一轮渲染结果的原速重采样，反复微调
            src = bed
            ss = 0.0
            dur = 26.0
            chain = f"atempo={atempo:.9f}"
        run([FF, "-y", "-v", "error", "-ss", f"{ss}", "-t", f"{dur}", "-i", src,
             "-af", chain, "-ar", "44100", "-ac", "2", bed])
        x, sr = decode_audio(bed)
        bpm, period, phase = measure_beat_period(x, sr)
        print(f"  [音乐] 第 {rnd + 1} 轮: atempo={atempo:.6f} -> 实测 {bpm:.3f} BPM "
              f"(周期 {period:.5f}s, 相位 {phase:.3f}s)")
        if abs(period - BEAT) < 0.0006:
            break
        atempo = stretch_factor_fix(atempo, period)

    # 在最优段落里挑 20 秒：让 10 次剪切全部落在最重的拍点上
    low, lfps = low_band_env(x, sr)
    onset, ofps = onset_env(x, sr)
    onset = onset / (onset.mean() + 1e-12)
    best = None
    cut_grid = np.array(CUT_TIMES)
    for start in np.arange(0.0, len(x) / sr - TOTAL - 0.05, 0.25):
        for off in np.arange(0.0, BEAT, 0.005):
            ts = start + off + cut_grid
            if ts[-1] > len(x) / sr - 0.01:
                break
            i_low = np.round(ts * lfps).astype(int)
            i_on = np.round(ts * ofps).astype(int)
            h = max(1, int(0.055 * lfps))
            lo = np.array([low[max(0, j - h):j + h + 1].max() for j in i_low])
            on = np.array([onset[max(0, j - h):j + h + 1].max() for j in i_on])
            rms = 20 * math.log10(np.sqrt(np.mean(x[int(start * sr):int((start + TOTAL) * sr)] ** 2)) + 1e-9)
            score = (lo.mean() * on.mean()) * (1.0 + 0.02 * (rms + 10))
            if best is None or score > best[0]:
                best = (score, start, off, lo.mean(), on.mean(), rms)
    _, start, off, lo_mean, on_mean, rms = best
    print(f"  [音乐] 段落起点 {start:.2f}s + 网格偏移 {off:.3f}s  "
          f"(低频能量 {lo_mean:.4f} / 起音 {on_mean:.3f} / RMS {rms:.1f} dBFS)")

    music = os.path.join(WORK, "music.m4a")
    af = (f"afade=t=in:st=0:d=0.20,"
          f"afade=t=out:st={TOTAL - 0.55:.3f}:d=0.55,"
          f"loudnorm=I=-14:TP=-1.5:LRA=11")
    run([FF, "-y", "-v", "error", "-ss", f"{start + off:.4f}", "-t", f"{TOTAL}",
         "-i", bed, "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", music])

    # 校验：最终音轨的节拍网格
    fx, fsr = decode_audio(music, 44100)
    bpm, period, phase = measure_beat_period(fx, fsr, bpm_hint=(118, 122))
    info = probe(music, "format=duration")
    print(f"  [音乐] 成品: {float(info['format']['duration']):.3f}s  "
          f"实测 {bpm:.2f} BPM / 周期 {period:.5f}s / 相位 {phase:.3f}s")
    return music


# ---------------------------------------------------------------- 2. 镜头
def src_fps(tag):
    info = probe(SOURCES[tag], "stream=width,height,r_frame_rate")
    st = info["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return st["width"], st["height"], float(num) / float(den)


def shot_filter(sh, tag):
    """生成单个镜头的 -vf 链。

    顺序：原生分辨率下做取景/运镜（zoompan）→ 变速 → 补帧/抽帧 → 输出 1080p。
    """
    sw, sh_, sfps = src_fps(tag)
    z0, z1 = sh["zoom"]
    n_in = max(2, int(round(sh["dur"] * sh["speed"] * sfps)))
    vf = []
    # 降重复手法（v3）：倒放 / 水平镜像 —— 同一素材由此派生出观感不同的“机位”
    if sh.get("reverse"):
        vf.append("reverse")
    if sh.get("mirror"):
        vf.append("hflip")
    moving = abs(z1 - z0) > 1e-6 or bool(sh.get("pan"))
    if not moving:
        # 纯静态：原生空间裁切后直接缩放到 1080p
        if z0 > 1.0005:
            cw = int(round(sw / z0) // 2) * 2
            ch = int(round(sh_ / z0) // 2) * 2
            cx = int(round((sw - cw) * sh["cx"]) // 2) * 2
            cy = int(round((sh_ - ch) * sh["cy"]) // 2) * 2
            vf.append(f"crop={cw}:{ch}:{cx}:{cy}")
        vf.append(f"scale={W}:{H}:flags=lanczos")
    else:
        zexpr = f"{z0:.6f}+({z1 - z0:.6f})*on/{n_in - 1}"
        if sh.get("pan"):
            span = sw - sw / z0
            if sh["pan"] == "l2r":
                xexpr = f"{span:.1f}*on/{n_in - 1}"
            else:
                xexpr = f"{span:.1f}-{span:.1f}*on/{n_in - 1}"
        elif abs(float(sh.get("cx", 0.5)) - 0.5) > 1e-6:
            # 推近/拉远时把取景窗口固定压向画面左/右侧（同一素材的“另一台机位”）
            xexpr = f"(iw-iw/zoom)*{float(sh['cx']):.4f}"
        else:
            xexpr = "iw/2-(iw/zoom/2)"
        yexpr = (f"(ih-ih/zoom)*{float(sh['cy']):.4f}"
                 if abs(float(sh.get("cy", 0.5)) - 0.5) > 1e-6
                 else "ih/2-(ih/zoom/2)")
        vf.append(f"zoompan=z='{zexpr}':d=1:x='{xexpr}':y='{yexpr}'"
                  f":s={W}x{H}:fps={FPS}")
    vf.append(f"setpts=PTS/{sh['speed']}")
    if sfps / sh["speed"] < 28.0:
        # 注：vsbmc=1 会慢 3 倍且对夜景下采样画质无可见收益，这里关掉
        vf.append(f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:"
                  f"me_mode=bidir:vsbmc=0")
    tone = sh.get("tone")
    if tone == "warm":
        vf.append("colorbalance=rm=0.030:gm=0.008:bm=-0.030")
    elif tone == "cool":
        vf.append("colorbalance=rm=-0.028:bm=0.038")
    # 末帧克隆补齐：源有效帧不够时用最后一帧顶到 dur*FPS，保证帧数精确（见 §9.1）
    vf.append(f"tpad=stop_mode=clone:stop_duration=0.5")
    vf.append(f"fps={FPS},setsar=1")
    return vf


def clip_ok(path, expect_frames):
    """断点续渲用：文件存在、能解码、且帧数正确才算可用（半截文件/被中断的片段会被丢弃）。"""
    if not os.path.exists(path) or os.path.getsize(path) < 4096:
        return False
    try:
        info = probe(path, "stream=nb_frames", allow_fail=True)
        return bool(info) and int(info["streams"][0]["nb_frames"]) == expect_frames
    except Exception:
        return False


def build_shots():
    os.makedirs(WORK, exist_ok=True)
    clip_dir = os.path.join(WORK, "clips")
    os.makedirs(clip_dir, exist_ok=True)
    resume = os.environ.get("BUILD_RESUME") == "1"
    files = []
    for idx, sh in enumerate(SHOTS):
        out = os.path.join(clip_dir, f"shot{idx:02d}.mp4")
        files.append(out)
        expect = int(round(sh["dur"] * FPS))
        if resume and clip_ok(out, expect):
            print(f"  [镜头 {idx + 1:02d}] 已存在且帧数正确（{expect} 帧），跳过")
            continue
        # 多取 0.4s 余量：保证 zoompan 变速后仍有足量真实帧，
        # 避免 tpad 克隆帧在切点前造成 1~3 帧“顿一下”。
        src_dur = sh["dur"] * sh["speed"] + 0.4
        vf = shot_filter(sh, sh["src"])
        cmd = [FF, "-y", "-v", "error",
               "-ss", f"{sh['t']}", "-t", f"{src_dur}",
               "-i", SOURCES[sh["src"]],
               "-an", "-vf", ",".join(vf),
               "-frames:v", str(int(round(sh["dur"] * FPS))),
               "-r", f"{FPS}",
               "-c:v", "libx264", "-preset", "medium", "-crf", "16",
               "-pix_fmt", "yuv420p", out]
        print(f"  [镜头 {idx + 1:02d}] {sh['dur']:.1f}s @ {CUT_TIMES[idx]:.1f}s "
              f"{sh['src']} t={sh['t']} 速度x{sh['speed']} {sh['pan'] or ''} "
              f"zoom={sh['zoom']}")
        run(cmd)
    return files


# ---------------------------------------------------------------- 3. 合成
def build_final(music):
    clips = [os.path.join(WORK, "clips", f"shot{i:02d}.mp4") for i in range(N_SHOTS)]
    lst = os.path.join(WORK, "clips.txt")
    with open(lst, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    concat = os.path.join(WORK, "video_concat.mp4")
    run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
         "-c", "copy", concat])

    # 白闪：把峰值放在第 10.0 s 那一刀上（第 6 个镜头起始）
    ACCENT = 10.0   # 强调点：落在第 6 刀的切点上（见 CUT_TIMES）
    flash = ("format=yuva420p,colorchannelmixer=aa=0.42,"
             f"fade=t=in:st={ACCENT - 0.06}:d=0.06:alpha=1,"
             f"fade=t=out:st={ACCENT}:d=0.14:alpha=1")
    vf = ("[0:v]scale=1920:1080,setsar=1,"
          "eq=contrast=1.09:saturation=1.18:gamma=1.04,"
          "colorlevels=rimin=0.035:gimin=0.035:bimin=0.035,"
          "vignette=angle=PI/5,"
          "noise=alls=4:allf=t+u,"
          "format=yuv420p[v0];"
          f"[1:v]{flash}[fl];"
          "[v0][fl]overlay=0:0:format=auto,"
          "fade=t=in:st=0:d=0.35,fade=t=out:st=19.45:d=0.55,"
          "format=yuv420p[vout]")
    rendered = os.path.join(WORK, "video_final.mp4")
    run([FF, "-y", "-v", "error", "-i", concat,
         "-f", "lavfi", "-i", f"color=c=white:s={W}x{H}:d={TOTAL}:r={FPS}",
         "-filter_complex", vf,
         "-map", "[vout]", "-t", f"{TOTAL}", "-r", f"{FPS}",
         "-c:v", "libx264", "-preset", "slow", "-crf", "19",
         "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", rendered])

    print("  [合成] 混流音视频 …")
    run([FF, "-y", "-v", "error", "-i", rendered, "-i", music,
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-t", f"{TOTAL}", "-movflags", "+faststart",
         "-metadata", "title=City Nights · 20s Timelapse Montage",
         "-metadata", "comment=Footage: Pexels royalty-free stock (github.com/sugianand/11planner). "
                      "Music: Shenzhen Nightlife by Kevin MacLeod (freepd.com, CC0 1.0)",
         OUT_MP4])
    return OUT_MP4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["all", "music", "video", "final"])
    args = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    music = os.path.join(WORK, "music.m4a")
    if args.stage in ("all", "music"):
        print("① 生成音乐床 …")
        music = build_music()
    if args.stage in ("all", "video"):
        print("② 渲染 10 个镜头 …")
        build_shots()
    if args.stage in ("all", "final"):
        print("③ 合成成片 …")
        out = build_final(music)
        info = probe(out, "format=duration,size,bit_rate")
        print(f"\n✅ 成片: {out}")
        print(f"   时长 {float(info['format']['duration']):.3f}s  "
              f"大小 {int(info['format']['size']) / 1e6:.2f} MB  "
              f"码率 {int(info['format']['bit_rate']) / 1e6:.2f} Mbps")


if __name__ == "__main__":
    main()
