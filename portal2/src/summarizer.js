const fetch = require('node-fetch');
const storage = require('./storage');

async function summarize(content) {
  const settings = storage.getSettings();
  const apiKey = settings.cohereApiKey;
  if (!apiKey) throw new Error('No Cohere API key set — add it in Settings');

  const res = await fetch('https://api.cohere.com/v2/chat', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'command-r-plus',
      messages: [
        {
          role: 'system',
          content: `You summarize conversations. Reply ONLY with valid JSON, no markdown, no backticks:
{"title":"short title max 8 words","summary":"full summary","keyPoints":["point 1","point 2"],"codeSnippets":["any code blocks if present"]}`
        },
        { role: 'user', content: `Summarize this:\n\n${content}` }
      ],
      max_tokens: 1500,
      temperature: 0.3
    })
  });

  if (!res.ok) throw new Error(`Cohere error ${res.status}: ${await res.text()}`);
  const data = await res.json();
  const text = data.message?.content?.[0]?.text || '';

  try {
    return JSON.parse(text.replace(/```json|```/g, '').trim());
  } catch {
    return { title: 'Chat Summary', summary: text, keyPoints: [], codeSnippets: [] };
  }
}

async function testKey() {
  const settings = storage.getSettings();
  if (!settings.cohereApiKey) return { ok: false, error: 'No key set' };
  try {
    const res = await fetch('https://api.cohere.com/v2/chat', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${settings.cohereApiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'command-r-plus', messages: [{ role: 'user', content: 'hi' }], max_tokens: 5 })
    });
    return { ok: res.ok, status: res.status };
  } catch (e) { return { ok: false, error: e.message }; }
}

module.exports = { summarize, testKey };
