# XOLTRA FRONTEND PRODUCT REQUIREMENTS DOCUMENT (PRD)

Version: 2.1
Status: Active

---

# PRODUCT OVERVIEW

XOLTRA is a modern workflow automation platform inspired by n8n.

The frontend must feel like a premium engineering tool rather than a marketing website.

Users should feel like they are operating infrastructure.

The interface should prioritize:

* Clarity
* Speed
* Reliability
* Visibility
* Scalability
* Developer Experience

Over aesthetics.

Every UI element must serve a purpose.

> **Resolved (v2.1):** Brand tone confirmed as "no expertise needed." The premium, minimal "infrastructure" *look* stays — it builds trust with a non-technical buyer like a company CEO — but the interaction model leans on the AI Assistant to do the heavy lifting, with mandatory onboarding and plain-language copy throughout, rather than assuming a developer-literate audience. See Architecture Decisions for full reasoning.

---

# DESIGN PHILOSOPHY

Inspirations:

* Linear
* Vercel
* Raycast
* GitHub
* Retool
* Warp
* n8n

Avoid:

* Cyberpunk
* Neon overload
* Gaming UI
* Glassmorphism
* Excessive gradients
* Excessive shadows
* AI-generated aesthetics
* Decorative clutter

The UI should feel handcrafted by senior product designers.

---

# VISUAL LANGUAGE

Keywords:

* Tactical
* Minimal
* Sharp
* Engineering-first
* Professional
* Technical
* Focused

The interface should communicate trust and competence.

---

# TYPOGRAPHY

Primary Display Font:

Tiempo Text

Fallbacks:

* Geist
* Inter
* IBM Plex Sans

Code Font:

* JetBrains Mono
* IBM Plex Mono

Usage:

Headers:

* Tiempo Text

Body:

* Inter

Code:

* JetBrains Mono

Never use futuristic fonts.

> **Recommendation:** none of the cited inspirations (Linear, Vercel, Raycast, GitHub, Retool, Warp) use a serif display font — all use sans-serif headers (usually Geist or Inter). Tiempo Text is a strong editorial choice but will read as "blog/publication" rather than "infrastructure tool" next to those references. Recommend Geist for headers unless there's a specific brand reason to keep the serif — confirm with Achyuth either way.

---

# COLOR SYSTEM

Background:
#050505

Panels:
#0B0B0B
#101010

Borders:
#1A1A1A
#202020

Primary Text:
#F5F5F5

Secondary Text:
#8B8B8B

Accent:
#00D9FF

Success:
#00FF88

Warning:
#FFB020

Error:
#FF4D4D

🆕 AI Category (new — see Node Categories section):
#8B7FD9 (muted violet, desaturated to stay within the minimal palette)

---

# BACKGROUND SYSTEM

Use:

Subtle Engineering Grid

Requirements:

* 1px lines
* 3%-5% opacity
* Large spacing
* Static

Forbidden:

* Moving backgrounds
* Particles
* Floating elements
* Animated effects

---

# SPACING SYSTEM

Only use:

4px
8px
12px
16px
24px
32px
48px
64px

No arbitrary spacing.

---

# BORDER SYSTEM

Global Radius:

4px

Never use:

* Pill buttons
* Large rounded cards
* Rounded blobs

---

# SHADOWS

Minimal.

Use shadows only for:

* Dropdowns
* Modals
* Command palette

Never use decorative shadows.

---

# ✅ ARCHITECTURE DECISIONS (RESOLVED — v2.1)

These were product/business decisions, not design questions. All three are now settled.

**1. Local-first, not multi-tenant — for now.**
XoltraOS stays local-first: one SQLite knowledge base, API keys in a local `.env`, no hosted accounts, no auth system. This was confirmed even though the sale is to a company (a water utility) rather than an individual — the reasoning: this deal doesn't require multi-tenant isolation (walling off unrelated companies from each other), since there's one customer right now. If a second, unrelated customer is signed later, multi-tenant SaaS becomes worth building then — not speculatively now. **Everything under "Future / Phase 3" stays deferred as a result** — Team Collaboration, SSO, White Labeling, and Billing remain documented intent, not active scope.

