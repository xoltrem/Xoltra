'use strict';
const fs = require('fs/promises');
const path = require('path');
const { pack, unpack } = require('./BinaryHandler');
const { encrypt, decrypt } = require('./CryptoVault');
const { sign, verify } = require('./IntegrityGuard');

// dataFile:   local encrypted+signed blob (e.g. userdata/memory.bin)
// getKey():   returns { encKey, hmacKey } from OS-secure storage (electron safeStorage / keytar)
// fetchGoldenRecord(): server call returning latest authoritative record
// onIntegrityWarning(reason): UI hook — show a non-blocking warning, let user choose resync

async function loadLocal(dataFile, encKey) {
  const raw = await fs.readFile(dataFile); // sig(32) | encBlob
  const sig = raw.subarray(0, 32);
  const encBlob = raw.subarray(32);
  return { sig, encBlob };
}

async function saveLocal(dataFile, encKey, hmacKey, obj) {
  const plain = pack(obj);
  const encBlob = encrypt(encKey, plain);
  const sig = sign(hmacKey, encBlob);
  await fs.writeFile(dataFile, Buffer.concat([sig, encBlob]));
}

async function boot({ dataFile, getKey, fetchGoldenRecord, onIntegrityWarning, log }) {
  const { encKey, hmacKey } = await getKey();

  let localOk = false;
  let record = null;

  try {
    await fs.access(dataFile);
    const { sig, encBlob } = await loadLocal(dataFile, encKey);

    if (verify(hmacKey, encBlob, sig)) {
      const plain = decrypt(encKey, encBlob);
      record = unpack(plain);
      localOk = true;
    } else {
      log?.warn('[Integrity] Local file signature mismatch — not authoritative, resyncing.');
      onIntegrityWarning?.('signature_mismatch');
    }
  } catch (e) {
    log?.info('[Integrity] No valid local cache, fetching from server.', e.message);
  }

  // Server is always the source of truth; local is only a perf cache.
  const golden = await fetchGoldenRecord();
  if (golden) {
    record = golden;
    await saveLocal(dataFile, encKey, hmacKey, golden);
    localOk = true;
  }

  if (!localOk) throw new Error('No valid local or server record available at boot.');
  return record;
}

module.exports = { boot, saveLocal, loadLocal };
