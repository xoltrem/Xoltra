# Xoltra Desktop (Electron) — local secure storage

Local, on-disk encrypted+signed storage layer for the Electron desktop
build (see `electron-builder.yml` at the repo root). Separate from the
backend's SQLite knowledge base — this is client-side local storage for
the desktop app specifically (e.g. cached credentials, offline state).

| File | Purpose |
|---|---|
| `BinaryHandler.js` | msgpack pack/unpack for the local data blob |
| `CryptoVault.js` | AES-256-GCM encrypt/decrypt (key from OS keychain / Electron `safeStorage`, never hardcoded) |
| `IntegrityGuard.js` | HMAC-SHA256 sign/verify, constant-time compare |
| `StartupOrchestrator.js` | Ties the above together: reads, decrypts, verifies the local blob on app startup |

Requires `msgpackr` (see `BinaryHandler.js`). Not part of the Next.js
frontend or Flask backend build — this runs in the Electron main process.
