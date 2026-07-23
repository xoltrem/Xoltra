/**
 * service-worker.ts — MV3 background for the Xoltra Companion.
 *
 * Responsibilities (kept deliberately small — MV3 workers are ephemeral and
 * everything here must survive being killed and restarted):
 *   - open the side panel from the toolbar action
 *   - on-demand page capture: inject content-capture.js into the active tab
 *     (action button / context menu / Alt+Shift+X), store the result in
 *     chrome.storage.session, broadcast CONTEXT_UPDATED
 *   - context menu: "Capture page for Xoltra" + "Send selection to Xoltra"
 *
 * All API calls happen in the extension pages themselves (side panel /
 * options); the worker holds no in-memory state that matters.
 */
import type { ExtMessage } from '../shared/messages';
import { setPageContext } from '../shared/storage';
import type { PageContext } from '../shared/types';

// Toolbar click opens the side panel (Chrome 116+).
chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });

  chrome.contextMenus.create({
    id: 'xoltra-capture-page',
    title: 'Capture page for Xoltra',
    contexts: ['page'],
  });
  chrome.contextMenus.create({
    id: 'xoltra-capture-selection',
    title: 'Send selection to Xoltra',
    contexts: ['selection'],
  });
});

async function captureTab(tabId: number): Promise<{ ok: boolean; error?: string }> {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content-capture.js'],
    });
    // The script reports back via PAGE_CONTEXT_RESULT; nothing to await here.
    return { ok: true };
  } catch (e) {
    // Typical: chrome:// pages, Web Store, or missing host access.
    return { ok: false, error: e instanceof Error ? e.message : 'Cannot access this page' };
  }
}

async function captureActiveTab(): Promise<{ ok: boolean; error?: string }> {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id) return { ok: false, error: 'No active tab' };
  return captureTab(tab.id);
}

function broadcast(msg: ExtMessage): void {
  // Fire-and-forget to all extension pages; no listener is fine.
  void chrome.runtime.sendMessage(msg).catch(() => {});
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'xoltra-capture-page' || info.menuItemId === 'xoltra-capture-selection') {
    if (tab?.id) {
      void captureTab(tab.id);
      if (tab.windowId !== undefined) void chrome.sidePanel.open({ windowId: tab.windowId });
    }
  }
});

chrome.commands.onCommand.addListener((command) => {
  if (command === 'capture-page') void captureActiveTab();
});

chrome.runtime.onMessage.addListener((raw: unknown, _sender, sendResponse) => {
  const msg = raw as ExtMessage;
  if (!msg || typeof msg !== 'object' || !('type' in msg)) return;

  if (msg.type === 'CAPTURE_PAGE') {
    void captureActiveTab().then(sendResponse);
    return true; // async response
  }

  if (msg.type === 'PAGE_CONTEXT_RESULT') {
    const context = msg.context as PageContext;
    void setPageContext(context).then(() => {
      broadcast({ type: 'CONTEXT_UPDATED', context });
    });
    return;
  }

  if (msg.type === 'CLEAR_CONTEXT') {
    void setPageContext(null).then(() => {
      broadcast({ type: 'CONTEXT_UPDATED', context: null });
    });
    return;
  }
});
