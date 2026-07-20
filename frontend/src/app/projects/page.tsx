'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { FolderKanban, Plus, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { formatDate } from '@/lib/utils';
import { listProjects, createProject, Project } from '@/lib/projectsApi';

function CreateProjectForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [goals, setGoals] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError('');
    try {
      await createProject(name.trim(), goals.trim());
      setName('');
      setGoals('');
      setOpen(false);
      onCreated();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <Button className="gap-2" onClick={() => setOpen(true)}>
        <Plus className="w-4 h-4" /> New Project
      </Button>
    );
  }

  return (
    <div className="absolute right-6 top-16 z-20 w-80 bg-[var(--color-panel-100)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] p-4 shadow-2xl space-y-3">
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && submit()}
        placeholder="Project name"
        className="w-full bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40"
      />
      <textarea
        value={goals}
        onChange={(e) => setGoals(e.target.value)}
        placeholder="Goal or focus (optional)"
        rows={3}
        className="w-full bg-[var(--color-panel-200)] border border-[var(--color-border-main)] rounded-[var(--radius-global)] px-3 py-2 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-secondary)] focus:outline-none focus:border-[var(--color-accent)]/40 resize-none"
      />
      {error && <p className="text-xs text-[var(--color-error)]">{error}</p>}
      <div className="flex gap-2">
        <Button size="sm" className="flex-1 gap-1.5" onClick={submit} disabled={busy || !name.trim()}>
          {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />} Create
        </Button>
        <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState('');

  const load = () =>
    listProjects()
      .then((r) => setProjects(r.projects))
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto flex flex-col h-full space-y-6 relative">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-semibold mb-1 tracking-tight">Projects</h1>
          <p className="text-[var(--color-text-secondary)] text-sm">
            Consolidate repos, files, and conversations into a persistent workspace.
          </p>
        </div>
        <CreateProjectForm onCreated={load} />
      </div>

      {error && <div className="text-xs text-[var(--color-error)]">{error}</div>}

      {!projects && !error && (
        <div className="text-sm text-[var(--color-text-secondary)]">Loading...</div>
      )}

      {projects && projects.length === 0 && (
        <div className="flex-1 flex items-center justify-center border border-dashed border-[var(--color-border-main)] rounded-[var(--radius-global)] p-12 text-center">
          <div>
            <div className="w-12 h-12 bg-[var(--color-panel-100)] rounded-full flex items-center justify-center mb-4 mx-auto">
              <FolderKanban className="w-6 h-6 text-[var(--color-text-secondary)]" />
            </div>
            <h3 className="text-sm font-medium mb-1">No projects yet</h3>
            <p className="text-xs text-[var(--color-text-secondary)] max-w-[280px] mx-auto">
              Create one, then clone a repo or upload files to give Xoltra lasting context.
            </p>
          </div>
        </div>
      )}

      {projects && projects.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => router.push(`/projects/${p.id}`)}
              className="text-left p-4 border border-[var(--color-border-main)] rounded-[var(--radius-global)] bg-[var(--color-panel-100)] hover:border-[var(--color-border-hover)] transition-colors"
            >
              <div className="flex items-center gap-2 mb-1.5">
                <FolderKanban className="w-4 h-4 text-[var(--color-accent)]" />
                <span className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                  {p.name}
                </span>
              </div>
              {p.goals && (
                <p className="text-xs text-[var(--color-text-secondary)] line-clamp-2 mb-2">
                  {p.goals}
                </p>
              )}
              <p className="text-[10px] text-[var(--color-text-secondary)]">
                Updated {formatDate(p.updated_at)}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
