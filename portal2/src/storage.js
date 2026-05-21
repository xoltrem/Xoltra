const fs = require('fs');
const path = require('path');
const { v4: uuid } = require('uuid');

const DATA = path.join(__dirname, '..', 'data');
const SETTINGS_FILE = path.join(DATA, 'settings.json');
const SUMMARIES_FILE = path.join(DATA, 'summaries.json');

function read(file, def) {
  if (!fs.existsSync(DATA)) fs.mkdirSync(DATA, { recursive: true });
  if (!fs.existsSync(file)) return def;
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return def; }
}
function write(file, data) {
  if (!fs.existsSync(DATA)) fs.mkdirSync(DATA, { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

module.exports = {
  getSettings() { return read(SETTINGS_FILE, {}); },
  saveSettings(data) {
    const s = read(SETTINGS_FILE, {});
    Object.assign(s, data);
    write(SETTINGS_FILE, s);
  },
  getSummaries() { return read(SUMMARIES_FILE, []); },
  addSummary(data) {
    const list = read(SUMMARIES_FILE, []);
    const entry = { id: uuid(), ...data, createdAt: new Date().toISOString() };
    list.unshift(entry);
    write(SUMMARIES_FILE, list.slice(0, 50));
    return entry;
  },
  deleteSummary(id) {
    write(SUMMARIES_FILE, read(SUMMARIES_FILE, []).filter(s => s.id !== id));
  },
  clearSummaries() { write(SUMMARIES_FILE, []); }
};
