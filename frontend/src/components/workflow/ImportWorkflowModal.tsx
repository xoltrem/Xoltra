'use client';
import { useState, useRef, useEffect } from 'react';
import { X, Upload, Sparkles, Loader2, Check, XCircle, ArrowRight, AlertTriangle, PartyPopper } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { parseWorkflowImport, compileImportSteps, createWorkflow } from '@/lib/api';
import { notify } from '@/lib/notifications';
import { useWorkflowCanvasStore } from '@/stores';

interface ProposedStep {
  step_index: number;
  label: string;
  node_type: string;
  params: Record<string, unknown>;
  ai_prompt_template: string | null;
  why: string;
  source_step_label?: string | null;
  fidelity: 'exact' | 'approximate';
  fidelity_note?: string | null;
}

interface ImportResult {
  source_detected: 'n8n' | 'make' | 'zapier' | 'freeform';
  original_step_count: number;
  steps: ProposedStep[];
  warnings: string[];
}

type Decision = 'pending' | 'accepted' | 'discarded';

const SOURCE_LABEL: Record<string, string> = {
  n8n: 'n8n export',
  make: 'Make.com blueprint',
  zapier: 'Zapier-style export',
  freeform: 'plain description',
};

interface ImportWorkflowModalProps {
  open: boolean;
  onClose: () => void;
}

