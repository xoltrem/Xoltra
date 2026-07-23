'use strict';
const os = require('os');
const crypto = require('crypto');

// Stable per-device ID derived from MAC addresses of non-internal network
// interfaces, hashed with app salt so the raw MAC never leaves the device.
// Sent as `fingerprint` in POST /api/auth/google — auth-service's
// checkDeviceFingerprint middleware already rate-limits by this value.
function getDeviceId(salt = 'xoltra-device-salt') {
  const macs = Object.values(os.networkInterfaces())
    .flat()
    .filter(i => i && !i.internal && i.mac && i.mac !== '00:00:00:00:00:00')
    .map(i => i.mac)
    .sort();

  const base = macs.length ? macs.join(',') : os.hostname();
  return crypto.createHash('sha256').update(salt + ':' + base).digest('hex');
}

module.exports = { getDeviceId };
