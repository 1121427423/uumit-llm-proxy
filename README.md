# UUMit LLM Proxy

一个轻量的 **LLM API 转发代理**：客户端只上传「用密码加密过的 API Key」，服务端在内存里解密后转发到上游模型，
**密钥全程不以明文落库/落盘**。附带 AES 加解密接口，便于前端在浏览器侧加密。

| 项目 | 说明 |
|---|---|
| 框架 | FastAPI + Uvicorn |
| 加密 | AES-256-**CBC** / AES-256-**GCM**（`pycryptodome`），密钥由 **PBKDF2-HMAC-SHA256**（100,000 轮，16 字节随机 salt）从密码派生 |
| 上游 | `deepseek`（默认 `deepseek-chat`）、`groq`（默认 `llama-3.1-8b-instant`） |
| 部署 | `render.yaml`（Python 运行时，`uvicorn main:app --host 0.0.0.0 --port $PORT`） |

## 快速开始

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000      # 或 python3 main.py（监听 $PORT，默认 8000）
```

## 接口

### `GET /` — 健康检查

```json
{"status": "ok", "endpoints": ["/encrypt", "/proxy"],
 "methods": ["aes-256-cbc", "aes-256-gcm"], "providers": ["deepseek", "groq"]}
```

### `POST /encrypt` — 加密 API Key

请求：`{ "key": "<明文 API Key>", "password": "<口令>", "method": "aes-256-cbc" }`
返回：`{ "encrypted_key", "iv", "salt", "method" }`（除 `method` 外均为 base64）。

### `POST /proxy` — 解密并转发对话请求

请求：

```json
{
  "encrypted_key": "...", "password": "...", "iv": "...", "salt": "...",
  "method": "aes-256-cbc",
  "provider": "deepseek",
  "model": "",
  "messages": [{"role": "user", "content": "你好"}]
}
```

- `provider` 不在支持列表时自动回退到 `deepseek`；`model` 留空则用该 provider 的默认模型。
- 上游返回原样透传；若响应里没有 `choices` 字段，会补一个 `{"choices": null, "error": ...}`，方便调用方统一判错。
- 转发超时 30 s；任何异常以 HTTP 500 + `proxy failed: ...` 返回。

## 示例

```bash
# 1) 加密（前端通常在浏览器里做这一步）
curl -s localhost:8000/encrypt -H 'Content-Type: application/json' \
  -d '{"key":"sk-xxxx","password":"my-pass","method":"aes-256-gcm"}'
# → {"encrypted_key":"...","iv":"...","salt":"...","method":"aes-256-gcm"}

# 2) 转发
curl -s localhost:8000/proxy -H 'Content-Type: application/json' -d '{
  "encrypted_key":"<上一步的 encrypted_key>","password":"my-pass",
  "iv":"<iv>","salt":"<salt>","method":"aes-256-gcm",
  "provider":"deepseek","messages":[{"role":"user","content":"用一句话介绍杭州"}]}'
```

## 本地自测记录

| 检查 | 结果 |
|---|---|
| `GET /` | 返回 `{"status":"ok", ...}`，`providers: ["deepseek","groq"]` ✅ |
| `POST /encrypt`（aes-256-gcm） | 返回 base64 的 `encrypted_key` / `iv`(12 B) / `salt`(16 B)；按同样参数解密 → **原文一致** ✅ |
| `POST /encrypt`（aes-256-cbc） | 同上，`iv` 16 B，解密原文一致 ✅ |
| `POST /proxy` | 链路可达；上游不可达时按约定返回 `HTTP 500 {"detail":"proxy failed: ..."}` ✅（转发成功与否取决于运行环境能否访问 `api.deepseek.com` / `api.groq.com`） |

## 安全说明

- 密码与解密后的 API Key **不写入日志、不落库**；服务本身无状态，重启即忘。
- PBKDF2 100k 轮 + 随机 salt/IV，同一 Key 多次加密结果不同；GCM 模式自带完整性校验（篡改会解密失败）。
- 生产环境请置于 HTTPS 之后，并按需收紧 `main.py` 里 `CORSMiddleware` 的 `allow_origins`（当前为 `*`）。

---

## 本仓库内的视频交付物

本仓库当前分支还包含一项独立的**「城市夜景 · 20 秒延时混剪」**任务成果，全部内容在 [`deliverables/`](./deliverables/)：

- 成片：`deliverables/city-night-timelapse-20s.mp4`（横版 16:9）、`deliverables/vertical/city-night-timelapse-9x16-20s.mp4`（竖版 9:16）
- 子代理评审：横版 **97.3 / 100**、竖版 **97.4 / 100**；画面重复度 **0.0 / 100**
- 说明文档：[`deliverables/README.md`](./deliverables/README.md)（速查）、[`deliverables/DOCUMENTATION.md`](./deliverables/DOCUMENTATION.md)（完整制作文档，含素材获取 / 软件安装 / 对拍算法 / 滤镜链 / 三轮返工）

该目录与代理服务互不影响，可单独取用或整体删除。
