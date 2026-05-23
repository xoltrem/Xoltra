function extractConversation() {
  var results = [];

  var selectors = [
    '[data-testid="message"]',
    '[class*="Message"]',
    '[class*="message"]',
    '[class*="ChatMessage"]',
    '[class*="Response"]',
    '[class*="UserMessage"]',
    '[class*="AIMessage"]',
    'article',
    '[role="article"]'
  ];

  for (var i = 0; i < selectors.length; i++) {
    var els = document.querySelectorAll(selectors[i]);
    if (els.length > 0) {
      els.forEach(function(el) {
        var text = el.innerText && el.innerText.trim();
        if (text && text.length > 3) results.push(text);
      });
      if (results.length > 0) break;
    }
  }

  // fallback — grab paragraphs from main area
  if (results.length === 0) {
    var main = document.querySelector('main') || document.body;
    var paras = main.querySelectorAll('p');
    paras.forEach(function(p) {
      var text = p.innerText && p.innerText.trim();
      if (text && text.length > 10) results.push(text);
    });
  }

  return results.join('\n\n');
}

chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (msg.type === 'get_conversation') {
    sendResponse({ conversation: extractConversation() });
  }
  return true;
});
