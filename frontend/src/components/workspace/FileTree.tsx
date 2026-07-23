'use client';
/**
 * FileTree.tsx — workspace explorer tree with expand/collapse,
 * file open, and context actions (new file/folder, rename, delete).
 */
import { useState } from 'react';
import {
  ChevronRight, ChevronDown, FileText, Folder, FolderOpen,
  FilePlus, FolderPlus, Trash2, PenLine, RefreshCw, Search, Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  TreeNode, SearchResult, createWorkspaceFolder, deleteWorkspacePath,
  moveWorkspacePath, writeWorkspaceFile, searchWorkspace, searchWorkspaceSemantic,
} from '@/lib/workspaceApi';
import { useWorkspaceStore } from '@/stores/workspace';

function TreeRow({ node, depth }: { node: TreeNode; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const { activePath, openFile, fetchTree, log } = useWorkspaceStore();
  const isDir = node.type === 'dir';
  const isActive = activePath === node.path;

  const rename = async () => {
    const to = window.prompt(`Rename/move ${node.path} to:`, node.path);
    if (!to || to === node.path) return;
    try {
      await moveWorkspacePath(node.path, to);
      log('success', `Moved ${node.path} -> ${to} (imports updated)`);
      fetchTree();
    } catch (e) { log('error', (e as Error).message); }
  };

  const remove = async () => {
    if (!window.confirm(`Delete ${node.path}? A checkpoint is created so this can be undone.`)) return;
    try {
      await deleteWorkspacePath(node.path);
      log('warn', `Deleted ${node.path}`);
      fetchTree();
    } catch (e) { log('error', (e as Error).message); }
  };

  return (
    <div>
      <div
        className={cn(
          'group flex items-center gap-1 px-2 py-1 text-[13px] rounded cursor-pointer select-none',
          isActive
            ? 'bg-[var(--color-panel-200)] text-white'
            : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-panel-200)]/50 hover:text-white',
        )}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => (isDir ? setOpen(!open) : openFile(node.path))}
      >
        {isDir ? (
          <>
            {open ? <ChevronDown className="w-3.5 h-3.5 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 shrink-0" />}
            {open ? <FolderOpen className="w-3.5 h-3.5 shrink-0 text-[var(--color-accent)]" /> : <Folder className="w-3.5 h-3.5 shrink-0 text-[var(--color-accent)]" />}
          </>
        ) : (
          <FileText className="w-3.5 h-3.5 shrink-0 ml-[18px]" />
        )}
        <span className="truncate flex-1">{node.name}</span>
        <span className="hidden group-hover:flex items-center gap-1">
          <button title="Rename / move" onClick={(e) => { e.stopPropagation(); rename(); }}
            className="p-0.5 hover:text-white"><PenLine className="w-3 h-3" /></button>
          <button title="Delete" onClick={(e) => { e.stopPropagation(); remove(); }}
            className="p-0.5 hover:text-red-400"><Trash2 className="w-3 h-3" /></button>
        </span>
      </div>
      {isDir && open && node.children?.map((c) => (
        <TreeRow key={c.path} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}

export function FileTree() {
  const { tree, treeLoading, fetchTree, log, openFile } = useWorkspaceStore();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [semantic, setSemantic] = useState(false);

  const runSearch = async () => {
    const q = query.trim();
    if (!q) { setResults(null); return; }
    setSearching(true);
    try {
      const data = semantic ? await searchWorkspaceSemantic(q) : await searchWorkspace(q);
      setResults(data.results);
      if (semantic && data.mode === 'lexical') {
        log('warn', 'Semantic search unavailable (no embedding key) — showed lexical results');
      }
    } catch (e) {
      log('error', (e as Error).message);
    } finally {
      setSearching(false);
    }
  };

  const newFile = async () => {
    const path = window.prompt('New file path (workspace-relative):');
    if (!path) return;
    try {
      await writeWorkspaceFile(path, '');
      log('success', `Created ${path}`);
      fetchTree();
    } catch (e) { log('error', (e as Error).message); }
  };

  const newFolder = async () => {
    const path = window.prompt('New folder path:');
    if (!path) return;
    try {
      await createWorkspaceFolder(path);
      log('success', `Created folder ${path}`);
      fetchTree();
    } catch (e) { log('error', (e as Error).message); }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-3 py-2 border-b border-[var(--color-border-main)] text-xs font-medium text-[var(--color-text-secondary)] uppercase tracking-wide">
        <span className="flex-1">Explorer</span>
        <button title="New file" onClick={newFile} className="p-1 hover:text-white"><FilePlus className="w-3.5 h-3.5" /></button>
        <button title="New folder" onClick={newFolder} className="p-1 hover:text-white"><FolderPlus className="w-3.5 h-3.5" /></button>
        <button title="Refresh" onClick={fetchTree} className="p-1 hover:text-white">
          <RefreshCw className={cn('w-3.5 h-3.5', treeLoading && 'animate-spin')} />
        </button>
      </div>
      <div className="px-2 py-2 border-b border-[var(--color-border-main)] space-y-1">
        <div className="flex gap-1">
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); if (!e.target.value) setResults(null); }}
            onKeyDown={(e) => { if (e.key === 'Enter') runSearch(); }}
            placeholder={semantic ? 'Semantic search…' : 'Search files/symbols…'}
            className="flex-1 min-w-0 bg-[#151515] border border-[var(--color-border-main)] rounded px-2 py-1 text-xs text-white outline-none focus:border-[var(--color-accent)]/50"
          />
          <button
            title={semantic ? 'Semantic (AI) search — click for lexical' : 'Lexical search — click for semantic'}
            onClick={() => setSemantic(!semantic)}
            className={cn('p-1 rounded', semantic ? 'text-[var(--color-accent)]' : 'text-[var(--color-text-secondary)] hover:text-white')}
          >
            <Sparkles className="w-3.5 h-3.5" />
          </button>
          <button title="Search" onClick={runSearch} className="p-1 text-[var(--color-text-secondary)] hover:text-white">
            <Search className={cn('w-3.5 h-3.5', searching && 'animate-pulse')} />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {results !== null ? (
          <>
            <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-[var(--color-text-secondary)]">
              {results.length} result{results.length === 1 ? '' : 's'}
            </div>
            {results.map((r, i) => (
              <button
                key={`${r.path}-${i}`}
                onClick={() => openFile(r.path)}
                className="w-full text-left px-3 py-1.5 text-xs hover:bg-[var(--color-panel-200)]/50"
              >
                <div className="text-white truncate">{r.path}<span className="text-[var(--color-text-secondary)]">:{r.line}</span></div>
                <div className="text-[var(--color-text-secondary)] truncate font-mono text-[11px]">{r.match}</div>
              </button>
            ))}
          </>
        ) : (
          <>
            {tree.length === 0 && !treeLoading && (
              <div className="px-3 py-4 text-xs text-[var(--color-text-secondary)]">
                No files. Is the backend running?
              </div>
            )}
            {tree.map((n) => <TreeRow key={n.path} node={n} depth={0} />)}
          </>
        )}
      </div>
    </div>
  );
}
