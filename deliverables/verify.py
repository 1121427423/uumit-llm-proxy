#!/usr/bin/env python3
"""成片自检：规格、节奏对齐、画面抽帧。"""
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build as B  # noqa: E402

OUT = os.path.join(HERE, "city-night-timelapse-20s.mp4")
SHEET = os.path.join(HERE, "qc-contact-sheet.jpg")


def main():
    ok = True
    info = B.probe(OUT, "format=duration,size,bit_rate,format_name:"
                        "stream=index,codec_name,codec_type,width,height,"
                        "r_frame_rate,nb_frames,sample_rate,channels")
    fmt = info["format"]
    v = [s for s in info["streams"] if s["codec_type"] == "video"][0]
    a = [s for s in info["streams"] if s["codec_type"] == "audio"][0]
    dur = float(fmt["duration"])
    frames = int(v["nb_frames"])
    print(f"文件      : {OUT}")
    print(f"容器/大小 : {fmt['format_name']} / {int(fmt['size'])/1e6:.2f} MB "
          f"/ {int(fmt['bit_rate'])/1e6:.2f} Mbps")
    print(f"视频      : {v['codec_name']} {v['width']}x{v['height']} "
          f"{v['r_frame_rate']} fps, {frames} 帧")
    print(f"音频      : {a['codec_name']} {a['sample_rate']} Hz "
          f"{a['channels']}ch")
    print(f"时长      : {dur:.3f} s")

    checks = [
        ("时长 20.000s (±0.02)", abs(dur - 20.0) <= 0.02),
        ("600 帧 @30fps", frames == 600),
        ("1920x1080", v["width"] == 1920 and v["height"] == 1080),
        ("含音轨", a["codec_type"] == "audio"),
        ("mp4 容器", "mp4" in fmt["format_name"]),
    ]

    # --- 节奏校验
    x, sr = B.decode_audio(OUT, 44100)
    low, lfps = B.low_band_env(x, sr)
    onset, ofps = B.onset_env(x, sr)
    onset = onset / (onset.mean() + 1e-12)
    emps = []
    for k in range(B.N_SHOTS):
        j = int(k * B.SHOT * lfps)
        h = int(0.06 * lfps)
        emps.append(low[max(0, j - h):j + h + 1].max() / low.mean())
    print("切点低频强调系数:", " ".join(f"{e:.2f}" for e in emps))
    beat_off = {}
    for off in (0.0, 0.25):
        idx = np.round(np.arange(off, dur - 0.05, 0.5) * lfps).astype(int)
        h = int(0.05 * lfps)
        beat_off[off] = np.mean([low[max(0, j - h):j + h + 1].max()
                                 for j in idx]) / low.mean()
    print(f"0.5s 网格强调: 偏移0.0s={beat_off[0.0]:.2f}x  "
          f"偏移0.25s={beat_off[0.25]:.2f}x  (应显著偏向前者 → 网格对齐)")
    checks += [
        ("10 个切点平均低频强调 > 1.6x", float(np.mean(emps)) > 1.6),
        ("切点均在拍点上 (0.5s 网格)",
         beat_off[0.0] > 1.5 * beat_off[0.25]),
    ]

    # --- 音频响度（近似）
    rms = 20 * math.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
    print(f"整体 RMS  : {rms:.1f} dBFS")
    checks.append(("音频电平正常 (>-20 dBFS)", rms > -20))

    # --- 运动流畅度：逐帧差分，确认没有冻帧（重复帧）且切点是硬切
    W2, H2 = 480, 270
    raw = subprocess.run([B.FF, "-v", "error", "-i", OUT, "-vf",
                          f"scale={W2}:{H2}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True).stdout
    n2 = len(raw) // (W2 * H2)
    fr = np.frombuffer(raw[:n2 * W2 * H2], dtype=np.uint8)\
        .reshape(n2, H2, W2).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    frozen = int((d < 0.35).sum())
    shot_min = [float(d[k * 60:(k + 1) * 60].min()) for k in range(B.N_SHOTS)]
    cut_jump = [float(d[k * 60 - 1]) for k in range(1, B.N_SHOTS)]
    print(f"帧间差分  : 均值 {d.mean():.2f} / 中位 {np.median(d):.2f}")
    print(f"冻帧      : {frozen} 处（阈值 diff<0.35）")
    print("镜头内最小运动:", " ".join(f"{m:.2f}" for m in shot_min))
    print("切点跳跃量   :", " ".join(f"{c:.0f}" for c in cut_jump))
    checks += [
        ("无冻帧/重复帧 (0 处)", frozen == 0),
        ("每个镜头内部持续运动 (最小 >0.5)", min(shot_min) > 0.5),
        ("9 个切点均为硬切 (跳跃 >20)", min(cut_jump) > 20),
    ]

    # --- 抽帧 contact sheet：每个镜头中段（第 36 帧 = 1.2s）各取一帧，5x2 拼图
    sel = f"select='eq(mod(n-{int(1.2 * B.FPS)},{int(B.SHOT * B.FPS)}),0)"\
          f"*gte(n,{int(1.2 * B.FPS)})'"
    r = subprocess.run([B.FF, "-y", "-v", "error", "-i", OUT,
                        "-vf", f"{sel},scale=480:-1,tile=5x2",
                        "-frames:v", "1", "-q:v", "3", SHEET],
                       capture_output=True)
    if r.returncode != 0:
        print("contact sheet 生成失败:", r.stderr.decode()[-500:])
        ok = False
    else:
        print(f"抽帧图    : {SHEET}")
        checks.append(("抽帧图生成", True))

    print("\n自检结果:")
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("\n" + ("全部通过 ✅" if ok else "存在未通过项 ❌"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