**2. React Flow = edit-time, Unity = run-time. Confirmed.**
Decided specifically because Unity already has real, working code behind it (`XoltraSimManager.cs`, `WorkflowVisualizer.cs`, `AgentPipelineView.cs`, `NodeRenderer.cs`, `unity_bridge.py`) rather than something to build from scratch. React Flow handles building/connecting/configuring workflows in the browser; Unity handles watching them execute. See Unity Integration Architecture below — no longer a recommendation, this is the spec.

**3. Brand tone: "no expertise needed." Confirmed.**
The buyer is a company CEO, not a developer — the Linear/Vercel/Raycast-style premium minimal look stays (it signals trust and seriousness to a non-technical buyer), but the product needs to do more of the explaining itself: the AI Assistant becomes the primary way most users build workflows rather than manual node-wiring, onboarding is mandatory rather than skippable, every node shows a plain-language description by default, and error/consent copy avoids engineering jargon.

---

# ✅ UNITY INTEGRATION ARCHITECTURE (CONFIRMED)

XoltraOS already has a working visualization layer in Unity (WebSocket bridge on port 5002, with renderers for the knowledge graph, agent pipeline, and workflow phases/steps). This is the confirmed split between it and the React Flow canvas:

* **React Flow canvas = edit-time.** Building, connecting, configuring, and arranging nodes happens here. This is the "blueprint."
* **Unity viewport = run-time.** Watching a workflow execute, auditing data mutations, and observing the agent pipeline happens here, fed by the same backend that powers the React Flow canvas. This is the "playback."

**Required UI elements:**

