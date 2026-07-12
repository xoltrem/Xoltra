'use strict';
const crypto = require('crypto');

function sign(hmacKey, dataBuf) {
  return crypto.createHmac('sha256', hmacKey).update(dataBuf).digest();
}

// Constant-time compare. Returns true/false only — caller decides what to do.
// No deletion, no lockout: mismatch just means "warn + offer resync".
function verify(hmacKey, dataBuf, signatureBuf) {
  const expected = sign(hmacKey, dataBuf);
  if (expected.length !== signatureBuf.length) return false;
  return crypto.timingSafeEqual(expected, signatureBuf);
}

module.exports = { sign, verify };
