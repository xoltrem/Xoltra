/**
 * AssistantView — chat with the Xoltra workflow assistant, with the captured
 * page context optionally woven into the message.
 *
 * Throttling is a hard requirement, not a nicety: the backend's per-user rate
 * limiter feeds moderation.record_violation, and a single burst past the
 * limit escalates into an account timeout. Sends are serialized and spaced
 * at least MIN_SEND_INTERVAL_MS apart.
 */
import { useEffect, useRef, useState } from 'react';
import { friendlyError, sendAssistantMessage } from '../../shared/api';
import type { PageContext } from '../../shared/types';

const MIN_SEND_INTERVAL_MS = 3000;

interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  proposedNode?: { label: string; category: string; actions: string[] } | null;
}

interface AssistantViewProps {
  pageContext: PageContext | null;
  webAppUrl: string;
}

function contextPreamble(ctx: PageContext): string {
  return [
    `[Page context] ${ctx.title} — ${ctx.url}`,
    ctx.selection && `Selected text: ${ctx.selection.slice(0, 500)}`,
    ctx.description && `Description: ${ctx.description}`,
    ctx.headings.length > 0 && `Headings: ${ctx.headings.slice(0, 6).join(' | ')}`,
  ].filter(Boolean).join('\n');
}

export function AssistantView({ pageContext, webAppUrl }: AssistantViewProps) {
  const [messages, setMessages] = useState<Message[]>([{
    id: 'welcome',
    role: 'assistant',
    text: pageContext
      ? `I can see the page you captured (“${pageContext.title}”). Describe the automation you want and I'll propose it step by step.`
      : 'Describe the automation you want — capture a page first if it should use what you are looking at.',
  }]);
  const [input, setInput] = useState('');
  const [useContext, setUseContext] = useState(true);
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(false);
  const lastSentAt = useRef(0);
  const conversationId = useRef(crypto.randomUUID());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy || cooldown) return;

    const sinceLast = Date.now() - lastSentAt.current;
    if (sinceLast < MIN_SEND_INTERVAL_MS) {
      setCooldown(true);
      setTimeout(() => setCooldown(false), MIN_SEND_INTERVAL_MS - sinceLast);
      return;
    }

    setInput('');
    setBusy(true);
    lastSentAt.current = Date.now();
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', text }]);

    const payload = useContext && pageContext ? `${contextPreamble(pageContext)}\n\n${text}` : text;

    try {
      const res = await sendAssistantMessage(payload, conversationId.current);
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: res.reply,
        proposedNode: res.proposed_node,
      }]);
    } catch (e: unknown) {
      setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'assistant', text: friendlyError(e) }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat grow" style={{ minHeight: 0, display: 'flex' }}>
      <div ref={scrollRef} className="col grow" style={{ overflowY: 'auto', gap: 8 }}>
        {messages.map(m => (
          <div key={m.id} style={{ display: 'flex', flexDirection: 'column' }}>
            <div className={`msg ${m.role}`}>{m.text}</div>
            {m.proposedNode && (
              <div className="proposed col" style={{ gap: 4, marginTop: 6 }}>
                <span className="tiny" style={{ color: 'var(--color-accent)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Proposed node
                </span>
                <span className="small" style={{ fontWeight: 600 }}>{m.proposedNode.label}</span>
                <div className="row wrap" style={{ gap: 4 }}>
                  {m.proposedNode.actions.map(a => (
                    <span key={a} className="tiny mono" style={{ padding: '2px 5px', background: '#151515', border: '1px solid var(--color-border-main)', borderRadius: 4 }}>
                      {a}
                    </span>
                  ))}
                </div>
                <a className="tiny" style={{ color: 'var(--color-accent)' }} href={`${webAppUrl}/workflows`} target="_blank" rel="noreferrer">
                  Build it in the full editor →
                </a>
              </div>
            )}
          </div>
        ))}
        {busy && <div className="row small muted"><span className="spinner" /> Thinking…</div>}
      </div>

      <div className="col" style={{ gap: 6, paddingTop: 8, borderTop: '1px solid var(--color-border-main)' }}>
        {pageContext && (
          <label className="row tiny muted" style={{ gap: 6, cursor: 'pointer' }}>
            <input type="checkbox" checked={useContext} onChange={e => setUseContext(e.target.checked)} />
            Include captured page (“{pageContext.title.slice(0, 40)}”)
          </label>
        )}
        <div className="row">
          <input
            className="input grow"
            placeholder="e.g. Summarize this page into an email"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') void send(); }}
            aria-label="Message the assistant"
          />
          <button className="btn btn-primary" onClick={send} disabled={busy || cooldown || !input.trim()}>
            {cooldown ? '…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}
