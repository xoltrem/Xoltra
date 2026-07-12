# Placement notes for the newly added files

This repo's frontend files are flat (no real src/app/ tree found), so the
following were added flat too, matching that convention. Once you have the
real Next.js folder structure, move them to:

  ToolsPage.tsx            -> src/app/tools/page.tsx
  SettingsPage.tsx          -> src/app/settings/page.tsx
  KnowledgePage.tsx         -> src/app/knowledge/page.tsx
  WorkflowsPage.tsx         -> src/app/workflows/page.tsx
  PersonalizationPanel.tsx  -> src/components/settings/PersonalizationPanel.tsx
  AIAssistantPanel.tsx      -> src/components/workflow/AIAssistantPanel.tsx
  sidebar.tsx               -> src/components/layout/Sidebar.tsx (overwrite)

Backend files (app.py, subscription_manager.py, personalization.py,
workflow_assistant.py, requirements_updated.txt) sit at repo root already,
matching where the originals were.

## IMPORTANT -- found during merge, needs your decision

This zip also contains a completely separate Node.js system under
"browser ai capabilities/" -- its own agent server (index.js, runs on
port 4000), role file watcher, persistence layer, and a separate Vite+React
dashboard. It is NOT the Flask backend (app.py, port 5001) that all the
work above targets.

api.ts's original port (4000) matches THAT Node server, not a typo pointing
at the wrong Flask port like I assumed earlier -- so my earlier "port fix"
may have pointed api.ts at the wrong backend. I changed it to 5001 (Flask)
since all the personalization/subscription/workflow work in this session
was built against Flask. If the Next.js frontend is actually meant to talk
to the Node "browser ai capabilities" agent instead (or as well), api.ts
needs to be reconsidered -- I did not touch that folder's code at all.
