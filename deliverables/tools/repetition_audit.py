#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重复度体检（repetition audit）—— 量化“成片里有多少镜头看起来像同一个画面”。

与 review/review_agent.py 的区别：
  · review_agent 看的是“相邻镜头差异”（剪辑是否单调）；
  · 本脚本看的是“任意两个镜头是否重复”（观众反馈的“重复度太高”正是这个）。
    它把每个镜头的中段帧缩略到 160×90 后两两比较，
    输出「高度重复镜头对」清单与重复度评分（0 = 十个镜头互不相同，100 = 全部雷同）。

判定口径：缩略图平均绝对差 MAD < 0.12 且 直方图 JS 散度 < 0.12 → 判为「看上去是同一个画面」。
重复度评分 = 重复对数 ÷ 总对数 × 100（10 个镜头 = 45 对）。

用法：
    python3 tools/repetition_audit.py city-night-timelapse-20s.mp4 [--json out.json]
    python3 tools/repetition_audit.py vertical/city-night-timelapse-9x16-20s.mp4
    python3 tools/repetition_audit.py xxx.mp4 --cuts "3,5,6.5,8.5,10,11.5,13.5,15,16.5"   # 已知切点时更准
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import shutil
import subprocess

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

W, H = 160, 90        # 比对用缩略图（分辨率越高越能检出真实差异）
THUMB_DUP = 0.12      # 缩略图平均绝对差 < 0.12 → 画面结构高度接近
HIST_DUP = 0.12       # 直方图 JS 散度 < 0.12 → 颜色分布也接近
#                      两者同时满足才判为“看上去是同一个画面”


def find_exe(name: str) -> str:
    for key in (f"{name.upper()}_BIN", name.upper()):
        env = os.environ.get(key)
        if env and os.path.exists(env):
            return env
    p = shutil.which(name)
    if p:
        return p
    local = os.path.join(HERE, "bin", name)
    if os.path.exists(local):
        return local
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    for cand in "/usr/local/lib/python3.11/dist-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2", \
                "/tmp/npm/node_modules/@ffprobe-installer/linux-x64/ffprobe", \
                "/tmp/node_modules/@ffprobe-installer/linux-x64/ffprobe":
        if os.path.exists(cand) and (name in os.path.basename(cand) or name == "ffmpeg"):
            return cand
    raise SystemExit(f"找不到 {name}")


FF = find_exe("ffmpeg")
FP = find_exe("ffprobe")

path_ref: list[str] = []          # 供 detect_cuts 读取路径
cut_times_override: list[float] = []


def probe_duration(path: str) -> float:
    out = subprocess.run(
        [FP, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True)
    return float(out.stdout.strip())


def detect_cuts() -> list[float]:
    """黑盒找切点：帧间差分的局部极大值，阈值 = max(中位数×3, 最大跳变×0.5)，最小间隔 0.5 s。"""
    raw = subprocess.run(
        [FF, "-v", "error", "-i", path_ref[0], "-vf",
         "fps=30,scale=240:136,format=gray", "-f", "rawvideo", "-"],
        capture_output=True).stdout
    n = len(raw) // (240 * 136)
    f = np.frombuffer(raw, dtype=np.uint8)[:n * 240 * 136].reshape(n, 136, 240).astype(np.float32)
    d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
    med = float(np.median(d))
    thr = max(med * 3.0, float(d.max()) * 0.5)
    cand = [int(i) + 1 for i in range(1, len(d) - 1)
            if d[i] >= thr and d[i] >= d[i - 1] and d[i] >= d[i + 1]]
    merged: list[int] = []
    for c in cand:
        if not merged or c - merged[-1] >= 15:
            merged.append(c)
    return [c / 30.0 for c in merged]


def jsd(p: np.ndarray, q: np.ndarray) -> float:
    m = (p + q) / 2

    def kl(a, b):
        mask = a > 0
        return float((a[mask] * np.log2(a[mask] / b[mask])).sum())

    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def audit(path: str) -> dict:
    path_ref.clear()
    path_ref.append(path)
    dur = probe_duration(path)
    cuts = cut_times_override or detect_cuts()
    bounds = [0.0] + cuts + [dur]
    shots = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)
             if bounds[i + 1] - bounds[i] > 0.3]

    thumbs, hists = [], []
    for (a, b) in shots:
        t = (a + b) / 2
        raw = subprocess.run(
            [FF, "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
             "-vf", f"scale={W}:{H}", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
            capture_output=True).stdout
        g = np.frombuffer(raw, dtype=np.uint8)[:W * H].reshape(H, W).astype(np.float32) / 255.0
        thumbs.append(g)
        h = np.histogram(g, bins=32, range=(0, 1))[0].astype(np.float32)
        hists.append(h / (h.sum() + 1e-9))

    pairs = []
    for i, j in itertools.combinations(range(len(thumbs)), 2):
        mad = float(np.abs(thumbs[i] - thumbs[j]).mean())
        dist = jsd(hists[i], hists[j])
        pairs.append(dict(i=i + 1, j=j + 1, thumb_mad=round(mad, 3),
                          hist_jsd=round(dist, 3),
                          duplicate=bool(mad < THUMB_DUP and dist < HIST_DUP)))
    n = len(thumbs)
    n_pairs = max(1, n * (n - 1) // 2)
    dup_pairs = [p for p in pairs if p["duplicate"]]
    score = round(100 * len(dup_pairs) / n_pairs, 1)
    worst = sorted(pairs, key=lambda p: p["thumb_mad"])[:5]
    return dict(video=os.path.relpath(path, ROOT), shots=n,
                shot_ranges=[[round(a, 2), round(b, 2)] for a, b in shots],
                n_pairs=n_pairs, duplicate_pairs=len(dup_pairs),
                repetition_score=score,
                mean_thumb_mad=round(float(np.mean([p["thumb_mad"] for p in pairs])), 3),
                mean_hist_jsd=round(float(np.mean([p["hist_jsd"] for p in pairs])), 3),
                most_similar=worst, duplicates=dup_pairs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?",
                    default=os.path.join(ROOT, "city-night-timelapse-20s.mp4"))
    ap.add_argument("--json", default=None)
    ap.add_argument("--cuts", default=None,
                    help="手动指定切点秒数（逗号分隔）；默认由帧间差分自动检测")
    args = ap.parse_args()

    if args.cuts:
        cut_times_override.extend(float(x) for x in args.cuts.split(",") if x.strip())

    res = audit(args.video)
    print(f"文件      : {res['video']}")
    print(f"检出镜头  : {res['shots']} 个  {res['shot_ranges']}")
    print(f"两两比对  : {res['n_pairs']} 对")
    print(f"重复度评分: {res['repetition_score']} / 100   (0=每个镜头都独一份，100=全部雷同)")
    print(f"平均差异  : 缩略图 MAD {res['mean_thumb_mad']}   直方图 JSD {res['mean_hist_jsd']}")
    print(f"高度重复对: {res['duplicate_pairs']} 对")
    for p in res["duplicates"]:
        print(f"   · 镜头{p['i']} ↔ 镜头{p['j']}  MAD={p['thumb_mad']}  JSD={p['hist_jsd']}")
    print("最相似的前 5 对（用于定位观感重复）:")
    for p in res["most_similar"]:
        mark = " ← 判为重复" if p["duplicate"] else ""
        print(f"   · 镜头{p['i']:2d} ↔ 镜头{p['j']:2d}  MAD={p['thumb_mad']:.3f}  "
              f"JSD={p['hist_jsd']:.3f}{mark}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"→ {os.path.relpath(args.json, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
