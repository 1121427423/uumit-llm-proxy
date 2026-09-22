#!/usr/bin/env python3
"""
「城市夜景」20 秒延时混剪 —— 可复现构建脚本
=================================================
素材（全部免版权）：
  视频 A : 216-speed-night-city-cars.mp4   —— 城市夜景车流（4K/60fps，pixabay 授权素材，CC0 兼容）
  视频 B : 233-eagle-drone-roundabout.mp4  —— 夜景俯瞰环岛航拍（DJI 实拍，pixabay 授权素材）
  视频 C : 211-speed-city.mp4              —— 街头车流拖尾（pixabay 授权素材）
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
    env = os.environ.get(name.upper())
    if env and os.path.exists(env):
        return env
    p = shutil.which(name)
    if p:
        return p
    for cand in (
        "/usr/local/lib/python3.11/dist-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2",
        "/tmp/npmtest/node_modules/@ffmpeg-installer/linux-x64/ffmpeg",
    ):
        if name == "ffmpeg" and os.path.exists(cand):
            return cand
    for cand in ("/tmp/npmtest/node_modules/@ffprobe-installer/linux-x64/ffprobe",):
        if name == "ffprobe" and os.path.exists(cand):
            return cand
    raise SystemExit(f"找不到 {name}")


FF = find_exe("ffmpeg")
FP = find_exe("ffprobe")

# ---------------------------------------------------------------- 参数
FPS = 30
W, H = 1920, 1080
SHOT = 2.0                      # 每个镜头 2.000 秒 = 120 BPM 的 4 拍 = 1 小节
N_SHOTS = 10
TOTAL = SHOT * N_SHOTS          # 20.000 秒
TARGET_BPM = 120.0
BEAT = 60.0 / TARGET_BPM        # 0.5 s
BAR = 4 * BEAT                  # 2.0 s

# 镜头表： (源, 源起点秒, 播放倍速, 取景)
#   zoom : (起始放大倍率, 结束放大倍率)；pan : 'l2r'/'r2l'/None
SHOTS = [
    dict(src="B", t=0.40, speed=1.30, zoom=(1.00, 1.07), pan=None, cx=0.5, cy=0.5),
    dict(src="A", t=0.50, speed=2.00, zoom=(1.00, 1.00), pan=None, cx=0.5, cy=0.5),
    dict(src="C", t=0.20, speed=1.00, zoom=(1.15, 1.15), pan=None, cx=0.5, cy=0.5),
    dict(src="B", t=5.60, speed=1.40, zoom=(1.45, 1.45), pan="l2r", cx=0.5, cy=0.5),
    dict(src="A", t=9.00, speed=2.20, zoom=(1.10, 1.22), pan=None, cx=0.5, cy=0.5),
    dict(src="C", t=3.60, speed=1.10, zoom=(1.30, 1.30), pan=None, cx=0.56, cy=0.5),
    dict(src="A", t=14.60, speed=1.80, zoom=(1.35, 1.35), pan="r2l", cx=0.5, cy=0.5),
    dict(src="B", t=11.40, speed=1.35, zoom=(1.28, 1.06), pan=None, cx=0.5, cy=0.5),
    dict(src="A", t=19.20, speed=2.20, zoom=(1.02, 1.08), pan=None, cx=0.5, cy=0.5),
    dict(src="B", t=16.40, speed=1.50, zoom=(1.18, 1.00), pan=None, cx=0.5, cy=0.5),
]

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


def probe(path, entries):
    r = run([FP, "-v", "error", "-show_entries", entries,
             "-of", "json", path])
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
    for start in np.arange(0.0, len(x) / sr - TOTAL - 0.05, 0.25):
        for off in np.arange(0.0, BAR, 0.005):
            ts = start + off + BAR * np.arange(N_SHOTS)
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
          f"afade=t=out:st={TOTAL - 0.45:.3f}:d=0.45,"
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
    n_in = max(2, int(round(SHOT * sh["speed"] * sfps)))
    vf = []
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
        else:
            xexpr = "iw/2-(iw/zoom/2)"
        vf.append(f"zoompan=z='{zexpr}':d=1:x='{xexpr}':y='ih/2-(ih/zoom/2)'"
                  f":s={W}x{H}:fps={FPS}")
    vf.append(f"setpts=PTS/{sh['speed']}")
    if sfps / sh["speed"] < 28.0:
        vf.append(f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:"
                  f"me_mode=bidir:vsbmc=1")
    # 末帧克隆补齐，保证每个镜头都是精确的 60 帧 / 2.000 s
    vf.append(f"tpad=stop_mode=clone:stop_duration=0.5")
    vf.append(f"fps={FPS},setsar=1")
    return vf


def build_shots():
    os.makedirs(WORK, exist_ok=True)
    clip_dir = os.path.join(WORK, "clips")
    os.makedirs(clip_dir, exist_ok=True)
    files = []
    for idx, sh in enumerate(SHOTS):
        out = os.path.join(clip_dir, f"shot{idx:02d}.mp4")
        files.append(out)
        # 多取 0.4s 余量：保证 zoompan 变速后仍有 ≥60 个真实帧，
        # 避免 tpad 克隆帧在切点前造成 1~3 帧“顿一下”。
        src_dur = SHOT * sh["speed"] + 0.4
        vf = shot_filter(sh, sh["src"])
        cmd = [FF, "-y", "-v", "error",
               "-ss", f"{sh['t']}", "-t", f"{src_dur}",
               "-i", SOURCES[sh["src"]],
               "-an", "-vf", ",".join(vf),
               "-frames:v", str(int(round(SHOT * FPS))),
               "-r", f"{FPS}",
               "-c:v", "libx264", "-preset", "medium", "-crf", "16",
               "-pix_fmt", "yuv420p", out]
        print(f"  [镜头 {idx + 1:02d}] {sh['src']} t={sh['t']} 速度x{sh['speed']} "
              f"{sh['pan'] or ''} zoom={sh['zoom']}")
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
    flash = ("format=yuva420p,colorchannelmixer=aa=0.42,"
             "fade=t=in:st=9.94:d=0.06:alpha=1,fade=t=out:st=10.0:d=0.14:alpha=1")
    vf = ("[0:v]scale=1920:1080,setsar=1,"
          "eq=contrast=1.08:saturation=1.18:gamma=0.96:brightness=-0.010,"
          "vignette=angle=PI/5,"
          "noise=alls=4:allf=t+u,"
          "format=yuv420p[v0];"
          f"[1:v]{flash}[fl];"
          "[v0][fl]overlay=0:0:format=auto,format=yuv420p[vout]")
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
         "-metadata", "comment=Footage: pixabay royalty-free stock (github.com/sugianand/11planner). "
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
