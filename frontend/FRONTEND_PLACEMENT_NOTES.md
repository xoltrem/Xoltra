Move these into the real frontend/ tree:

  projectsApi.ts          -> frontend/src/lib/projectsApi.ts        (new)
  projects_page.tsx        -> frontend/src/app/projects/page.tsx      (new)
  project_detail_page.tsx  -> frontend/src/app/projects/[id]/page.tsx (new — note the [id] dir)
  Sidebar.tsx              -> frontend/src/components/layout/Sidebar.tsx (overwrite)

No changes needed to frontend/src/lib/api.ts — projectsApi.ts imports
`fetchApi` from it, keeping the diff isolated to new files plus one
Sidebar overwrite (single line added: the "Projects" NAV_ITEMS entry).

Requires the backend/projects.py routes from the prior pass to already be
registered in app.py.
