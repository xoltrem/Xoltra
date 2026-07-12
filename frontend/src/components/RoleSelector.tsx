// RoleSelector.tsx — fixed, single file (styles inlined via <style> tag)
import { useEffect, useRef, useState } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Role {
  id: string;
  name: string;
  description: string;
  icon: string;
  tone: string;
  expertise_areas: string[];
}

interface RoleSelectorProps {
  selectedRoleId: string;
  onRoleSelect: (roleId: string) => void;
  className?: string;
}

// ─── Zustand slice (add to your existing store.ts) ────────────────────────────
//
//   interface RoleSlice {
//     activeRoleId: string;
//     setActiveRole: (id: string) => void;
//   }
//   // inside create():
//   activeRoleId: "default",
//   setActiveRole: (id) => set({ activeRoleId: id }),
//
// Usage in any component that calls the API:
//   const { activeRoleId } = useRoleStore();
//   body: JSON.stringify({ goal, mode, answers, role_id: activeRoleId })

// ─── Component ────────────────────────────────────────────────────────────────

export default function RoleSelector({
  selectedRoleId,
  onRoleSelect,
  className,
}: RoleSelectorProps) {
  const [roles, setRoles]         = useState<Role[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  // FIX 4: AbortController — prevents race condition in StrictMode and
  // state updates on unmounted components
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    abortRef.current = new AbortController();

    fetch("/api/roles", { signal: abortRef.current.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to fetch roles (${r.status})`);
        return r.json();
      })
      .then((data) => {
        setRoles(data.roles ?? []);
        setLoading(false);
      })
      .catch((e) => {
        if (e.name === "AbortError") return;
        setError(e.message);
        setLoading(false);
      });

    return () => abortRef.current?.abort();
  }, []);

  // FIX 9: cx() prevents trailing whitespace from undefined/empty className
  const cx = (...parts: (string | undefined | false)[]) =>
    parts.filter(Boolean).join(" ");

  if (loading) {
    return (
      // FIX 3: was "role-loading-text" — never defined in the CSS block
      <div className={cx("role-selector--loading", className)}>
        <span>Loading roles...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={cx("role-selector--error", className)}>
        <span>Could not load roles: {error}</span>
      </div>
    );
  }

  const activeRole = roles.find((r) => r.id === selectedRoleId);

  return (
    <>
      {/* FIX 1+2: CSS was inside a block comment — uncommented and injected
          via a <style> tag so the component stays self-contained */}
      <style>{STYLES}</style>

      <div className={cx("role-selector", className)}>
        <div className="role-selector__header">
          <span className="role-selector__label">ROLE</span>
          {activeRole && (
            <span className="role-selector__active-badge">
              {activeRole.icon} {activeRole.name}
            </span>
          )}
        </div>

        <div className="role-selector__grid">
          {roles.map((role) => {
            const isSelected = role.id === selectedRoleId;
            const isHovered  = hoveredId === role.id;

            return (
              <button
                key={role.id}
                // FIX 5: missing type="button" — buttons default to type="submit"
                // and would submit any ancestor <form> instead of selecting a role
                type="button"
                // FIX 8: guard prevents firing onRoleSelect on already-active role
                onClick={() => { if (!isSelected) onRoleSelect(role.id); }}
                onMouseEnter={() => setHoveredId(role.id)}
                onMouseLeave={() => setHoveredId(null)}
                // FIX 6: removed role-card--hovered — CSS :hover already covers it
                className={cx("role-card", isSelected && "role-card--selected")}
                aria-pressed={isSelected}
                aria-label={`${role.name}: ${role.description}`}
                title={role.description}
              >
                <span className="role-card__icon" aria-hidden="true">{role.icon}</span>
                <span className="role-card__name">{role.name}</span>
                <span className="role-card__desc">{role.description}</span>

                {(isSelected || isHovered) && (
                  <div className="role-card__expertise">
                    {/* FIX 7: key={area} alone risks duplicate key warning */}
                    {role.expertise_areas.slice(0, 3).map((area, i) => (
                      <span key={`${area}-${i}`} className="role-card__pill">
                        {area}
                      </span>
                    ))}
                  </div>
                )}

                {isSelected && (
                  <span className="role-card__check" aria-hidden="true">✓</span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
// FIX 1+2: was a /* */ block comment — CSS inside a JS comment does nothing.
// Stored as a template literal and injected via <style> above.

const STYLES = `
  :root {
    --role-bg:        #0d0d0f;
    --role-surface:   #141417;
    --role-border:    #2a2a30;
    --role-border-hi: #3d3d46;
    --role-accent:    #f5a623;
    --role-accent-lo: rgba(245, 166, 35, 0.12);
    --role-text:      #e8e8ec;
    --role-muted:     #6b6b78;
    --role-pill-bg:   #1e1e24;
    --role-radius:    6px;
    --role-font:      "DM Mono", "Fira Code", monospace;
  }

  .role-selector { font-family: var(--role-font); width: 100%; }

  .role-selector__header {
    display: flex; align-items: center;
    justify-content: space-between; margin-bottom: 10px;
  }

  .role-selector__label {
    font-size: 10px; letter-spacing: 0.15em;
    color: var(--role-muted); font-weight: 600;
  }

  .role-selector__active-badge {
    font-size: 11px; color: var(--role-accent);
    background: var(--role-accent-lo); border: 1px solid var(--role-accent);
    border-radius: 3px; padding: 2px 8px; letter-spacing: 0.05em;
  }

  .role-selector__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 8px;
  }

  .role-card {
    position: relative; display: flex; flex-direction: column;
    align-items: flex-start; gap: 4px; padding: 12px 14px;
    background: var(--role-surface); border: 1px solid var(--role-border);
    border-radius: var(--role-radius); cursor: pointer; text-align: left;
    transition: border-color 0.15s, background 0.15s;
    outline: none; width: 100%;
  }

  /* FIX 10: focus-visible restores keyboard nav without affecting mouse users */
  .role-card:focus-visible {
    outline: 2px solid var(--role-accent); outline-offset: 2px;
  }

  /* FIX 6: only :hover needed — role-card--hovered was redundant */
  .role-card:hover { border-color: var(--role-border-hi); background: #17171b; }

  .role-card--selected {
    border-color: var(--role-accent); background: var(--role-accent-lo);
  }
  .role-card--selected:hover { background: rgba(245, 166, 35, 0.16); }

  .role-card__icon  { font-size: 20px; line-height: 1; margin-bottom: 2px; }
  .role-card__name  { font-size: 12px; font-weight: 600; color: var(--role-text); letter-spacing: 0.03em; }
  .role-card__desc  {
    font-size: 10px; color: var(--role-muted); line-height: 1.4;
    display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden;
  }

  .role-card__expertise { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }

  .role-card__pill {
    font-size: 9px; letter-spacing: 0.06em; color: var(--role-muted);
    background: var(--role-pill-bg); border: 1px solid var(--role-border);
    border-radius: 2px; padding: 2px 5px; text-transform: uppercase;
  }
  .role-card--selected .role-card__pill {
    border-color: rgba(245, 166, 35, 0.25);
    color: rgba(245, 166, 35, 0.7); background: rgba(245, 166, 35, 0.06);
  }

  .role-card__check {
    position: absolute; top: 8px; right: 10px;
    font-size: 11px; color: var(--role-accent); font-weight: 700;
  }

  /* FIX 3: renamed from .role-loading-text which was never defined */
  .role-selector--loading, .role-selector--error {
    font-family: var(--role-font); font-size: 12px;
    color: var(--role-muted); padding: 16px 0;
  }
  .role-selector--error { color: #e05c5c; }

  @media (max-width: 600px) {
    .role-selector__grid { grid-template-columns: 1fr 1fr; }
  }
`;
