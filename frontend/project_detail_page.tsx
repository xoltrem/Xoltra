'use client';
import { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  FolderKanban, GitBranch, Upload, Loader2, Trash2, RefreshCw,
  CheckCircle2, XCircle, Clock, Layers, FileText, MessageSquare, Eye,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';
import {
  getProject, deleteProject, addGithubSource, addUploadSource,
  bootstrapProjectSession, Project, ProjectSource, ProjectCache, BootstrapPayload,
} from '@/lib/projectsApi';

const STATUS_STYLE: Record<string, { icon: any; color: string }> = {
  indexed: { icon: CheckCircle2, color: 'text-[var(--color-success)]' },
  pending: { icon: Clock, color: 'text-[var(--color-warning)]' },
  error: { icon: XCircle, color: 'text-[var(--color-error)]' },
};

function SourceRow({ source }: { source: ProjectSource }) {
  const style = STATUS_STYLE[source.status] || STATUS_STYLE.pending;
  const Icon = style.icon;
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 border-b border-[var(--color-border-main)] last:border-b-0 text-xs">
      {source.type === 'github' ? (
        <GitBranch className="w-3.5 h-3.5 text-[var(--color-text-secondary)] shrink-0" />
      ) : (
        <Upload className="w-3.5 h-3.5 text-[var(--color-text-secondary)] shrink-0" />
      )}
      <span className="flex-1 truncate text-[var(--color-text-primary)] font-mono">{source.ref}</span>
      <span className="text-[var(--color-text-secondary)]">{source.file_count} files</span>
      <span className={cn('flex items-center gap-1', style.color)}>
        <Icon className="w-3 h-3" /> {source.status}
      </span>
    </div>
  );
}

function AddGithubForm({ projectId, onAdded }: { projectId: string; onAdded: () => void }) {
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!url.trim()) return;
    setBusy(true);
    setError('');
    try {
      await addGithubSource(projectId, url.trim());
      setUrl('');
      onAdded();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-1.5 flex-1">
      <div className="flex gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder="https://github.com/owner/repo"
          className="flex-1 bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs font-mono text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40"
        />
        <Button size="sm" onClick={submit} disabled={busy || !url.trim()} className="gap-1.5 shrink-0">
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <GitBranch className="w-3.5 h-3.5" />}
          {busy ? 'Cloning...' : 'Clone'}
        </Button>
      </div>
      {error && <p className="text-[10px] text-[var(--color-error)]">{error}</p>}
    </div>
  );
}

