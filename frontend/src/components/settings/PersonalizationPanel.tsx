'use client';
import { useEffect, useState } from 'react';
import { Sparkles, RotateCcw, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { xoltra } from '@/lib/xoltra-ai';

const MODES = [
  { id: 'adaptive', label: 'Adaptive', desc: 'Learns 6 traits from how you write, every 4 messages.' },
  { id: 'custom', label: 'Custom', desc: 'Use your own system prompt instead of auto-learning.' },
  { id: 'off', label: 'Off', desc: 'Default assistant behavior — no personalization.' },
];

const TRAIT_LABELS: Record<string, string> = {
  vocabulary: 'Vocabulary', reasoning: 'Reasoning', communication: 'Communication', tone: 'Tone',
};

export function PersonalizationPanel() {
  const [state, setState] = useState(xoltra.getState());
  const [customPrompt, setCustomPrompt] = useState('');

  useEffect(() => {
    xoltra.init();
    setCustomPrompt(xoltra.getSettings().customPrompt || '');
    return xoltra.onChange((s: ReturnType<typeof xoltra.getState>) => setState(s));
  }, []);

  const setMode = async (mode: string) => {
    await xoltra.setSettings(mode === 'custom' ? { mode, customPrompt } : { mode });
  };

  const { traits, settings, extracting } = state;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold tracking-tight mb-1">AI Personalization</h2>
        <p className="text-sm text-[var(--color-text-secondary)]">
          Xoltra silently learns how you communicate every 4 messages and adapts to match.
        </p>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">Mode</h3>
        <div className="grid grid-cols-3 gap-2">
          {MODES.map(m => {
            const selected = settings.mode === m.id;
            return (
              <button
                key={m.id}
                onClick={() => setMode(m.id)}
                className={cn(
                  "text-center p-3 rounded-[var(--radius-global)] border transition-colors flex flex-col items-center",
                  selected
                    ? "border-[var(--color-accent)] bg-[var(--color-accent)]/[0.06]"
                    : "border-[var(--color-border-main)] bg-[var(--color-panel-100)] hover:border-[var(--color-border-hover)]"
                )}
              >
                <div className="text-sm font-medium text-[var(--color-text-primary)] mb-1">{m.label}</div>
                <p className="text-[11px] text-[var(--color-text-secondary)] leading-snug">{m.desc}</p>
              </button>
            );
          })}
        </div>
      </div>

      {settings.mode === 'custom' && (
        <div>
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-2">Custom Prompt</h3>
          <textarea
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            onBlur={() => xoltra.setSettings({ mode: 'custom', customPrompt })}
            rows={4}
            placeholder="You are..."
            className="w-full bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-3 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40 resize-none"
          />
        </div>
      )}

      {settings.mode === 'adaptive' && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Learned Profile</h3>
            {extracting && (
              <span className="flex items-center gap-1 text-[10px] text-[var(--color-accent)]">
                <Sparkles className="w-3 h-3 animate-pulse" /> updating...
              </span>
            )}
          </div>

          {!traits ? (
            <div className="p-4 border border-dashed border-[var(--color-border-main)] rounded-[var(--radius-global)] text-xs text-[var(--color-text-secondary)]">
              Nothing learned yet — send a few messages and Xoltra will start adapting.
            </div>
          ) : (
            <div className="p-4 border border-[var(--color-border-main)] rounded-[var(--radius-global)] bg-[var(--color-panel-100)] space-y-3">
              <div className="grid grid-cols-2 gap-3 text-center">
                {Object.entries(TRAIT_LABELS).map(([key, label]) => (
                  <div key={key}>
                    <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)] mb-0.5">{label}</div>
                    <div className="text-sm text-[var(--color-text-primary)] capitalize">{(traits as any)[key] || '—'}</div>
                  </div>
                ))}
              </div>
              {traits.interests?.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)] mb-1">Interests</div>
                  <div className="flex flex-wrap gap-1">
                    {traits.interests.map((i: string) => (
                      <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-[#151515] border border-[var(--color-border-main)] text-[var(--color-text-secondary)]">{i}</span>
                    ))}
                  </div>
                </div>
              )}
              {traits.expertise?.length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)] mb-1">Expertise</div>
                  <div className="flex flex-wrap gap-1">
                    {traits.expertise.map((i: string) => (
                      <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-[#151515] border border-[var(--color-border-main)] text-[var(--color-text-secondary)]">{i}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex gap-2 mt-3">
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => xoltra.resetTraits()}>
              <RotateCcw className="w-3.5 h-3.5" /> Reset Profile
            </Button>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => xoltra.clearHistory()}>
              <Trash2 className="w-3.5 h-3.5" /> Clear History
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