export function ImportWorkflowModal({ open, onClose }: ImportWorkflowModalProps) {
  const [stage, setStage] = useState<'input' | 'parsing' | 'review' | 'saving' | 'done'>('input');
  const [sourceText, setSourceText] = useState('');
  const [result, setResult] = useState<ImportResult | null>(null);
  const [revealedCount, setRevealedCount] = useState(0);
  const [decisions, setDecisions] = useState<Record<number, Decision>>({});
  const [error, setError] = useState<string | null>(null);
  const [workflowName, setWorkflowName] = useState('Imported Workflow');
  const conversationIdRef = useRef<string>(crypto.randomUUID());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { pushState, nodes, edges } = useWorkflowCanvasStore();

  useEffect(() => {
    if (!open) {
      // Reset for next time this is opened, but only after it's closed —
      // no point wiping state while the user can still see it.
      const t = setTimeout(() => {
        setStage('input');
        setSourceText('');
        setResult(null);
        setRevealedCount(0);
        setDecisions({});
        setError(null);
        setWorkflowName('Imported Workflow');
        conversationIdRef.current = crypto.randomUUID();
      }, 300);
      return () => clearTimeout(t);
    }
  }, [open]);

  // Reveal accepted-by-default steps one at a time, like watching it get built.
  useEffect(() => {
    if (stage !== 'review' || !result) return;
    if (revealedCount >= result.steps.length) return;
    const t = setTimeout(() => {
      const step = result.steps[revealedCount];
      setDecisions(prev => ({ ...prev, [step.step_index]: prev[step.step_index] ?? 'accepted' }));
      setRevealedCount(c => c + 1);
    }, 550);
    return () => clearTimeout(t);
  }, [stage, result, revealedCount]);

  const handleFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => setSourceText(String(reader.result || ''));
    reader.readAsText(file);
  };

  const handleParse = async () => {
    if (!sourceText.trim()) return;
    setStage('parsing');
    setError(null);
    try {
      const res: ImportResult = await parseWorkflowImport(sourceText, conversationIdRef.current);
      setResult(res);
      setRevealedCount(0);
      setDecisions({});
      setStage('review');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Import failed');
      setStage('input');
    }
  };

  const toggleDecision = (stepIndex: number, decision: Decision) => {
    setDecisions(prev => ({ ...prev, [stepIndex]: decision }));
  };

  const acceptedSteps = () =>
    (result?.steps || []).filter(s => decisions[s.step_index] === 'accepted');

  const handleSave = async () => {
    const accepted = acceptedSteps();
    if (accepted.length === 0) return;
    setStage('saving');
    setError(null);
    try {
      const { graph } = await compileImportSteps(accepted);
      pushState({ nodes: [...nodes, ...graph.nodes], edges: [...edges, ...graph.edges] });
      await createWorkflow({ name: workflowName.trim() || 'Imported Workflow', status: 'draft', graph });
      notify('Workflow imported', `${accepted.length} step${accepted.length === 1 ? '' : 's'} rebuilt in Xoltra.`);
      setStage('done');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
      setStage('review');
    }
  };

  if (!open) return null;

  const allRevealed = result ? revealedCount >= result.steps.length : false;
  const acceptedCount = Object.values(decisions).filter(d => d === 'accepted').length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl max-h-[85vh] flex flex-col bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-2 px-5 py-4 border-b border-[var(--color-border-main)] shrink-0">
          <Upload className="w-4 h-4 text-[var(--color-accent)]" />
          <div className="flex-1">
            <div className="text-sm font-medium text-[var(--color-text-primary)]">Rebuild an existing automation</div>
            <div className="text-[10px] text-[var(--color-text-secondary)]">
              Paste a Zapier/Make/n8n export, or just describe it
            </div>
          </div>
          <button onClick={onClose} className="text-[var(--color-text-secondary)] hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {stage === 'input' && (
            <div className="space-y-3">
              <textarea
                value={sourceText}
                onChange={e => setSourceText(e.target.value)}
                placeholder={`Paste an n8n export, a Make.com blueprint, or just describe it:\n\n"When a new row is added to my Google Sheet, use AI to write a one-line summary and post it to our Slack channel."`}
                rows={8}
                className="w-full bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2.5 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40 resize-none font-mono"
              />
              <div className="flex items-center justify-between">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="text-xs text-[var(--color-text-secondary)] hover:text-white transition-colors flex items-center gap-1.5"
                >
                  <Upload className="w-3 h-3" /> or upload a file
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json,.txt"
                  className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
                />
              </div>
              {error && (
                <div className="flex items-start gap-2 text-xs text-[var(--color-error)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/20 rounded-[var(--radius-global)] px-3 py-2">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  {error}
                </div>
              )}
            </div>
          )}

          {stage === 'parsing' && (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
              <Loader2 className="w-6 h-6 animate-spin text-[var(--color-accent)]" />
              <div className="text-sm text-[var(--color-text-primary)]">Reading your automation...</div>
              <div className="text-xs text-[var(--color-text-secondary)] max-w-[320px]">
                Mapping each step onto Xoltra&apos;s real node types, not just pattern-matching names.
              </div>
            </div>
          )}

          {(stage === 'review' || stage === 'saving') && result && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs text-[var(--color-text-secondary)]">
                <span>
                  Detected: <span className="text-[var(--color-text-primary)] font-medium">{SOURCE_LABEL[result.source_detected]}</span>
                  {' · '}{result.original_step_count} step{result.original_step_count === 1 ? '' : 's'} found
                </span>
                <span>{revealedCount}/{result.steps.length} rebuilt</span>
              </div>

              {/* progress bar */}
              <div className="h-1 bg-[var(--color-panel-200)] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[var(--color-accent)] transition-all duration-500 ease-out"
                  style={{ width: `${result.steps.length ? (revealedCount / result.steps.length) * 100 : 0}%` }}
                />
              </div>

              {result.warnings.length > 0 && (
                <div className="flex items-start gap-2 text-[11px] text-[var(--color-text-secondary)] bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-yellow-500" />
                  <div>{result.warnings.join(' ')}</div>
                </div>
              )}

              <div className="space-y-2">
                {result.steps.slice(0, revealedCount).map((step, i) => {
                  const decision = decisions[step.step_index] ?? 'accepted';
                  return (
                    <div
                      key={step.step_index}
                      className={cn(
                        "border rounded-[var(--radius-global)] p-3 transition-all duration-300 animate-in fade-in slide-in-from-bottom-1",
                        decision === 'accepted'
                          ? "border-[var(--color-accent)]/30 bg-[var(--color-accent)]/[0.04]"
                          : "border-[var(--color-border-main)] bg-[var(--color-panel-200)] opacity-50"
                      )}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-[10px] font-mono text-[var(--color-text-secondary)] shrink-0">
                            {i + 1}.
                          </span>
                          <span className="text-xs font-medium text-[var(--color-text-primary)] truncate">
                            {step.label}
                          </span>
                          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#151515] border border-[var(--color-border-main)] text-[var(--color-text-secondary)] shrink-0">
                            {step.node_type}
                          </span>
                          {step.fidelity === 'approximate' && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 shrink-0">
                              approximate
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => toggleDecision(step.step_index, 'accepted')}
                            className={cn("w-6 h-6 rounded flex items-center justify-center transition-colors",
                              decision === 'accepted' ? "bg-[var(--color-accent)] text-black" : "text-[var(--color-text-secondary)] hover:text-white")}
                            title="Keep this step"
                          >
                            <Check className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => toggleDecision(step.step_index, 'discarded')}
                            className={cn("w-6 h-6 rounded flex items-center justify-center transition-colors",
                              decision === 'discarded' ? "bg-[var(--color-error)] text-white" : "text-[var(--color-text-secondary)] hover:text-white")}
                            title="Skip this step"
                          >
                            <XCircle className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                      <p className="text-[11px] text-[var(--color-text-secondary)] leading-relaxed">{step.why}</p>
                      {step.fidelity_note && (
                        <p className="text-[10px] text-yellow-500/80 mt-1">{step.fidelity_note}</p>
                      )}
                    </div>
                  );
                })}
              </div>

              {!allRevealed && (
                <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Rebuilding next step...
                </div>
              )}

              {allRevealed && (
                <div className="pt-2 border-t border-[var(--color-border-main)] flex items-center gap-2">
                  <input
                    value={workflowName}
                    onChange={e => setWorkflowName(e.target.value)}
                    placeholder="Workflow name"
                    className="flex-1 bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-accent)]/40"
                  />
                  <Button
                    size="sm"
                    disabled={acceptedCount === 0 || stage === 'saving'}
                    onClick={handleSave}
                    className="gap-1.5 shrink-0"
                  >
                    {stage === 'saving' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ArrowRight className="w-3.5 h-3.5" />}
                    Save {acceptedCount} step{acceptedCount === 1 ? '' : 's'} to canvas
                  </Button>
                </div>
              )}

              {error && (
                <div className="flex items-start gap-2 text-xs text-[var(--color-error)] bg-[var(--color-error)]/10 border border-[var(--color-error)]/20 rounded-[var(--radius-global)] px-3 py-2">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  {error}
                </div>
              )}
            </div>
          )}

          {stage === 'done' && (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
              <PartyPopper className="w-6 h-6 text-[var(--color-accent)]" />
              <div className="text-sm text-[var(--color-text-primary)]">Rebuilt and saved</div>
              <p className="text-xs text-[var(--color-text-secondary)] max-w-[320px]">
                Every step is logged in the audit trail — open Settings → Admin to see exactly what ran and why.
              </p>
              <Button size="sm" onClick={onClose} className="mt-2">Done</Button>
            </div>
          )}
        </div>

        {/* Footer action for the input stage */}
        {stage === 'input' && (
          <div className="p-4 border-t border-[var(--color-border-main)] shrink-0 flex justify-end">
            <Button size="sm" disabled={!sourceText.trim()} onClick={handleParse} className="gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              Rebuild it
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
