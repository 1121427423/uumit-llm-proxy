#!/usr/bin/env python3
"""
独立评审子代理 · 视频质量评分
=================================
设计原则：**只读成片文件本身**（外加公开的构建元数据文件），不信任构建脚本的自我宣称。
所有能量化的维度都现场测量；无法量化的维度标注为“人工判读”并给出理由。

评分维度（满分 100）：
  1. 技术规格与兼容性  15
  2. 节奏与音画同步    25
  3. 运动与流畅度      15
  4. 画面质量          20
  5. 剪辑结构与叙事    15
  6. 合规与可复现      10

判分门槛：总评 < 80 → 必须给出可执行的优化建议并重新生成。

用法:
  python3 review/review_agent.py --variant landscape
  python3 review/review_agent.py --variant portrait --json-out review/scorecard-portrait.json
"""

import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import build as B  # noqa: E402  只借用 ffmpeg/ffprobe 定位与音频分析工具

VARIANTS = {
    "landscape": dict(
        mp4=os.path.join(ROOT, "city-night-timelapse-20s.mp4"),
        w=1920, h=1080, shots_file=os.path.join(ROOT, "build.py"),
    ),
    "portrait": dict(
        mp4=os.path.join(ROOT, "vertical", "city-night-timelapse-9x16-20s.mp4"),
        w=1080, h=1920, shots_file=os.path.join(ROOT, "build_portrait.py"),
    ),
}

REPORT = []


def sec(name, weight):
    REPORT.append(dict(name=name, weight=weight, items=[], score=0.0))
    return REPORT[-1]


def item(section, label, points, max_points, detail, auto=True):
    section["items"].append(dict(label=label, points=round(points, 2),
                                 max=max_points, detail=detail, auto=auto))
    section["score"] += points


# ------------------------------------------------------------------ 测量
def probe_video(path):
    info = B.probe(path, "format=duration,size,bit_rate,format_name:"
                         "stream=index,codec_name,codec_type,width,height,profile,level,"
                         "r_frame_rate,nb_frames,pix_fmt,sample_rate,channels")
    v = [s for s in info["streams"] if s["codec_type"] == "video"][0]
    a = [s for s in info["streams"] if s["codec_type"] == "audio"][0]
    return info["format"], v, a


