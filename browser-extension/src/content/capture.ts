/**
 * capture.ts — page-context extraction, injected ON DEMAND via
 * chrome.scripting when the user asks for it (side panel button, context
 * menu, or Alt+Shift+X). Never runs persistently on pages: no ambient DOM
 * access, no keylogging surface, nothing to audit on every site.
 *
 * Reads only what a human skimming the page would: title, meta description,
 * selection, headings, and a bounded main-text excerpt. Explicitly skips
 * input/textarea values so form data (passwords, cards) can never leak into
 * a capture.
 */
import type { PageContext } from '../shared/types';

const EXCERPT_LIMIT = 4000; // chars — bounded payload, enough for LLM context
const HEADING_LIMIT = 12;

function visibleText(el: Element): string {
  // innerText respects visibility/display, unlike textContent.
  return (el as HTMLElement).innerText?.trim() ?? '';
}

function pickMainElement(): Element {
  // Prefer semantic containers; fall back to body.
  return (
    document.querySelector('main') ||
    document.querySelector('article') ||
    document.querySelector('[role="main"]') ||
    document.body
  );
}

function extract(): PageContext {
  const main = pickMainElement();
  const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
    .map(visibleText)
    .filter(Boolean)
    .slice(0, HEADING_LIMIT);

  const rawText = visibleText(main).replace(/\s+/g, ' ').trim();

  return {
    url: location.href,
    title: document.title,
    selection: String(getSelection() ?? '').trim().slice(0, 2000),
    description:
      document.querySelector<HTMLMetaElement>('meta[name="description"]')?.content?.trim() ?? '',
    headings,
    excerpt: rawText.slice(0, EXCERPT_LIMIT),
    stats: {
      links: document.links.length,
      forms: document.forms.length,
      images: document.images.length,
      words: rawText ? rawText.split(' ').length : 0,
    },
    capturedAt: new Date().toISOString(),
  };
}

try {
  void chrome.runtime.sendMessage({ type: 'PAGE_CONTEXT_RESULT', context: extract() });
} catch {
  // Extension context invalidated (reload while injected) — nothing to do.
}
