"""
secure-api/python/server.py
Drop-in encrypted API + storage layer. Single file. Protocol-compatible with node/server.js.

LAYER 1 - TRANSPORT: TLS enforced (uvicorn --ssl-certfile/--ssl-keyfile) + HSTS header.
LAYER 2 - PAYLOAD: AES-256-GCM end-to-end body encryption + HMAC-SHA256 signed
          requests with timestamp/nonce replay protection.
LAYER 3 - AT-REST: AES-256-GCM field-level encryption in SQLite, key derived via
          scrypt per-record salt, integrity-tagged.

ENV REQUIRED:
  MASTER_KEY   64-hex-char (32 byte) root secret
  API_KEYS     JSON map {"keyId": "hexSecret"}
  DB_PATH      optional, default secure.db
"""
import os, json, time, hmac, hashlib, base64, sqlite3
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

def need(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"[FATAL] missing env {name}")
    return v

MASTER_KEY = bytes.fromhex(need("MASTER_KEY"))
assert len(MASTER_KEY) == 32, "MASTER_KEY must be 32 bytes (64 hex chars)"
API_KEYS = json.loads(need("API_KEYS"))
DB_PATH = os.environ.get("DB_PATH", "secure.db")
SIG_WINDOW_MS = 5 * 60 * 1000

# ---------- layer 3: at-rest crypto ----------
def derive_key(salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(MASTER_KEY)

def encrypt_field(plaintext: str, aad: str = "kv"):
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = derive_key(salt)
    ct = AESGCM(key).encrypt(iv, plaintext.encode(), aad.encode())
    return {"salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}  # AESGCM appends tag to ct

def decrypt_field(rec: dict, aad: str = "kv") -> str:
    key = derive_key(unb64(rec["salt"]))
    pt = AESGCM(key).decrypt(unb64(rec["iv"]), unb64(rec["ct"]), aad.encode())
    return pt.decode()

def b64(b): return base64.b64encode(b).decode()
def unb64(s): return base64.b64decode(s)

# ---------- storage ----------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("""CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY, salt TEXT, iv TEXT, ct TEXT, updated_at INTEGER)""")
conn.commit()

def kv_set(key, value):
    rec = encrypt_field(json.dumps(value), key)
    conn.execute("""INSERT INTO kv (k,salt,iv,ct,updated_at) VALUES (?,?,?,?,?)
      ON CONFLICT(k) DO UPDATE SET salt=excluded.salt, iv=excluded.iv, ct=excluded.ct, updated_at=excluded.updated_at""",
      (key, rec["salt"], rec["iv"], rec["ct"], int(time.time()*1000)))
    conn.commit()

def kv_get(key):
    row = conn.execute("SELECT salt,iv,ct FROM kv WHERE k=?", (key,)).fetchone()
    if not row: return None
    try:
        return json.loads(decrypt_field({"salt": row[0], "iv": row[1], "ct": row[2]}, key))
    except Exception:
        return "__INTEGRITY_FAIL__"

def kv_delete(key): conn.execute("DELETE FROM kv WHERE k=?", (key,)); conn.commit()
def kv_list(prefix=""):
    return [r[0] for r in conn.execute("SELECT k FROM kv WHERE k LIKE ?", (prefix + "%",)).fetchall()]

# ---------- layer 2: payload crypto + signing ----------
def session_key(key_id: str):
    secret = API_KEYS.get(key_id)
    if not secret: return None
    h = hashlib.sha256()
    h.update(bytes.fromhex(secret)); h.update(MASTER_KEY)
    return h.digest()

def decrypt_body(key_id, payload):
    key = session_key(key_id)
    pt = AESGCM(key).decrypt(unb64(payload["iv"]), unb64(payload["ct"]), None)
    return json.loads(pt.decode())

def encrypt_body(key_id, obj):
    key = session_key(key_id)
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, json.dumps(obj).encode(), None)
    return {"iv": b64(iv), "ct": b64(ct)}

_seen_nonces = {}
def verify_signature(method, path, headers, raw_body: str):
    key_id = headers.get("x-api-key-id")
    ts = headers.get("x-timestamp")
    nonce = headers.get("x-nonce")
    sig = headers.get("x-signature")
    secret = API_KEYS.get(key_id) if key_id else None
    if not (key_id and secret and ts and nonce and sig):
        return None, "missing_auth_headers"
    ts = int(ts)
    if abs(int(time.time()*1000) - ts) > SIG_WINDOW_MS:
        return None, "stale_timestamp"
    now = int(time.time()*1000)
    for n, exp in list(_seen_nonces.items()):
        if exp < now: del _seen_nonces[n]
    if nonce in _seen_nonces:
        return None, "replay_detected"
    base = f"{method}\n{path}\n{ts}\n{nonce}\n{raw_body}"
    expected = hmac.new(bytes.fromhex(secret), base.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None, "bad_signature"
    _seen_nonces[nonce] = now + SIG_WINDOW_MS
    return key_id, None

# ---------- app ----------
app = FastAPI()
_buckets = {}

@app.middleware("http")
async def security_layers(request: Request, call_next):
    ip = request.client.host
    now = time.time()
    w = _buckets.get(ip, {"count": 0, "reset": now + 60})
    if now > w["reset"]: w = {"count": 0, "reset": now + 60}
    w["count"] += 1; _buckets[ip] = w
    if w["count"] > 120:
        return JSONResponse({"error": "rate_limited"}, status_code=429)
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

async def auth_and_decrypt(request: Request):
    raw = (await request.body()).decode() or ""
    key_id, err = verify_signature(request.method, request.url.path, request.headers, raw)
    if err:
        return None, None, JSONResponse({"error": err}, status_code=401)
    try:
        payload = decrypt_body(key_id, json.loads(raw)) if raw else {}
    except Exception:
        return None, None, JSONResponse({"error": "decrypt_failed"}, status_code=400)
    return key_id, payload, None

def reply(key_id, status, obj):
    return JSONResponse(encrypt_body(key_id, obj), status_code=status)

@app.get("/health")
def health(): return {"status": "ok", "ts": int(time.time()*1000)}

@app.post("/v1/data/{key}")
async def set_data(key: str, request: Request):
    key_id, payload, err = await auth_and_decrypt(request)
    if err: return err
    kv_set(key, payload)
    return reply(key_id, 200, {"stored": True})

@app.get("/v1/data/{key}")
async def get_data(key: str, request: Request):
    key_id, _, err = await auth_and_decrypt(request)
    if err: return err
    v = kv_get(key)
    if v is None: return reply(key_id, 404, {"error": "not_found"})
    if v == "__INTEGRITY_FAIL__": return reply(key_id, 409, {"error": "integrity_failure"})
    return reply(key_id, 200, {"value": v})

@app.delete("/v1/data/{key}")
async def delete_data(key: str, request: Request):
    key_id, _, err = await auth_and_decrypt(request)
    if err: return err
    kv_delete(key)
    return reply(key_id, 200, {"deleted": True})

@app.get("/v1/data")
async def list_data(request: Request, prefix: str = ""):
    key_id, _, err = await auth_and_decrypt(request)
    if err: return err
    return reply(key_id, 200, {"keys": kv_list(prefix)})

# run: uvicorn server:app --host 0.0.0.0 --port 8443 --ssl-certfile cert.pem --ssl-keyfile key.pem