* A Unity connection status badge in the top bar or sidebar (mirrors the existing `SimulationUI.cs` connection indicator) — shows connected/disconnected, doesn't block core functionality when disconnected.
* An explicit "Open Simulation View" action on a workflow, rather than assuming Unity is always visible — Unity is a separate window/application, not embedded in the browser.
* Execution state shown identically in both places (a node marked "running" on the React Flow canvas should match what's playing in Unity) — this means execution state needs to live in one shared backend source of truth, not be duplicated per-frontend.

For a company sale like this one, the Unity layer doubles as a security/trust feature — being able to literally watch what an AI-built workflow does to company systems, in real time, is a strong argument for a buyer wary of an AI touching operational infrastructure.

---

# LAYOUT ARCHITECTURE

Three-panel layout.

LEFT SIDEBAR
CENTER CANVAS
RIGHT INSPECTOR

---

# LEFT SIDEBAR

Contains:

* Workflows
* Templates
* Personas
* Schemas
* Knowledge Graph
* Audit Logs
* Settings

🆕 Add:

* Unity connection status (small badge, bottom of sidebar — see Unity Integration Architecture)

Requirements:

* Collapsible
* Searchable
* Fixed
* Independent scrolling

---

# CENTER WORKFLOW CANVAS

Technology:

React Flow

> This is the **edit-time** canvas (see Unity Integration Architecture). Runtime playback/audit is a separate Unity view, not rendered here.

Features:

* Infinite canvas
* Zoom
* Pan
* Drag
* Snap-to-grid
* Multi-select
* Copy
* Paste
* Duplicate
* Delete
* Undo
* Redo
* Node grouping

Performance Target:

1000+ nodes
1000+ edges
60 FPS

> Treat this as the long-term target, not a v1 acceptance criterion — there's no real workflow data yet to stress-test against. Build with virtualization from day one so it scales naturally, but don't block MVP launch on hitting this number with synthetic data.

---

# RIGHT INSPECTOR PANEL

Displays:

Configuration
Runtime
Debugging
🆕 Permissions

Sections:

## Configuration

* Node Parameters
* Variables
* Secrets References

## 🆕 Permissions

* The node's Manifest (from the Permission Bridge): declared actions, required scopes (read-only / write-modify / system-level)
* Approval status against the current App Registry — approved, needs consent, or blocked
* A "Request Access" action if the node needs a scope the user hasn't granted yet

## Runtime

* Execution Time
* Status
* Tokens
* Cost
* Duration

> Phase 2 — depends on a backend execution engine and run-history store that don't exist yet. Spec the UI now; wire it once `workflow_engine.py` exists.

## Debug

* Inputs
* Outputs
* Logs
* Errors

> Same Phase 2 dependency as Runtime above.

---

# WORKFLOW NODES

Node Width:

220px–260px

States:

* Default
* Hover
* Selected
* Running
* Success
* Error
* Disabled

Requirements:

* Thin border
* Minimal shadow
* Status indicator
* Compact layout

---

# ✏️ NODE CATEGORIES (revised)

v1.0 listed ten categories (Triggers, Logic, AI, Databases, Storage, Integrations, Notifications, Utilities, System, Custom). That conflicts with the simpler 5-category system already established for XoltraOS's security model. This revision keeps the ten as **functional** categories (what a node does) but maps them to **five visual treatments** (how a node looks), so the canvas doesn't end up with ten different colors — which would violate this same document's "avoid neon overload / decorative clutter" rule.

**Visual treatment (reuses the existing minimal palette — no new neon colors added):**

| Functional categories | Visual treatment | Color |
|---|---|---|
| Triggers | 1px left border, Accent | `#00D9FF` |
| AI / Cohere | 1px left border, muted violet | `#8B7FD9` |
| Integrations, Databases, Storage, Notifications | 1px left border, Success green | `#00FF88` |
| Logic, Utilities, System | 1px left border, Warning amber | `#FFB020` |
| Custom / AI-generated nodes | Dashed (not solid) left border in the color of its underlying category | — |

The dashed-border treatment for AI-generated nodes distinguishes "the AI built this" from native nodes using stroke style instead of an additional color — consistent with the minimal palette rule, and gives users an at-a-glance way to spot nodes that came from natural-language generation versus ones they built by hand.

---

# CONNECTION SYSTEM

Requirements:

* Custom edges
* Smooth curves
* Validation
* Visual feedback
* Error handling

Connection rules should be obvious.

> "Obvious" needs an actual rule set, not just a feel. The node schema (input/output types per node, what can connect to what) isn't built yet — that has to exist before connection validation can be implemented. Spec a placeholder: a node's output and the receiving node's input must declare compatible data shapes (string / object / file-path / etc.); incompatible connections are visually rejected with a red flash on the edge, not silently allowed.

---

# EXECUTION VISUALIZATION

> Phase 2 — entirely dependent on a workflow execution engine that doesn't exist in the backend yet. Keep this spec as the target; sequence the build so backend execution-history exists before this UI is wired to real data.

Every workflow execution should provide:

Execution Timeline

Display:

* Node Name
* Start Time
* End Time
* Duration
* Tokens
* Cost
* Status

States:

* Pending
* Running
* Success
* Failed

Use subtle border highlights only.

---

# 🆕 AI-GENERATED NODE REVIEW

When a node is generated from a natural-language prompt (the "AI Node Factory" / Magic Node concept), it must be reviewed before it's allowed onto the canvas — this is a direct extension of the Permission Bridge's "manifest before code" security guardrail already defined for the backend.

**Required flow:**

1. User describes the node in plain English in the AI Assistant panel.
2. The system generates the Node Manifest (declared actions/scopes) and shows it to the user **before** generating execution logic.
3. User reviews the manifest — sees exactly what the node will touch (e.g., "READ ~/Downloads/*.pdf", "POST api.dropboxapi.com").
4. Only after the manifest is accepted does the system generate the node's internal logic and run it through sandbox validation.
5. If sandbox validation fails, the user sees the rejection reason in plain language (not raw error text) and can either revise the prompt or discard the node.
6. Accepted nodes get the dashed-border "AI-generated" treatment described in Node Categories.

This is the single most important trust-building moment in the product — it should not be skippable or buried in a secondary panel.

---

# 🆕 PERMISSION & CONSENT SYSTEM

Surfaces the existing backend Permission Bridge (App Registry, Just-In-Time consent, Audit Log) in the UI. Without this, the security model that differentiates Xoltra has no visible presence in the product at all.

**Required screens/components:**

* **App Registry panel** (in Settings) — list of approved apps/services, their granted scopes, and a revoke action per app.
* **JIT Consent Modal** — appears when a running workflow hits an action outside its approved scope. Pauses execution. Shows exactly what's being requested ("This node wants to modify your 'Chill Vibes' Spotify playlist") with Allow / Deny, not a generic permission popup.
* **Audit Log Viewer** (already in v1.0's sidebar list) — should pull from the existing backend `AuditLog`, showing action, node, outcome (allowed/blocked/consent-required), and timestamp, with the same User/Action/Resource/Timestamp filtering already specified.

---

# COMMAND PALETTE

Shortcut:

CTRL + K

Supports:

* Search Workflows
* Search Nodes
* Search Executions
* Search Settings
* Search Templates
* Search Schemas
* Search Personas

Inspired by Raycast and Linear.

---

# SEARCH EXPERIENCE

Global search must be available everywhere.

Results should appear instantly.

Support fuzzy search.

---

# WORKFLOW MANAGEMENT

Features:

* Create Workflow
* Duplicate Workflow
* Export Workflow
* Import Workflow
* Archive Workflow
* Delete Workflow

---

# VERSION HISTORY UI

> Phase 2 — the planned workflow storage layer only scopes draft/published versioning for v1, not full diff history. Spec below is the target; build the simpler draft/published toggle first.

Display:

* Version Number
* Author
* Timestamp
* Changes

Support:

* Compare
* Rollback
* Restore

---

# AI NODE EXPERIENCE

For Cohere Nodes:

Display:

* Model
* Temperature
* Max Tokens
* Timeout
* Streaming
* Structured Output

Show estimates before execution:

* Input Tokens
* Output Tokens
* Estimated Cost

> Note: XoltraOS currently auto-selects models via a 3-tier system (Fast/Standard/Deep) based on detected complexity, rather than manual per-node model selection. If manual override is intended here, confirm that's a deliberate change from the current "fully automatic" tier behavior — it was a specific earlier product decision, not an oversight.

---

# USAGE DASHBOARD

Display:

* Today's Executions
* Weekly Executions
* Monthly Executions
* Success Rate
* Failure Rate
* Token Usage
* Cohere Usage

Minimal card layout.

---

# COST CENTER

> Phase 2 — no usage-metering backend exists yet, and Cohere doesn't return cost data directly. Ship a simple "tokens used" display for v1; defer the budget/lock mechanics below until a metering system is built.

Display:

* Monthly Budget
* Daily Budget
* Workflow Budget
* Node Budget

Progress Indicators:

0-79% Normal

80% Warning

90% Critical

100% Locked

---

# RATE LIMIT CENTER

> Phase 2 — same backend dependency as Cost Center.

Display:

* Requests Per Minute
* Current Usage
* Remaining Capacity
* Reset Time

For:

* Workspace
* Workflow
* AI Nodes

---

# NOTIFICATION CENTER

Types:

* Success
* Warning
* Error
* Info

Features:

* Notification history
* Filtering
* Read/Unread

---

# ACTIVITY FEED

Track:

* Workflow Created
* Workflow Updated
* Workflow Deleted
* Workflow Executed
* User Activity

Provide timestamps.

---

# AUDIT LOG VIEWER

> Ties directly to the existing backend `AuditLog` class — see Permission & Consent System above.

Display:

* User
* Action
* Resource
* Timestamp

Filters:

* User
* Action
* Date Range

---

# 🆕 ONBOARDING & FIRST-RUN EXPERIENCE

Not present in v1.0 at all — needed given the product's "no prior knowledge required" positioning.

**Required:**

* A first-run welcome flow (not a full tutorial — a short, skippable orientation: what a node is, what a workflow is, where the AI Assistant lives).
* Empty-state CTAs that don't just say "no workflows yet" but actively prompt the first action ("Describe what you want to automate" with the AI Assistant input visible right there).
* Inline contextual hints the first 2-3 times a user encounters something new (consent modal, AI node review screen) — dismissible, never shown again once acknowledged.

---

# SETTINGS EXPERIENCE

Sections:

General

Workspace

Users

Permissions

API Keys

Billing

Notifications

Security

Appearance

> "Users" and "Billing" sections stay in the IA for future-proofing, but remain empty/disabled states for now — the confirmed local-first architecture means there's no hosted account system to populate them yet (see Architecture Decisions).

---

# 🆕 FEEDBACK MECHANISM

Not present in v1.0. Required for a product preparing for real users:

* A lightweight feedback entry point (e.g., a "?" or feedback icon in the top bar) — short form, no account required to submit
* Optional: surface this automatically after a workflow execution fails, asking if the error message was clear

---

# ➡️ TEAM COLLABORATION (Future / Phase 3)

> Confirmed deferred — the local-first architecture decision (see Architecture Decisions) means there's no hosted account system to build roles against yet. Revisit if a second, unrelated customer is signed and multi-tenant becomes worth building.

Support UI for:

* Inviting Users
* Removing Users
* Assigning Roles

Roles:

* Owner
* Admin
* Editor
* Viewer

---

# EMPTY STATES

Design dedicated empty states for:

* No Workflows
* No Templates
* No Executions
* No Logs
* No Results

Must feel intentional.

---

# LOADING STATES

Use:

* Skeletons
* Placeholder Cards
* Placeholder Nodes

Never use generic loading text.

---

# ERROR STATES

Dedicated experiences for:

* Execution Failed
* API Error
* Connection Failed
* Invalid Workflow
* Rate Limited

Provide actionable information.

---

# KEYBOARD SHORTCUTS

CTRL + K

CTRL + S

CTRL + Z

CTRL + SHIFT + Z

DELETE

COPY

PASTE

DUPLICATE

ESCAPE

---

# ACCESSIBILITY

Requirements:

* Keyboard Navigation
* ARIA Labels
* Focus States
* Reduced Motion
* WCAG Compliance

---

# RESPONSIVENESS

Support:

* 1440p
* 1080p
* Laptop
* Tablet

Desktop-first.

---

# THEME ARCHITECTURE

Use CSS variables.

Support future:

* Light Theme
* Custom Themes
* Workspace Branding

Without major refactoring.

---

# ➡️ FUTURE / PHASE 3 REQUIREMENTS (renamed from "Startup Requirements")

Everything below is explicitly deferred. List them here so the architecture *can* support them later without a rewrite — but none of these should be built, or have UI scaffolding built for them, until the local-first vs. hosted decision is made.

* Billing
* Teams
* Enterprise Plans
* API Marketplace
* Plugin Marketplace
* Workflow Templates
* Public Workflow Sharing
* Analytics
* SSO
* White Labeling

---

# COMPONENT LIBRARY

Build reusable components:

* Button
* Input
* Select
* Modal
* Drawer
* Tooltip
* Dropdown
* Tabs
* Table
* Badge
* Alert
* Command Palette
* Search
* Data Grid
* Chart Components

🆕 Add:

* Consent Modal (distinct from generic Modal — has its own Allow/Deny pattern, see Permission & Consent System)
* Node Manifest Viewer (used in both the Inspector's Permissions tab and AI-Generated Node Review)

All components must share a consistent design language.

---

# PERFORMANCE REQUIREMENTS

Lighthouse Score:
90+

Canvas:
60 FPS

Interaction Delay:
<16ms

Use:

* Memoization
* Virtualization
* Code Splitting
* Lazy Loading

Avoid unnecessary rerenders.

---

# TECH STACK

Next.js 15

React

TypeScript

TailwindCSS

React Flow

Zustand

React Hook Form

Zod

Framer Motion (minimal)

Lucide Icons

---

# CODE QUALITY REQUIREMENTS

TypeScript Strict Mode

No Any Types

Reusable Hooks

Reusable Components

Feature-Based Architecture

ESLint

Prettier

Consistent Naming Conventions

---

# FINAL DESIGN CHECKLIST

Before considering the frontend complete:

✓ Minimal visual noise

✓ Consistent spacing

✓ Consistent typography

✓ Consistent borders

✓ Cohere usage visibility

✓ Budget visibility

✓ Rate limit visibility

✓ Execution visibility

✓ Strong empty states

✓ Strong loading states

✓ Strong error states

✓ No AI-generated design clichés

✓ No excessive animations

✓ No unnecessary UI elements

✓ Premium engineering aesthetic

✓ Feels like production software

🆕 ✓ Unity/React Flow relationship is explicit, not assumed

🆕 ✓ Every AI-generated node is reviewable before it reaches the canvas

🆕 ✓ Permission/consent flow is visible somewhere in the product, not just in the backend

🆕 ✓ A brand-new user can build and run one workflow without external help

The final result should feel like software built by an experienced startup team preparing for thousands of users, not a hackathon project or a concept mockup.
