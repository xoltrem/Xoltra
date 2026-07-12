'use strict';
const msgpack = require('msgpackr');

function pack(obj) {
  return msgpack.pack(obj);
}

function unpack(buf) {
  return msgpack.unpack(buf);
}

module.exports = { pack, unpack };
