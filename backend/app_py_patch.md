Add to backend/app.py, alongside the other register_*_routes calls:

    from projects import register_project_routes, init_project_tables
    register_project_routes(app)
    init_project_tables()

Requires `git` on whatever host runs Flask app.py (not Vercel — see
projects.py's module docstring; this is the same non-Vercel host that
already runs unity_bridge + the SQLite/Chroma knowledge base). No volume
needed: ingestion clones/uploads into tempfile.mkdtemp() and deletes it in
a finally block every time, so it's safe even if that host's /tmp is
wiped between runs. Optional PROJECTS_SCRATCH_DIR env var overrides the
tempdir base if you want it off the default disk.

subscription_manager.py: currently reuses the "workflow_builder" feature
flag for project-creation gating (so Basic-tier users are blocked, same
as workflow builder). Add "projects" alongside it in each plan's
`features` set if you want independent gating instead.
