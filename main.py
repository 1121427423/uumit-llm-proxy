"""UUMit LLM Proxy — encrypt + proxy with AES symmetric encryption."""
import os, base64, json, hashlib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
# PBKDF2 via hashlib
import httpx

app = FastAPI(title="UUMit LLM Proxy")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PROVIDERS = {
    "deepseek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "default_model": "deepseek-chat",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.1-8b-instant",
    },
}

# ─── Models ────────────────────────────────────────────

class EncryptRequest(BaseModel):
    key: str
    password: str
    method: str = "aes-256-cbc"  # aes-256-cbc | aes-256-gcm

class EncryptResponse(BaseModel):
    encrypted_key: str
    iv: str
    salt: str
    method: str

class ProxyRequest(BaseModel):
    encrypted_key: str
    password: str
    iv: str
    salt: str
    method: str = "aes-256-cbc"
    messages: list
    model: str = ""
    provider: str = "deepseek"

# ─── Crypto ────────────────────────────────────────────

def _derive_key(password: str, salt: bytes, key_len: int = 32) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000, dklen=key_len)

def encrypt_aes(key_str: str, password: str, method: str) -> dict:
    salt = get_random_bytes(16)
    aes_key = _derive_key(password, salt)
    iv = get_random_bytes(12 if method == "aes-256-gcm" else 16)

    if method == "aes-256-gcm":
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv)
        ct, tag = cipher.encrypt_and_digest(key_str.encode())
        encrypted = ct + tag
    else:
        cipher = AES.new(aes_key, AES.MODE_CBC, iv=iv)
        encrypted = cipher.encrypt(pad(key_str.encode(), AES.block_size))

    return {
        "encrypted_key": base64.b64encode(encrypted).decode(),
        "iv": base64.b64encode(iv).decode(),
        "salt": base64.b64encode(salt).decode(),
        "method": method,
    }

def decrypt_aes(encrypted_key: str, password: str, iv: str, salt: str, method: str) -> str:
    salt_bytes = base64.b64decode(salt)
    iv_bytes = base64.b64decode(iv)
    enc_bytes = base64.b64decode(encrypted_key)
    aes_key = _derive_key(password, salt_bytes)

    if method == "aes-256-gcm":
        tag = enc_bytes[-16:]
        ct = enc_bytes[:-16]
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=iv_bytes)
        decrypted = cipher.decrypt_and_verify(ct, tag)
    else:
        cipher = AES.new(aes_key, AES.MODE_CBC, iv=iv_bytes)
        decrypted = unpad(cipher.decrypt(enc_bytes), AES.block_size)

    return decrypted.decode()

# ─── Routes ────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "endpoints": ["/encrypt", "/proxy"], "methods": ["aes-256-cbc", "aes-256-gcm"], "providers": list(PROVIDERS.keys())}

@app.post("/encrypt")
def encrypt(req: EncryptRequest):
    try:
        if req.method not in ("aes-256-cbc", "aes-256-gcm"):
            raise HTTPException(400, f"unsupported method: {req.method}")
        result = encrypt_aes(req.key, req.password, req.method)
        return result
    except Exception as e:
        raise HTTPException(500, f"encrypt failed: {e}")

@app.post("/proxy")
async def proxy(req: ProxyRequest):
    try:
        if req.method not in ("aes-256-cbc", "aes-256-gcm"):
            raise HTTPException(400, f"unsupported method: {req.method}")
        if req.provider not in PROVIDERS:
            req.provider = "deepseek"

        api_key = decrypt_aes(req.encrypted_key, req.password, req.iv, req.salt, req.method)
        prov = PROVIDERS[req.provider]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                prov["url"],
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": req.model or prov["default_model"], "messages": req.messages},
            )
            data = resp.json()
            # Always include "choices" so the review server can find it
            if "choices" not in data:
                data = {"choices": None, "error": data.get("error", str(data))}
            return data
    except Exception as e:
        raise HTTPException(500, f"proxy failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
