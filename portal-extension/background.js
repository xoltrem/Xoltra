chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg.type === 'open_duck') {
    chrome.windows.create({ url: 'https://duck.ai/', incognito: true }, function(win) {
      if (chrome.runtime.lastError) {
        chrome.tabs.create({ url: 'https://duck.ai/' }, function() {
          sendResponse({ ok: true, incognito: false });
        });
      } else {
        sendResponse({ ok: true, incognito: true });
      }
    });
    return true;
  }
});
