let summaries = [];
let currentDetail = null;
let watching = false;
let watchInterval = null;
let activeDuckTabId = null;

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async function() {
  summaries = await loadSummaries();
  renderList();
  await checkDuckTab();
  wireButtons();
});

function wireButtons() {
  document.getElementById('btnSettings').addEventListener('click', showSettings);
  document.getElementById('btnAuto').addEventListener('click', toggleAuto);
  document.getElementById('btnSum').addEventListener('click', doSummarize);
  document.getElementById('btnBack').addEventListener('click', showMain);
  document.getElementById('btnSave').addEventListener('click', saveSettings);
  document.getElementById('btnTest').addEventListener('click', testKey);
  document.getElementById('btnBackDetail').addEventListener('click', showMain);
  document.getElementById('btnCopy').addEventListener('click', copyDetail);
  document.getElementById('btnDl').addEventListener('click', downloadDetail);
  document.getElementById('btnDel').addEventListener('click', deleteDetail);
}

// ── Auto button ───────────────────────────────────────────────────────────────
async function toggleAuto() {
  if (watching) {
    stopWatching();
    return;
  }

  chrome.runtime.sendMessage({ type: 'open_duck' }, function(res) {
    if (chrome.runtime.lastError) {
      toast('Error: ' + chrome.runtime.lastError.message, 'err');
      return;
    }
    toast('duck.ai opened 🦆', 'ok');
  });

  watching = true;
  setAutoUI(true);

  watchInterval = setInterval(async function() {
    var tabId = await findDuckTab();
    if (!tabId) return;

    activeDuckTabId = tabId;
    setDuckStatus(true);

    var text = await getConversation(tabId);
    if (text && text.length > 150) {
      clearInterval(watchInterval);
      watchInterval = null;
      watching = false;
      setAutoUI(false);
      toast('Conversation found — summarizing...', 'ok');
      await runSummarize(text);
    }
  }, 3000);
}

function stopWatching() {
  if (watchInterval) { clearInterval(watchInterval); watchInterval = null; }
  watching = false;
  setAutoUI(false);
  toast('Stopped', '');
}

function setAutoUI(on) {
  var btn = document.getElementById('btnAuto');
  var inner = document.getElementById('autoInner');
  var status = document.getElementById('autoStatus');

  if (on) {
    btn.classList.add('watching');
    inner.innerHTML = '<span class="pulse"></span><div class="auto-text"><div class="auto-main">Watching...</div><div class="auto-sub">CLICK TO STOP</div></div>';
    status.textContent = 'Monitoring duck.ai — will auto-summarize when you chat';
    status.className = 'on';
  } else {
    btn.classList.remove('watching');
    inner.innerHTML = '<span style="font-size:22px;position:relative;z-index:1;">⚡</span><div class="auto-text"><div class="auto-main">Auto</div><div class="auto-sub">CLICK TO OPEN DUCK.AI</div></div>';
    status.textContent = 'Opens duck.ai in incognito + auto-summarizes';
    status.className = '';
  }
}

// ── Duck tab helpers ──────────────────────────────────────────────────────────
function findDuckTab() {
  return new Promise(function(resolve) {
    chrome.tabs.query({ url: 'https://duck.ai/*' }, function(tabs) {
      resolve(tabs && tabs.length > 0 ? tabs[0].id : null);
    });
  });
}

async function checkDuckTab() {
  var tabId = await findDuckTab();
  if (tabId) {
    activeDuckTabId = tabId;
    setDuckStatus(true);
  } else {
    setDuckStatus(false);
  }
}

function setDuckStatus(found) {
  var el = document.getElementById('sumStatus');
  var btn = document.getElementById('btnSum');
  if (found) {
    el.textContent = '✓ duck.ai tab found — ready to summarize';
    el.className = 'ready';
    btn.disabled = false;
  } else {
    el.textContent = 'Click Auto to open duck.ai first';
    el.className = '';
    btn.disabled = true;
  }
}

// ── Summarize ─────────────────────────────────────────────────────────────────
async function doSummarize() {
  if (!activeDuckTabId) { toast('No duck.ai tab found', 'err'); return; }
  var text = await getConversation(activeDuckTabId);
  if (!text || text.length < 20) { toast('No conversation yet — chat a bit first', 'err'); return; }
  await runSummarize(text);
}

