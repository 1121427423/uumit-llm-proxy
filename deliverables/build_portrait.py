#!/usr/bin/env python3
"""
「城市夜景」竖版 9:16 · 20 秒延时混剪
=================================================
与横版（build.py）共用同一套素材、同一条 120 BPM 音乐床、同一个 2.000 s 镜头节拍，
只把画布换成 1080x1920（抖音 / Reels / Shorts）并重排取景：
  · 源为 16:9，竖版一次只能吃到 9/16 的宽度，因此先按每支镜头的主体位置
    裁出 810x1440（1080p 源裁 608x1080）的竖窗口，再做推拉/摇移；
  · 摇移镜头在竖窗口内横扫，视觉冲击更强；
  · 音乐沿用横版已对好拍的 /tmp/city_night_build/music.m4a（缺失时自动重建）。

用法: python3 build_portrait.py
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build as B  # noqa: E402  复用 ffmpeg 定位、音频分析、音乐对拍等工具

W, H = 1080, 1920
OUT_DIR = os.path.join(HERE, "vertical")
WORK = os.environ.get("BUILD_WORKDIR_V", "/tmp/city_night_v")
OUT_MP4 = os.path.join(OUT_DIR, "city-night-timelapse-9x16-20s.mp4")

# px/py : 竖窗口在源画面中的位置（0=左/上，1=右/下）
PORTRAIT_SHOTS = [
    dict(src="B", t=0.40, speed=1.30, zoom=(1.00, 1.07), pan=None, px=0.50),
    dict(src="A", t=0.50, speed=2.00, zoom=(1.00, 1.00), pan=None, px=0.50),
    dict(src="C", t=0.20, speed=1.00, zoom=(1.15, 1.15), pan=None, px=0.50),
    dict(src="B", t=5.60, speed=1.40, zoom=(1.45, 1.45), pan="l2r", px=0.50),
    dict(src="A", t=9.00, speed=2.20, zoom=(1.10, 1.22), pan=None, px=0.46),
    dict(src="C", t=3.60, speed=1.10, zoom=(1.30, 1.30), pan=None, px=0.56),
    dict(src="A", t=14.60, speed=1.80, zoom=(1.35, 1.35), pan="r2l", px=0.50),
    dict(src="B", t=11.40, speed=1.35, zoom=(1.28, 1.06), pan=None, px=0.52),
    dict(src="A", t=19.20, speed=2.20, zoom=(1.02, 1.08), pan=None, px=0.50),
    dict(src="B", t=16.40, speed=1.50, zoom=(1.18, 1.00), pan=None, px=0.48),
]


def even(v):
    return int(round(v / 2)) * 2


def shot_filter(sh, tag):
    """竖版滤镜链：先在源上裁 9:16 竖窗口，再做 zoompan 推拉/摇移 → 1080x1920。"""
    sw, sh_, sfps = B.src_fps(tag)
    z0, z1 = sh["zoom"]
    win_w = even(sh_ * W / H)          # 源中 9:16 竖窗口的宽（A/B: 810, C: 608）
    x0 = min(max(even((sw - win_w) * sh.get("px", 0.5)), 0), sw - win_w)
    n_in = max(2, int(round(B.SHOT * sh["speed"] * sfps)))
    vf = [f"crop={win_w}:{sh_}:{x0}:0"]
    moving = abs(z1 - z0) > 1e-6 or bool(sh.get("pan"))
    if not moving:
        if z0 > 1.0005:
            cw, ch = even(win_w / z0), even(sh_ / z0)
            vf.append(f"crop={cw}:{ch}:{even((win_w - cw) / 2)}:{even((sh_ - ch) / 2)}")
        vf.append(f"scale={W}:{H}:flags=lanczos")
    else:
        zexpr = f"{z0:.6f}+({z1 - z0:.6f})*on/{n_in - 1}"
        if sh.get("pan"):
            span = win_w - win_w / z0
            xexpr = (f"{span:.1f}*on/{n_in - 1}" if sh["pan"] == "l2r"
                     else f"{span:.1f}-{span:.1f}*on/{n_in - 1}")
        else:
            xexpr = "iw/2-(iw/zoom/2)"
        vf.append(f"zoompan=z='{zexpr}':d=1:x='{xexpr}':y='ih/2-(ih/zoom/2)'"
                  f":s={W}x{H}:fps={B.FPS}")
    vf.append(f"setpts=PTS/{sh['speed']}")
    if sfps / sh["speed"] < 28.0:
        vf.append("minterpolate=fps=%d:mi_mode=mci:mc_mode=aobmc:"
                  "me_mode=bidir:vsbmc=1" % B.FPS)
    vf.append("tpad=stop_mode=clone:stop_duration=0.5")
    vf.append(f"fps={B.FPS},setsar=1")
    return vf


def build_shots():
    clip_dir = os.path.join(WORK, "clips")
    os.makedirs(clip_dir, exist_ok=True)
    for idx, sh in enumerate(PORTRAIT_SHOTS):
        out = os.path.join(clip_dir, f"shot{idx:02d}.mp4")
        vf = shot_filter(sh, sh["src"])
        print(f"  [竖直镜头 {idx + 1:02d}] {sh['src']} t={sh['t']} 速度x{sh['speed']} "
              f"{sh['pan'] or ''} zoom={sh['zoom']} px={sh.get('px')}")
        B.run([B.FF, "-y", "-v", "error",
               "-ss", f"{sh['t']}", "-t", f"{B.SHOT * sh['speed'] + 0.4}",
               "-i", B.SOURCES[sh["src"]],
               "-an", "-vf", ",".join(vf),
               "-frames:v", str(int(round(B.SHOT * B.FPS))),
               "-r", f"{B.FPS}",
               "-c:v", "libx264", "-preset", "medium", "-crf", "16",
               "-pix_fmt", "yuv420p", out])


def build_final(music):
    clips = [os.path.join(WORK, "clips", f"shot{i:02d}.mp4")
             for i in range(len(PORTRAIT_SHOTS))]
    lst = os.path.join(WORK, "clips.txt")
    with open(lst, "w") as f:
        for c in clips:
            f.write(f"file '{c}'\n")
    concat = os.path.join(WORK, "video_concat.mp4")
    B.run([B.FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
           "-c", "copy", concat])

    flash = ("format=yuva420p,colorchannelmixer=aa=0.42,"
             "fade=t=in:st=9.94:d=0.06:alpha=1,fade=t=out:st=10.0:d=0.14:alpha=1")
    vf = (f"[0:v]scale={W}:{H},setsar=1,"
          "eq=contrast=1.08:saturation=1.18:gamma=0.96:brightness=-0.010,"
          "vignette=angle=PI/5,"
          "noise=alls=4:allf=t+u,"
          "format=yuv420p[v0];"
          f"[1:v]{flash}[fl];"
          "[v0][fl]overlay=0:0:format=auto,format=yuv420p[vout]")
    rendered = os.path.join(WORK, "video_final.mp4")
    B.run([B.FF, "-y", "-v", "error", "-i", concat,
           "-f", "lavfi", "-i", f"color=c=white:s={W}x{H}:d={B.TOTAL}:r={B.FPS}",
           "-filter_complex", vf,
           "-map", "[vout]", "-t", f"{B.TOTAL}", "-r", f"{B.FPS}",
           "-c:v", "libx264", "-preset", "slow", "-crf", "19",
           "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", rendered])

    print("  [合成] 混流音视频 …（与横版共用同一条音乐床，切点完全一致）")
    B.run([B.FF, "-y", "-v", "error", "-i", rendered, "-i", music,
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-t", f"{B.TOTAL}", "-movflags", "+faststart",
           "-metadata", "title=City Nights · 20s Vertical Timelapse Montage",
           "-metadata", "comment=Footage: pixabay/pexels royalty-free stock. "
                        "Music: Shenzhen Nightlife by Kevin MacLeod (freepd.com, CC0 1.0)",
           OUT_MP4])


def main():
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    music = os.path.join(B.WORK, "music.m4a")
    if os.path.exists(music):
        print(f"① 复用横版音乐床: {music}")
    else:
        print("① 重新生成音乐床 …")
        music = B.build_music()
    print("② 渲染 10 个竖直镜头 …")
    build_shots()
    print("③ 合成竖版成片 …")
    build_final(music)
    info = B.probe(OUT_MP4, "format=duration,size,bit_rate")
    print(f"\n✅ 竖版成片: {OUT_MP4}")
    print(f"   时长 {float(info['format']['duration']):.3f}s  "
          f"大小 {int(info['format']['size']) / 1e6:.2f} MB  "
          f"码率 {int(info['format']['bit_rate']) / 1e6:.2f} Mbps")


if __name__ == "__main__":
    main()