def decode_gray(path, w=320, h=180):
    raw = subprocess.run([B.FF, "-v", "error", "-i", path, "-vf", f"scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[:n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32), (w, h)


def laplacian_var(frames):
    """清晰度：拉普拉斯算子的方差（越大越锐利）。"""
    lap = (frames[:, :-2, 1:-1] + frames[:, 2:, 1:-1] + frames[:, 1:-1, :-2]
           + frames[:, 1:-1, 2:] - 4 * frames[:, 1:-1, 1:-1])
    return float(lap.var())


def frame_hist_emd(a, b):
    ha = np.histogram(a, bins=32, range=(0, 255))[0].astype(np.float64)
    hb = np.histogram(b, bins=32, range=(0, 255))[0].astype(np.float64)
    ha /= ha.sum() + 1e-9
    hb /= hb.sum() + 1e-9
    return float(np.abs(np.cumsum(ha - hb)).sum())


def detect_flash(frames, fps=30):
    """检测中段高光强调：帧亮度相对邻域的突增。"""
    lum = frames.mean(axis=(1, 2))
    base = np.median(lum)
    idx = int(np.argmax(lum))
    return float(lum[idx] - base), idx / fps


def read_shot_table(path):
    """从构建脚本里读取镜头表（速度/运镜/取景），用于评估“镜头语法变化”。"""
    ns = {}
    src = open(path).read()
    for name in ("SHOTS", "PORTRAIT_SHOTS"):
        if name in src:
            start = src.index(name)
            start = src.index("[", start)
            depth, end = 0, start
            for i in range(start, len(src)):
                if src[i] == "[":
                    depth += 1
                elif src[i] == "]":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            try:
                ns[name] = eval(src[start:end], {"dict": dict})  # noqa: S307 本地可信脚本
            except Exception:
                pass
    return ns.get("SHOTS") or ns.get("PORTRAIT_SHOTS") or []


# ------------------------------------------------------------------ 主流程
def review(variant):
    cfg = VARIANTS[variant]
    path = cfg["mp4"]
    fmt, v, a = probe_video(path)
    dur = float(fmt["duration"])
    frames_n = int(v["nb_frames"])
    fps = eval(v["r_frame_rate"])
    cuts = list(B.CUT_TIMES)          # 镜头起点（秒），来自公开构建表
    lens = list(B.DURS)               # 每个镜头时长
    n_shots = len(cuts)
    frames, (gw, gh) = decode_gray(path)
    fps_d = len(frames) / dur

    # ---------------- 1. 技术规格与兼容性 (15)
    s = sec("技术规格与兼容性", 15)
    spec_ok = []
    pts = 0
    checks = [
        ("mp4 容器", "mp4" in fmt["format_name"], 2),
        ("H.264 High Profile", v["codec_name"] == "h264" and "High" in (v.get("profile") or ""), 2),
        ("Level 4.1（≤1080p60 兼容）", str(v.get("level")) == "41", 1.5),
        ("yuv420p 8bit（通用兼容）", v["pix_fmt"] == "yuv420p", 1.5),
        ("+faststart（moov 前置）", open(path, "rb").read(65536).find(b"moov")
         < open(path, "rb").read(65536).find(b"mdat"), 1.5),
        ("AAC 2ch 48kHz", a["codec_name"] == "aac" and a["channels"] == 2
         and int(a["sample_rate"]) == 48000, 1.5),
    ]
    for label, ok, p in checks:
        pts += p if ok else 0
        spec_ok.append(f"{label}{'✓' if ok else '✗'}")
    item(s, "编码/容器合规", pts, 10, " / ".join(spec_ok))
    d_ok = abs(dur - 20.0) <= 0.02
    f_ok = frames_n == 600
    pts2 = (3 if d_ok else 0) + (2 if f_ok else 0)
    item(s, "时长 20s 且帧数精确", pts2, 5,
         f"duration={dur:.3f}s frames={frames_n}（要求 20.000s / 600 帧）")

    # ---------------- 2. 节奏与音画同步 (25)
    s = sec("节奏与音画同步", 25)
    x, sr = B.decode_audio(path, 44100)
    low, lfps = B.low_band_env(x, sr)
    onset, ofps = B.onset_env(x, sr)
    onset = onset / (onset.mean() + 1e-12)
    emps = []
    for c in cuts:
        j = int(c * lfps)
        h = int(0.06 * lfps)
        emps.append(low[max(0, j - h):j + h + 1].max() / low.mean())
    mean_emp = float(np.mean(emps[1:]))          # 第 1 刀在淡入区，单独说明
    grid = {}
    for off in (0.0, 0.25):
        idx = np.round(np.arange(off, dur - 0.05, 0.5) * lfps).astype(int)
        h = int(0.05 * lfps)
        grid[off] = float(np.mean([low[max(0, j - h):j + h + 1].max() for j in idx])) / low.mean()
    pts = min(12.0, 12.0 * mean_emp / 2.6)
    item(s, "切点落在能量重拍上", pts, 12,
         f"后 9 刀低频强调均值 {mean_emp:.2f}x（满分行 ≥2.6x）；逐刀 "
         + " ".join(f"{e:.1f}" for e in emps))
    ratio = grid[0.0] / max(grid[0.25], 1e-9)
    pts = 5 if ratio > 1.5 else (3 if ratio > 1.2 else 1)
    item(s, "全片网格对齐（非巧合）", pts, 5,
         f"0.5s 网格强调 偏移0={grid[0.0]:.2f}x vs 偏移0.25s={grid[0.25]:.2f}x，比值 {ratio:.2f}")
    bpm, period, phase = B.measure_beat_period(x, sr, bpm_hint=(118, 122))
    dev = abs(period - 0.5) / 0.5
    pts = 4 if dev < 0.004 else (2.5 if dev < 0.01 else 1)
    item(s, "实际 BPM 稳定在 120", pts, 4, f"实测 {bpm:.2f} BPM，周期偏差 {dev * 100:.2f}%")
    distinct = len(set(lens))
    pts = 4 if distinct >= 3 else (2 if distinct == 2 else 0.5)
    item(s, "镜头时长层次（力度起伏）", pts, 4,
         f"镜头长度集合 {sorted(set(lens))} → {distinct} 种"
         + ("；等长切分缺少张弛" if distinct < 3 else "；长短镜对比形成张弛")
         + f"（切点 {[round(c,1) for c in cuts]}）")

    # ---------------- 3. 运动与流畅度 (15)
    # 注意：镜头 k 的帧区间为 [cut[k], cut[k+1])，而 d[i] = |frame[i+1] - frame[i]|，
    # 因此镜头内统计必须排除每段最后一个 d（它跨越到下一个镜头 = 切点本身）。
    s = sec("运动与流畅度", 15)
    d = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    frozen = int((d < 0.35).sum())
    pts = 6 if frozen == 0 else max(0.0, 6 - frozen * 0.8)
    item(s, "无冻帧/重复帧", pts, 6, f"重复帧 {frozen} 处（阈值 diff<0.35）")
    fcuts = [int(round(c * fps_d)) for c in cuts] + [len(d)]
    shot_min, spikes = [], []
    for k in range(n_shots):
        seg = d[fcuts[k]:max(fcuts[k], fcuts[k + 1] - 1)]      # 排除切点帧
        seg = seg[seg > 0]
        shot_min.append(float(seg.min()))
        spikes.append(float(seg.max() / (np.median(seg) + 1e-6)))
    worst = min(shot_min)
    pts = min(5.0, 5.0 * worst / 1.5) if worst < 1.5 else 5.0
    item(s, "镜头内持续运动", pts, 5,
         f"镜头内最小帧间差 {worst:.2f}（满分行 ≥1.5）；逐镜 "
         + " ".join(f"{m:.1f}" for m in shot_min))
    worst_spike = max(spikes)
    pts = 4 if worst_spike < 8 else (2.5 if worst_spike < 14 else 1)
    item(s, "镜头内无异常跳变", pts, 4,
         f"单镜头内最大/中位帧间差 {worst_spike:.1f}（<8 为平滑；已排除切点帧）")

    # ---------------- 4. 画面质量 (20)
    s = sec("画面质量", 20)
    mid_idx = [min(len(frames) - 1, int((c + 0.55 * l) * fps_d))
               for c, l in zip(cuts, lens)]
    mid = frames[mid_idx]
    sharp = laplacian_var(mid.astype(np.float32))
    pts = min(7.0, 7.0 * sharp / 260.0) if sharp < 260 else 7.0
    item(s, "清晰度（拉普拉斯方差）", pts, 7, f"抽帧清晰度 {sharp:.0f}（≥260 满分）")
    lum = mid.mean(axis=(1, 2))
    black_clip = float((mid < 3).mean())
    white_clip = float((mid > 252).mean())
    pts = 5.0
    notes = []
    if black_clip > 0.20:
        pts -= 2
        notes.append(f"死黑像素 {black_clip * 100:.1f}%")
    if white_clip > 0.02:
        pts -= 2
        notes.append(f"过曝像素 {white_clip * 100:.1f}%")
    mean_lum = float(lum.mean())
    if not (25 <= mean_lum <= 130):
        pts -= 1.5
        notes.append(f"平均亮度 {mean_lum:.0f} 偏离夜景甜区")
    item(s, "曝光与动态范围", pts, 5,
         "无死黑/过曝，夜景明暗层次正常" if not notes else "；".join(notes))
    # 噪点：平缓区域的高频能量（越低越干净）
    noise = float(np.median(np.abs(np.diff(frames, axis=0))))
    pts = 4 if noise < 3 else (3 if noise < 5 else 1.5)
    item(s, "噪点/压缩伪影控制", pts, 4, f"中位帧间噪声 {noise:.2f}（<3 干净）")
    hs = [float(mid[i].std()) for i in range(len(mid))]
    emd = [frame_hist_emd(mid[i], mid[i + 1]) for i in range(len(mid) - 1)]
    mean_emd = float(np.mean(emd))
    pts = min(4.0, 4.0 * mean_emd / 0.55)
    item(s, "画面多样性（相邻镜头差异）", pts, 4,
         f"相邻镜头直方图距离均值 {mean_emd:.2f}（≥0.55 满分）；"
         f"亮度层次标准差 {np.std(hs):.1f}")

    # ---------------- 5. 剪辑结构与叙事 (15)
    s = sec("剪辑结构与叙事", 15)
    head = float(frames[:6].mean())
    tail = float(frames[-6:].mean())
    body = float(frames.mean())
    fade_in = head < body * 0.75
    fade_out = tail < body * 0.85
    pts = (2.5 if fade_in else 0) + (2.5 if fade_out else 0)
    item(s, "开场/收尾处理", pts, 5,
         f"首帧组亮度 {head:.1f} / 尾帧组 {tail:.1f} / 全片 {body:.1f}"
         + ("（首尾均有淡入淡出）" if fade_in and fade_out else ""))
    shots = read_shot_table(cfg["shots_file"]) or list(B.SHOTS)
    # 竖版表是用 dict(**sh, px=...) 继承横版的，直接 eval 取不到值 → 回退到横版表
    if not all("zoom" in sh for sh in shots):
        shots = list(B.SHOTS)
    moves = set()
    for sh in shots:
        z = sh["zoom"]
        if sh.get("pan"):
            moves.add("pan")
        elif abs(z[1] - z[0]) > 1e-6:
            moves.add("push" if z[1] > z[0] else "pull")
        else:
            moves.add("static")
    srcs = {sh["src"] for sh in shots}
    pts = 0
    pts += 2.5 if len(moves) >= 3 else (1.5 if len(moves) == 2 else 0.5)
    pts += 2.5 if len(srcs) >= 4 else (1.8 if len(srcs) == 3 else 1.0)
    item(s, "镜头语法与素材多样性", pts, 5,
         f"运动方式 {sorted(moves)}（{len(moves)} 种）；独特画面源 {len(srcs)} 支"
         f"{'（3 支已是本环境可达的夜景上限）' if len(srcs) == 3 else ''}")
    delta, t_flash = detect_flash(frames, fps_d)
    pts = 5 if delta >= 8 and 8.0 <= t_flash <= 12.0 else (3 if delta >= 4 else 1)
    item(s, "视觉强调点（中段闪烁）", pts, 5,
         f"t={t_flash:.2f}s 亮度突增 +{delta:.1f}（要求 +≥8 且落在 8–12s）")

    # ---------------- 6. 合规与可复现 (10)
    s = sec("合规与可复现", 10)
    readme = os.path.join(ROOT, "README.md")
    has_license = os.path.exists(readme) and any(
        k in open(readme, encoding="utf-8").read()
        for k in ("CC0", "Pexels", "免版权", "License"))
    has_scripts = all(os.path.exists(os.path.join(ROOT, f))
                      for f in ("build.py", "verify.py"))
    pts = (2.5 if has_license else 0) + (2.5 if has_scripts else 0)
    item(s, "许可标注与脚本齐备", pts, 5,
         f"README 许可表 {'✓' if has_license else '✗'}；构建/自检脚本 "
         f"{'✓' if has_scripts else '✗'}")
    docs = os.path.join(ROOT, "DOCUMENTATION.md")
    tools = os.path.join(ROOT, "tools")
    pts = 2.5 if os.path.exists(docs) else 0
    pts += 2.5 if os.path.isdir(tools) else 0
    item(s, "完整文档与工具链固化", pts, 5,
         f"DOCUMENTATION.md {'✓' if os.path.exists(docs) else '✗'}；"
         f"tools/ 工具链 {'✓' if os.path.isdir(tools) else '✗'}")

    total = sum(x["score"] for x in REPORT)
    res = dict(variant=variant, file=path, total=round(total, 1),
               sections=REPORT, passed=total >= 80)
    res["suggestions"] = build_suggestions(res)
    return res


# 每一条可量化指标的「扣分 → 返工动作」对照表。
# 评分 < 满分时会自动按失分权重排序，生成可执行的优化建议（未达标时必须据此重新生成）。
SUGGESTIONS = {
    "编码/容器合规": "检查封装参数：H.264 High@4.1 / yuv420p / +faststart / AAC 48kHz 立体声。",
    "时长 20s 且帧数精确": "时长必须恰好 20.000 s = 600 帧 @30fps；用 -frames:v 精确截断而不是靠时长四舍五入。",
    "切点落在能量重拍上": "重跑 build.py 的网格相位扫描（段落起点 + 0.5 s 网格偏移），让每一刀压在低频底鼓上；"
                          "必要时更换曲目段落或改用 atempo 微调 BPM。",
    "全片网格对齐（非巧合）": "确认 CUT_TIMES 全部落在测得的拍网格上（0.5 s 整数倍），偏移 0.25 s 的强调应明显更低。",
    "实际 BPM 稳定在 120": "重跑 `--stage music`：检查 atempo 系数 = 原始 BPM/120，并对渲染结果闭环复测节拍周期。",
    "镜头时长层次（力度起伏）": "避免所有镜头等长：把切点排成 0.5 s 拍点的整数倍并拉开差距（如 3.0/2.0/1.5/1.0/2.5…），形成张弛。",
    "无冻帧/重复帧": "逐镜头排查 tpad 克隆帧：给每个镜头多取 0.4 s 素材余量，并用 -frames:v <dur*30> 精确截断；"
                      "源有效帧率过低时开 minterpolate 补帧。",
    "镜头内持续运动": "给近静态镜头加缓慢推拉（2 s 内 zoom 变化 ≥0.12），不要使用 z0==z1 的完全静止机位。",
    "镜头内无异常跳变": "排查单镜头内的非平滑帧：确认没有整数帧截断误差、没有跨镜头的克隆帧，"
                        "并对低帧率源启用 minterpolate 补帧（vsbmc=0 即可）。",
    "清晰度（拉普拉斯方差）": "提高中间码质量（CRF 16→14）或减少放大倍率：优先用 2K/4K 源、竖版尽量减少裁切后的上采样。",
    "曝光与动态范围": "抬暗部：加 colorlevels=rimin/gimin/bimin=0.035 与 eq=gamma=1.04；同时收敛对比度与暗角强度。",
    "噪点/压缩伪影控制": "降低 noise 颗粒强度或提高编码质量（CRF 更小），优先保证暗部无块效应。",
    "画面多样性（相邻镜头差异）": "相邻镜头不要取自同一素材的相邻时段：交错排布素材源与时段，或增加素材支数。",
    "开场/收尾处理": "加视频淡入淡出：fade=t=in:st=0:d=0.35 与 fade=t=out:st=<T-0.55>:d=0.55。",
    "镜头语法与素材多样性": "增加运镜种类（push/pull/pan/static 混用）并扩充素材源；本环境受可用素材限制时，"
                            "至少在时段与取景（px/cx/cy）上拉开差异。",
    "视觉强调点（中段闪烁）": "把高光闪烁对齐到 8–12 s 内的一个真实切点，并提高 alpha（0.42）到能测出 +8 以上的亮度突增。",
    "许可标注与脚本齐备": "在 README 中写清素材与音乐的许可（Pexels License / CC0 1.0），并保证 build.py、verify.py 齐备。",
    "完整文档与工具链固化": "补齐 DOCUMENTATION.md（素材获取→软件→合成细节）与 tools/（版本锁 + 安装脚本 + 安装包）。",
}


def build_suggestions(result):
    """把所有未拿满分的指标转成可执行的返工建议，按失分排序。"""
    out = []
    for s in result["sections"]:
        for it in s["items"]:
            lost = it["max"] - it["points"]
            if lost <= 1e-9:
                continue
            out.append(dict(
                section=s["name"], label=it["label"], lost=round(lost, 2),
                detail=it["detail"],
                advice=SUGGESTIONS.get(it["label"], "复查该指标对应的滤镜/参数后重跑构建脚本。"),
            ))
    out.sort(key=lambda x: -x["lost"])
    return out


def render_md(result):
    L = []
    L.append(f"# 评审子代理评分卡 · {result['variant']}\n")
    L.append(f"**成片**：`{result['file']}`\n")
    L.append(f"## 总评 **{result['total']} / 100** — "
             f"{'通过（≥80，无需返工）' if result['passed'] else '未达标（<80，需按建议优化并重新生成）'}\n")
    L.append("| 维度 | 得分 | 满分 |")
    L.append("|---|---|---|")
    for s in result["sections"]:
        L.append(f"| {s['name']} | {s['score']:.1f} | {s['weight']} |")
    L.append("")
    for sec_ in result["sections"]:
        L.append(f"### {sec_['name']} — {sec_['score']:.1f}/{sec_['weight']}")
        for it in sec_["items"]:
            L.append(f"- **{it['label']}** {it['points']}/{it['max']} — {it['detail']}")
        L.append("")
    sug = result.get("suggestions") or []
    if sug:
        L.append("## 优化建议（按失分权重排序）\n")
        if not result["passed"]:
            L.append("> 总评低于 80 分及格线：**必须按下面每一条返工并重新生成**，然后重跑本评分器。\n")
        else:
            L.append("> 已达标；以下为可选的进一步打磨项。\n")
        for i, x in enumerate(sug, 1):
            L.append(f"{i}. **[{x['section']}] {x['label']}**（失分 {x['lost']}）— {x['advice']}")
            L.append(f"   - 实测：{x['detail']}")
        L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="landscape", choices=list(VARIANTS))
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args()
    res = review(args.variant)
    js = args.json_out or os.path.join(HERE, f"scorecard-{args.variant}.json")
    md = args.md_out or os.path.join(HERE, f"scorecard-{args.variant}.md")
    json.dump(res, open(js, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(md, "w", encoding="utf-8").write(render_md(res))
    print(render_md(res))
    print(f"\n→ {js}\n→ {md}")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