function UploadButton({ projectId, onAdded }: { projectId: string; onAdded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setBusy(true);
    setError('');
    try {
      await addUploadSource(projectId, files);
      onAdded();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      <input ref={inputRef} type="file" multiple className="hidden" onChange={handleChange} />
      <Button
        size="sm"
        variant="outline"
        className="gap-1.5"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
        {busy ? 'Uploading...' : 'Upload files'}
      </Button>
      {error && <p className="text-[10px] text-[var(--color-error)]">{error}</p>}
    </div>
  );
}

function CacheSection({ cache }: { cache: ProjectCache | null }) {
  if (!cache || (!cache.structure_summary && !cache.key_docs_summary)) {
    return (
      <p className="text-xs text-[var(--color-text-secondary)]">
        No context indexed yet — add a source above.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {cache.structure_summary && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)] mb-1">
            Structure
          </div>
          <pre className="bg-[#0d0d0d] border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-3 text-[11px] font-mono text-[var(--color-text-primary)] whitespace-pre-wrap">
            {cache.structure_summary}
          </pre>
        </div>
      )}
      {cache.key_docs_summary && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)] mb-1">
            Key docs
          </div>
          <pre className="bg-[#0d0d0d] border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-3 text-[11px] font-mono text-[var(--color-text-primary)] whitespace-pre-wrap max-h-64 overflow-y-auto">
            {cache.key_docs_summary}
          </pre>
        </div>
      )}
    </div>
  );
}

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.id as string;

  const [project, setProject] = useState<Project | null>(null);
  const [sources, setSources] = useState<ProjectSource[]>([]);
  const [cache, setCache] = useState<ProjectCache | null>(null);
  const [error, setError] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [preview, setPreview] = useState<BootstrapPayload | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);

  const load = () => {
    getProject(projectId)
      .then((r) => {
        setProject(r.project);
        setSources(r.sources);
        setCache(r.cache);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const remove = async () => {
    if (!confirm(`Delete "${project?.name}"? This removes all sources and cached context.`)) return;
    try {
      await deleteProject(projectId);
      router.push('/projects');
    } catch (e: any) {
      setError(e.message);
    }
  };

  const openPreview = async () => {
    setPreviewOpen(true);
    setPreviewBusy(true);
    try {
      const r = await bootstrapProjectSession(projectId);
      setPreview(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setPreviewBusy(false);
    }
  };

  if (error && !project) {
    return <div className="p-6 text-sm text-[var(--color-error)]">{error}</div>;
  }
  if (!project) {
    return <div className="p-6 text-sm text-[var(--color-text-secondary)]">Loading...</div>;
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2 min-w-0">
          <FolderKanban className="w-5 h-5 text-[var(--color-accent)] shrink-0" />
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight truncate">{project.name}</h1>
            {project.goals && (
              <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{project.goals}</p>
            )}
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button size="sm" variant="outline" className="gap-1.5" onClick={openPreview}>
            <Eye className="w-3.5 h-3.5" /> Preview session context
          </Button>
          <Button size="sm" variant="destructive" className="gap-1.5" onClick={remove}>
            <Trash2 className="w-3.5 h-3.5" /> Delete
          </Button>
        </div>
      </div>

      {error && <div className="text-xs text-[var(--color-error)]">{error}</div>}

      <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-1.5 text-sm font-medium">
            <Layers className="w-3.5 h-3.5" /> Sources
          </div>
          <button onClick={load} className="text-[var(--color-text-secondary)] hover:text-white transition-colors">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 mb-3">
          <AddGithubForm projectId={projectId} onAdded={load} />
          <UploadButton projectId={projectId} onAdded={load} />
        </div>

        {sources.length === 0 ? (
          <p className="text-xs text-[var(--color-text-secondary)]">No sources yet.</p>
        ) : (
          <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] overflow-hidden">
            {sources.map((s) => (
              <SourceRow key={s.id} source={s} />
            ))}
          </div>
        )}
      </div>

      <div className="border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-4">
        <div className="flex items-center gap-1.5 text-sm font-medium mb-3">
          <FileText className="w-3.5 h-3.5" /> Context cache
        </div>
        <CacheSection cache={cache} />
      </div>

      {previewOpen && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4"
          onClick={() => setPreviewOpen(false)}
        >
          <div
            className="w-full max-w-lg max-h-[80vh] overflow-y-auto bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-1.5 text-sm font-medium mb-3">
              <MessageSquare className="w-3.5 h-3.5 text-[var(--color-accent)]" /> What a new chat loads automatically
            </div>
            {previewBusy ? (
              <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading...
              </div>
            ) : preview ? (
              <div className="space-y-3 text-xs">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)] mb-1">
                    Structure
                  </div>
                  <pre className="bg-[#0d0d0d] border border-[var(--color-border-main)] rounded p-2 font-mono whitespace-pre-wrap">
                    {preview.structure_summary || '—'}
                  </pre>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-secondary)] mb-1">
                    Recent conversation digests
                  </div>
                  {preview.conversation_digests?.length ? (
                    preview.conversation_digests.map((d, i) => (
                      <p key={i} className="text-[var(--color-text-secondary)] mb-1">
                        • {d.summary}
                      </p>
                    ))
                  ) : (
                    <p className="text-[var(--color-text-secondary)]">None yet.</p>
                  )}
                </div>
              </div>
            ) : null}
            <Button size="sm" variant="outline" className="mt-4 w-full" onClick={() => setPreviewOpen(false)}>
              Close
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