async function runSummarize(text) {
  var btn = document.getElementById('btnSum');
  btn.textContent = 'Summarizing...';
  btn.disabled = true;
  try {
    var result = await callCohere(text);
    summaries.unshift(result);
    await saveSummaries(summaries);
    renderList();
    toast('Summary saved!', 'ok');
  } catch(e) {
    toast(e.message, 'err');
  } finally {
    btn.textContent = 'Summarize with Cohere';
    btn.disabled = false;
  }
}

function getConversation(tabId) {
  return new Promise(function(resolve) {
    chrome.tabs.sendMessage(tabId, { type: 'get_conversation' }, function(res) {
      if (chrome.runtime.lastError || !res) {
        chrome.scripting.executeScript({ target: { tabId: tabId }, files: ['content.js'] }, function() {
          setTimeout(function() {
            chrome.tabs.sendMessage(tabId, { type: 'get_conversation' }, function(res2) {
              resolve(res2 ? res2.conversation : '');
            });
          }, 800);
        });
      } else {
        resolve(res.conversation || '');
      }
    });
  });
}

// ── Cohere Chat API (v2) ──────────────────────────────────────────────────────
async function callCohere(text) {
  var stored = await chrome.storage.local.get('cohereApiKey');
  var apiKey = stored.cohereApiKey;
  if (!apiKey) throw new Error('Add your Cohere key in Settings ⚙');

  var res = await fetch('https://api.cohere.com/v2/chat', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ' + apiKey,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: 'command-r-08-2024',
      messages: [
        {
          role: 'system',
          content: 'You summarize AI conversations. Reply only with valid JSON in this exact format, no markdown, no backticks: {"title":"short title max 8 words","summary":"full summary paragraph","keyPoints":["point 1","point 2","point 3"]}'
        },
        {
          role: 'user',
          content: 'Summarize this conversation:\n\n' + text.slice(0, 100000)
        }
      ],
      max_tokens: 1000
    })
  });

  if (!res.ok) {
    var err = await res.json().catch(function() { return {}; });
    throw new Error('Cohere: ' + (err.message || res.status));
  }

  var data = await res.json();
  var raw = data.message.content[0].text || '';

  var parsed;
  try {
    parsed = JSON.parse(raw.replace(/```json|```/g, '').trim());
  } catch(e) {
    parsed = { title: 'Chat Summary', summary: raw, keyPoints: [] };
  }

  return {
    id: Date.now().toString(),
    title: parsed.title || 'Chat Summary',
    summary: parsed.summary || raw,
    keyPoints: parsed.keyPoints || [],
    createdAt: new Date().toISOString()
  };
}

// ── Test key ──────────────────────────────────────────────────────────────────
async function testKey() {
  var key = document.getElementById('cohereKey').value.trim();
  if (!key) { toast('Paste a key first', 'err'); return; }
  await chrome.storage.local.set({ cohereApiKey: key });
  try {
    var res = await fetch('https://api.cohere.com/v2/chat', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + key,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'command-r-08-2024',
        messages: [{ role: 'user', content: 'say ok' }],
        max_tokens: 5
      })
    });
    var el = document.getElementById('keyStatus');
    if (res.ok) {
      el.textContent = '✓ Key works!';
      el.className = 'ok';
      toast('Connected!', 'ok');
    } else {
      var d = await res.json().catch(function() { return {}; });
      el.textContent = '✗ ' + (d.message || 'Invalid key — status ' + res.status);
      el.className = 'err';
    }
  } catch(e) {
    toast(e.message, 'err');
  }
}

// ── Summary list ──────────────────────────────────────────────────────────────
function renderList() {
  var list = document.getElementById('sumList');
  if (!summaries.length) {
    list.innerHTML = '<div class="empty">No summaries yet</div>';
    return;
  }
  list.innerHTML = summaries.map(function(s) {
    return '<div class="card" data-id="' + s.id + '">' +
      '<div class="card-title">' + esc(s.title) + '</div>' +
      '<div class="card-preview">' + esc(s.summary) + '</div>' +
      '<div class="card-meta">' +
        '<div class="card-time">' + fmt(s.createdAt) + '</div>' +
        '<div class="card-btns">' +
          '<button class="bx copy-btn" data-id="' + s.id + '">Copy</button>' +
          '<button class="bx d del-btn" data-id="' + s.id + '">Del</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('');

  list.querySelectorAll('.card').forEach(function(card) {
    card.addEventListener('click', function() { openDetail(card.dataset.id); });
  });
  list.querySelectorAll('.copy-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) { e.stopPropagation(); copyById(btn.dataset.id); });
  });
  list.querySelectorAll('.del-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) { e.stopPropagation(); delById(btn.dataset.id); });
  });
}

