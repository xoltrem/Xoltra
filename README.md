# automation-agent (browser ai capabilities)

Kept as a separate top-level tool, NOT merged into frontend/ or backend/.

Why: it has its own Node agent server AND its own Vite-based dashboard
(different build tool than the main Next.js frontend — Vite and Next.js
cannot share one package.json). Merging it would have meant either breaking
the dashboard's build or silently dropping functionality. Two package.json
files live here (this folder + dashboard/) as a result — an intentional,
explained exception to the "one frontend / one backend package.json" rule,
not an oversight.

Login.jsx was moved here from the repo root — it uses import.meta.env
(Vite's convention, not Next.js's), and calls localhost:5000, matching
auth-server.js exactly. It belongs to this dashboard, not the main app.
