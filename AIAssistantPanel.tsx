'use client';
import { useState, useRef, useEffect } from 'react';
import { X, Send, Sparkles, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { sendAssistantMessage } from '@/lib/api';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  // If the assistant proposed a node, its manifest is attached here for review
  // per the PRD's "AI-Generated Node Review" flow — shown, not silently added.
  proposedNode?: {
    label: string;
    category: string;
    actions: string[];
  };
}

interface AIAssistantPanelProps {
  open: boolean;
  onClose: () => void;
  onAcceptNode?: (node: any) => void;
}

export function AIAssistantPanel({ open, onClose, onAcceptNode }: AIAssistantPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    { id: 'welcome', role: 'assistant', text: "Describe what you want this workflow to do — I'll build it step by step." }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput('');
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role: 'user', text }]);
    setLoading(true);

    try {
      const res = await sendAssistantMessage(text);
      // Expected shape: { reply: string, proposed_node?: { label, category, actions } }
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: res.reply,
        proposedNode: res.proposed_node,
      }]);
    } catch (e: any) {
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: `Something went wrong: ${e.message}`,
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!open) return null;

  return (
    <div className="fixed right-4 bottom-4 z-40 w-[360px] h-[520px] flex flex-col bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] shadow-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--color-border-main)] shrink-0">
        <Sparkles className="w-4 h-4 text-[var(--color-accent)]" />
        <div className="flex-1">
          <div className="text-sm font-medium text-[var(--color-text-primary)]">Workflow Assistant</div>
          <div className="text-[10px] text-[var(--color-text-secondary)]">Describe it, I'll build it</div>
        </div>
        <button
          onClick={onClose}
          className="text-[var(--color-text-secondary)] hover:text-white transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.map(m => (
          <div key={m.id} className={cn("flex flex-col", m.role === 'user' ? "items-end" : "items-start")}>
            <div className={cn(
              "max-w-[85%] rounded-[var(--radius-global)] px-3 py-2 text-xs leading-relaxed",
              m.role === 'user'
                ? "bg-[var(--color-panel-200)] text-[var(--color-text-primary)]"
                : "bg-[#151515] border border-[var(--color-border-main)] text-[var(--color-text-primary)]"
            )}>
              {m.text}
            </div>

            {/* AI-generated node review — required before it reaches the canvas */}
            {m.proposedNode && (
              <div className="mt-2 max-w-[85%] w-full border border-dashed border-[var(--color-accent)]/40 rounded-[var(--radius-global)] p-3 bg-[var(--color-accent)]/[0.04]">
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-accent)] font-medium mb-1">
                  Proposed Node
                </div>
                <div className="text-xs font-medium text-[var(--color-text-primary)] mb-1">
                  {m.proposedNode.label}
                </div>
                <div className="flex flex-wrap gap-1 mb-2">
                  {m.proposedNode.actions.map(a => (
                    <span key={a} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#151515] border border-[var(--color-border-main)] text-[var(--color-text-secondary)]">
                      {a}
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => onAcceptNode?.(m.proposedNode)}
                    className="flex-1 text-xs px-2 py-1.5 rounded bg-[var(--color-accent)] text-black font-medium hover:opacity-90 transition-opacity"
                  >
                    Add to Canvas
                  </button>
                  <button
                    className="text-xs px-2 py-1.5 rounded border border-[var(--color-border-main)] text-[var(--color-text-secondary)] hover:text-white transition-colors"
                  >
                    Discard
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
            <Loader2 className="w-3 h-3 animate-spin" />
            Thinking...
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-3 border-t border-[var(--color-border-main)] shrink-0">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. Send a Slack message when a file is uploaded"
            className="flex-1 bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40"
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="w-8 h-8 shrink-0 flex items-center justify-center rounded-[var(--radius-global)] bg-[var(--color-accent)] text-black disabled:opacity-30 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