function openDetail(id) {
  currentDetail = summaries.find(function(s) { return s.id === id; });
  if (!currentDetail) return;
  document.getElementById('detailTitle').textContent = currentDetail.title;
  var html = '';
  if (currentDetail.summary) {
    html += '<div class="d-section"><div class="d-label">Summary</div><div class="d-text">' + esc(currentDetail.summary) + '</div></div>';
  }
  if (currentDetail.keyPoints && currentDetail.keyPoints.length) {
    html += '<div class="d-section"><div class="d-label">Key Points</div>' +
      currentDetail.keyPoints.map(function(p) { return '<div class="kp">' + esc(p) + '</div>'; }).join('') +
    '</div>';
  }
  document.getElementById('detailBody').innerHTML = html;
  showScreen('screenDetail');
}

function buildText(s) {
  var t = 'PORTAL SUMMARY\n==============\n' + s.title + '\n' + fmt(s.createdAt) + '\n\nSUMMARY:\n' + s.summary + '\n';
  if (s.keyPoints && s.keyPoints.length) {
    t += '\nKEY POINTS:\n' + s.keyPoints.map(function(p) { return '• ' + p; }).join('\n') + '\n';
  }
  return t;
}

function copyDetail() {
  if (currentDetail) navigator.clipboard.writeText(buildText(currentDetail)).then(function() { toast('Copied!', 'ok'); });
}
function copyById(id) {
  var s = summaries.find(function(x) { return x.id === id; });
  if (s) navigator.clipboard.writeText(buildText(s)).then(function() { toast('Copied!', 'ok'); });
}
function downloadDetail() {
  if (!currentDetail) return;
  var blob = new Blob([buildText(currentDetail)], { type: 'text/plain' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'summary-' + Date.now() + '.txt';
  a.click();
  URL.revokeObjectURL(a.href);
  toast('Downloaded', 'ok');
}
async function delById(id) {
  summaries = summaries.filter(function(s) { return s.id !== id; });
  await saveSummaries(summaries);
  renderList();
}
async function deleteDetail() {
  if (!currentDetail) return;
  await delById(currentDetail.id);
  showMain();
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function showSettings() {
  var stored = await chrome.storage.local.get('cohereApiKey');
  var el = document.getElementById('cohereKey');
  el.value = '';
  el.placeholder = stored.cohereApiKey ? 'Key saved — paste to replace' : 'Paste your key...';
  document.getElementById('keyStatus').textContent = '';
  document.getElementById('keyStatus').className = '';
  showScreen('screenSettings');
}

async function saveSettings() {
  var key = document.getElementById('cohereKey').value.trim();
  if (key) await chrome.storage.local.set({ cohereApiKey: key });
  toast('Saved', 'ok');
  showMain();
}

// ── Screens ───────────────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(function(s) { s.classList.remove('active'); });
  document.getElementById(id).classList.add('active');
}
function showMain() { showScreen('screenMain'); }

// ── Storage ───────────────────────────────────────────────────────────────────
async function loadSummaries() {
  var stored = await chrome.storage.local.get('summaries');
  return stored.summaries || [];
}
async function saveSummaries(list) {
  await chrome.storage.local.set({ summaries: list.slice(0, 50) });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function fmt(iso) {
  if (!iso) return '';
  var d = new Date(iso);
  return d.toLocaleDateString('en', { month: 'short', day: 'numeric' }) + ' · ' +
    d.toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', hour12: true });
}
function toast(msg, type) {
  var ex = document.querySelector('.toast');
  if (ex) ex.remove();
  var el = document.createElement('div');
  el.className = 'toast' + (type === 'ok' ? ' ok' : type === 'err' ? ' err' : '');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(function() {
    el.style.opacity = '0';
    el.style.transition = 'opacity .2s';
    setTimeout(function() { el.remove(); }, 200);
  }, 2500);
}
