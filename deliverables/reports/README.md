# 报告（reports/）

由工具自动生成的**体检报告**，与 `review/`（子代理评分卡）分工不同：

| 目录 | 回答的问题 | 生成工具 |
|---|---|---|
| `review/` | 成片**整体**好不好？（6 维度 100 分、80 分门禁、返工建议） | `review/review_agent.py` |
| `reports/`（本目录） | 十个镜头之间**有没有撞脸**？（观众反馈的「重复度太高」） | `tools/repetition_audit.py` |

## 文件

| 文件 | 内容 |
|---|---|
| `rep-landscape.md` / `.json` | 横版重复度体检（评分、45 对镜头明细、最相似的 5 对） |
| `rep-portrait.md` / `.json` | 竖版重复度体检 |

## 重新生成

```bash
cd deliverables
python3 tools/repetition_audit.py city-night-timelapse-20s.mp4 \
        --json reports/rep-landscape.json
python3 tools/repetition_audit.py vertical/city-night-timelapse-9x16-20s.mp4 \
        --json reports/rep-portrait.json
```

## 判定口径（速记）

- 每个镜头取**中段一帧**，缩略到 160×90 后**两两比对**（10 个镜头 = 45 对）；
- 同时满足「缩略图平均绝对差 **MAD < 0.12**」与「直方图 JS 散度 **< 0.12**」→ 判为「看上去是同一个画面」；
- **重复度评分 = 重复对数 ÷ 总对数 × 100**：0 = 十个镜头互不相同，100 = 全部雷同；
- 切点：本项目优先传入已知切点（`--cuts`）；黑盒场景下由帧间差分自动检测
  （阈值 = max(中位数×3, 最大跳变×0.5)，最小间隔 0.5 s）。

## 当前结果

| 版本 | 重复度 | 高度重复对 | 平均 MAD | 平均 JSD |
|---|---|---|---|---|
| 横版 v3.2 | **0.0 / 100** | 0 对 | 0.196 | 0.044 |
| 竖版 v3.2 | **0.0 / 100** | 0 对 | 0.215 | 0.059 |
| 横版 v2（改造前，历史值） | 8.9 / 100 | 4 对 | 0.169 | 0.038 |

> 改造手法（镜像 / 倒放 / 局部特写 / 多取景窗口 / 冷暖微差 / 运动方向变化）见
> [`../README.md`](../README.md) §四 与 [`../DOCUMENTATION.md`](../DOCUMENTATION.md) §5.1a。
