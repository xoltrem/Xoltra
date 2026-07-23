/**
 * messages.ts — the typed message protocol between extension surfaces.
 *
 * Flow for page capture:
 *   side panel ──CAPTURE_PAGE──▶ service worker
 *   service worker injects content-capture.js into the active tab
 *   capture script ──PAGE_CONTEXT_RESULT──▶ service worker
 *   service worker stores context ──CONTEXT_UPDATED──▶ all extension pages
 *
 * Everything crossing a boundary is declared here; no stringly-typed
 * `sendMessage` calls anywhere else.
 */
import type { PageContext } from './types';

export type ExtMessage =
  | { type: 'CAPTURE_PAGE' }                                  // panel -> SW
  | { type: 'PAGE_CONTEXT_RESULT'; context: PageContext }     // content -> SW
  | { type: 'CONTEXT_UPDATED'; context: PageContext | null }  // SW -> pages (broadcast)
  | { type: 'CLEAR_CONTEXT' };                                // panel -> SW

export interface CaptureResponse {
  ok: boolean;
  error?: string;
}

export function sendMessage<T = unknown>(msg: ExtMessage): Promise<T> {
  return chrome.runtime.sendMessage(msg);
}

/** Subscribe to broadcasts; returns an unsubscribe function. */
export function onMessage(handler: (msg: ExtMessage) => void): () => void {
  const listener = (msg: unknown) => {
    if (msg && typeof msg === 'object' && 'type' in msg) handler(msg as ExtMessage);
  };
  chrome.runtime.onMessage.addListener(listener);
  return () => chrome.runtime.onMessage.removeListener(listener);
}
