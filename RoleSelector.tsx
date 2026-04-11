// RoleSelector.tsx
// XoltaOS Role Selection component.
// Fetches roles from /api/roles, renders as a scannable selector grid.
// Drop this into your existing layout — it calls onRoleSelect with the role_id.

import { useEffect, useState } from "react";

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

// ─── Zustand slice (add to your existing store) ────────────────────────────
// In your store.ts:
//
//   import { create } from "zustand";
//
//   interface RoleSlice {
//     activeRoleId: string;
//     setActiveRole: (id: string) => void;
//   }
//
//   export const useRoleStore = create<RoleSlice>((set) => ({
//     activeRoleId: "default",
//     setActiveRole: (id) => set({ activeRoleId: id }),
//   }));
//
// Then in any component that calls the API:
//   const { activeRoleId } = useRoleStore();
//   // include role_id: activeRoleId in every POST body

// ─── Component ────────────────────────────────────────────────────────────────

export default function RoleSelector({
  selectedRoleId,
  onRoleSelect,
  className = "",
}: RoleSelectorProps) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/roles")
      .then((r) => {
        if (!r.ok) throw new Error("Failed to fetch roles");
        return r.json();
      })
      .then((data) => {
        setRoles(data.roles ?? []);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className={`role-selector-loading ${className}`}>
        <span className="role-loading-text">Loading roles...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`role-selector-error ${className}`}>
        <span>Could not load roles: {error}</span>
      </div>
    );
  }

  const activeRole = roles.find((r) => r.id === selectedRoleId);

  return (
    <div className={`role-selector ${className}`}>
      {/* Header */}
      <div className="role-selector__header">
        <span className="role-selector__label">ROLE</span>
        {activeRole && (
          <span className="role-selector__active-badge">
            {activeRole.icon} {activeRole.name}
          </span>
        )}
      </div>

      {/* Grid */}
      <div className="role-selector__grid">
        {roles.map((role) => {
          const isSelected = role.id === selectedRoleId;
          const isHovered = hoveredId === role.id;

          return (
            <button
              key={role.id}
              onClick={() => onRoleSelect(role.id)}
              onMouseEnter={() => setHoveredId(role.id)}
              onMouseLeave={() => setHoveredId(null)}
              className={[
                "role-card",
                isSelected ? "role-card--selected" : "",
                isHovered && !isSelected ? "role-card--hovered" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-pressed={isSelected}
              title={role.description}
            >
              <span className="role-card__icon">{role.icon}</span>
              <span className="role-card__name">{role.name}</span>
              <span className="role-card__desc">{role.description}</span>

              {/* Expertise pills — shown on hover/select */}
              {(isSelected || isHovered) && (
                <div className="role-card__expertise">
                  {role.expertise_areas.slice(0, 3).map((area) => (
                    <span key={area} className="role-card__pill">
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
  );
}


// ─── Styles (add to your global CSS / Tailwind @layer) ────────────────────────
//
// If you're using Tailwind, translate these to utility classes.
// If you have a global .css file, paste this in directly.
//
// Design language: dark industrial, sharp geometry, amber accent.
// Matches an "execution engine" product feel.
//
/*

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

.role-selector {
  font-family: var(--role-font);
  width: 100%;
}

.role-selector__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.role-selector__label {
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--role-muted);
  font-weight: 600;
}

.role-selector__active-badge {
  font-size: 11px;
  color: var(--role-accent);
  background: var(--role-accent-lo);
  border: 1px solid var(--role-accent);
  border-radius: 3px;
  padding: 2px 8px;
  letter-spacing: 0.05em;
}

.role-selector__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}

.role-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 12px 14px;
  background: var(--role-surface);
  border: 1px solid var(--role-border);
  border-radius: var(--role-radius);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s, transform 0.1s;
  outline: none;
  width: 100%;
}

.role-card:hover,
.role-card--hovered {
  border-color: var(--role-border-hi);
  background: #17171b;
}

.role-card--selected {
  border-color: var(--role-accent);
  background: var(--role-accent-lo);
}

.role-card--selected:hover {
  background: rgba(245, 166, 35, 0.16);
}

.role-card__icon {
  font-size: 20px;
  line-height: 1;
  margin-bottom: 2px;
}

.role-card__name {
  font-size: 12px;
  font-weight: 600;
  color: var(--role-text);
  letter-spacing: 0.03em;
}

.role-card__desc {
  font-size: 10px;
  color: var(--role-muted);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.role-card__expertise {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.role-card__pill {
  font-size: 9px;
  letter-spacing: 0.06em;
  color: var(--role-muted);
  background: var(--role-pill-bg);
  border: 1px solid var(--role-border);
  border-radius: 2px;
  padding: 2px 5px;
  text-transform: uppercase;
}

.role-card--selected .role-card__pill {
  border-color: rgba(245, 166, 35, 0.25);
  color: rgba(245, 166, 35, 0.7);
  background: rgba(245, 166, 35, 0.06);
}

.role-card__check {
  position: absolute;
  top: 8px;
  right: 10px;
  font-size: 11px;
  color: var(--role-accent);
  font-weight: 700;
}

.role-selector-loading,
.role-selector-error {
  font-family: var(--role-font);
  font-size: 12px;
  color: var(--role-muted);
  padding: 16px 0;
}

.role-selector-error {
  color: #e05c5c;
}

@media (max-width: 600px) {
  .role-selector__grid {
    grid-template-columns: 1fr 1fr;
  }
}

*/
