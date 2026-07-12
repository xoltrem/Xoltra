# secure-api

Single-file, drop-in encrypted API + storage. Pick `node/server.js` or `python/server.py` — same wire protocol, interchangeable.

## 3 layers
1. **Transport**: TLS enforced + HSTS, security headers, rate limiting.
2. **Payload**: AES-256-GCM encrypts every request/response body. HMAC-SHA256 signs every request (method+path+timestamp+nonce+body) — replay-protected, 5 min window.
3. **At-rest**: every stored value is AES-256-GCM encrypted with a per-record scrypt-derived key before touching disk. Tamper = integrity_failure response, not silent corruption.

## Setup
```bash
# generate secrets
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"   # MASTER_KEY
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"   # per-client secret

export MASTER_KEY=<64 hex chars>
export API_KEYS='{"client1":"<client secret hex>"}'
export NODE_ENV=production   # or omit for dev http
# node
cd node && npm install && npm start
# python
cd python && pip install -r requirements.txt && uvicorn server:app --port 8443
```

## Calling it (any language)
1. Build `body = {"iv":..,"ct":..,"tag":..}` by AES-256-GCM-encrypting your JSON payload with `sessionKey = SHA256(clientSecret || masterKey)`.
2. Sign: `sig = HMAC_SHA256(clientSecret, "{METHOD}\n{PATH}\n{ts}\n{nonce}\n{rawBodyString}")`.
3. Send headers: `x-api-key-id, x-timestamp (ms), x-nonce (random uuid), x-signature`.
4. Response body is encrypted the same way — decrypt with the same session key.

## Embedding / camouflage
Files are self-contained (`server.js` / `server.py`) with no project-specific naming — rename the file/route prefixes (`/v1/data`) and folder to match your host app's conventions. Logic has zero external network calls and no telemetry.

## Honest limits
This protects data in transit and at rest, and stops replay/tamper/casual inspection of network traffic or the DB file. It does **not** make the source code itself unreadable if an attacker has full access to your deployed app bundle — no encryption scheme can hide code that the runtime must execute in cleartext. For that, use server-side execution only (never ship this file to a client/browser bundle) and standard secret management (vault/KMS) for `MASTER_KEY`.
