# Design System (DESIGN.md) — IntentGuard Recovery

> **Status: implemented** in `frontend/`:
> - tokens in `frontend/src/styles/tokens.css`, components in `frontend/src/components/`, pages in `frontend/src/pages/`;
> - fonts self-hosted via `@fontsource` (no third-party requests, so the CSP can stay `'self'`);
> - checked in headless Chrome at 1440 px and 390 px, in dark and light themes.
>
> Differences from this spec are noted inline as *planned* or *as built*.

## 1. Philosophy
**High-tech financial observability.** The dashboard exists so an operator can answer three questions fast: *What is stuck? What was verified? What needs me?* Visual weight follows risk: unresolved and escalated items are loud, verified items are calm.

Principles:
1. **Evidence over decoration.** Every status chip links to the evidence behind it.
2. **"Being verified" is not "failed".** Uncertain states have their own visual identity.
3. **Dark by default**, light theme supported via tokens.
4. **Monospace for identifiers**, proportional type for prose.
5. **No full-page reloads**; the UI is a single-page React app.

## 2. Typography

| Role | Font | Weights | Use |
|------|------|---------|-----|
| Primary | `Outfit`, system-ui, sans-serif | 300, 400, 500, 600, 700 | UI text, headings |
| Monospace | `JetBrains Mono`, ui-monospace, monospace | 400, 500, 700 | IDs (`INT-1001`), hashes, JSON, console |

Type scale (rem): `xs .75 · sm .875 · base 1 · lg 1.125 · xl 1.25 · 2xl 1.5 · 3xl 1.875 · 4xl 2.25`.
Line heights: body 1.5, headings 1.2, mono blocks 1.6. Tabular numerals for all money: `font-variant-numeric: tabular-nums`.

## 3. Color tokens

### Core (dark)
| Token | Value | Use |
|-------|-------|-----|
| `--bg-deep` | `#0a0d14` | app background |
| `--bg-secondary` | `#101522` | panels, sidebar |
| `--surface-glass` | `rgba(18, 24, 38, 0.75)` + `backdrop-filter: blur(14px)` | cards |
| `--border` | `rgba(255, 255, 255, 0.08)` | default borders |
| `--text` | `#f8fafc` | primary text |
| `--text-muted` | `#94a3b8` | secondary text |

### Semantic accents
| Token | Value | Glow | Meaning |
|-------|-------|------|---------|
| `--accent-cyan` | `#00e5ff` | `rgba(0,229,255,.2)` | Active, reconciling, in progress |
| `--accent-emerald` | `#10b981` | `rgba(16,185,129,.2)` | Completed, verified |
| `--accent-rose` | `#f43f5e` | `rgba(244,63,94,.2)` | Blocked, rejected, outage |
| `--accent-amber` | `#f59e0b` | `rgba(245,158,11,.2)` | Escalated, discrepancy, needs review |
| `--accent-indigo` | `#6366f1` | `rgba(99,102,241,.2)` | Authorized, in flight |
| `--accent-violet` | `#a78bfa` | `rgba(167,139,250,.2)` | AI-generated content (investigator output) |

Rule: color is never the only signal; every status also has a label and icon.

*As built:* `PROPOSED`/`VALIDATED`/`REJECTED`/`BLOCKED` are statuses of a single proposal, not intent states (DECISIONS ADR-029). The map lives in `STATE_META` in `frontend/src/domain.js`.

### State → color map
| State | Color | Pill label |
|-------|-------|-----------|
| `AUTHORIZED` | indigo | Authorized |
| `PROPOSED`, `VALIDATED` *(proposal status)* | indigo | Proposed / Validated |
| `IN_FLIGHT`, `EXECUTING` | cyan (pulse) | Executing |
| `UNKNOWN`, `RECONCILING` | cyan (dashed border) | Verifying |
| `COMPLETED` | emerald | Completed ✓ |
| `CANCEL_REQUESTED` | amber | Cancelling |
| `CANCELLED` | slate | Cancelled |
| `REJECTED`, `BLOCKED` *(proposal status)* | rose | Blocked |
| `DISCREPANCY` | amber | Discrepancy |
| `ESCALATED` | amber | Needs review |
| `CLOSED` | slate | Closed |

### Light theme
Provide the same token names under `[data-theme="light"]` and `@media (prefers-color-scheme: light)`: `--bg-deep #f8fafc`, `--bg-secondary #ffffff`, `--surface-glass rgba(255,255,255,.85)`, `--border rgba(15,23,42,.1)`, `--text #0f172a`, `--text-muted #475569`. Accents darken one step to keep 4.5:1 contrast on light surfaces.

## 4. Spacing, radius, elevation
- Spacing scale (px): 4, 8, 12, 16, 24, 32, 48, 64.
- Radius: `sm 6 · md 10 · lg 16 · pill 999`.
- Elevation: glass cards use border + soft shadow `0 8px 30px rgba(0,0,0,.35)`; hover lifts `translateY(-2px)` with accent glow.

## 5. Components

### 5.1 State pipeline
Five sequential nodes: **Authorized → Proposed → Validated → Executing → Outcome**. The outcome node shows Completed, Blocked, Needs review, Cancelled, or Closed ("resolved by a reviewer").
- Active node pulses with cyan glow.
- Passed nodes turn emerald.
- Blocked node turns rose and shows an immediate callout with the reason code and plain-language text.
- `UNKNOWN`/`RECONCILING` render as a dashed cyan "Verifying" branch under Executing, never as an error.
- *As built:* `DISCREPANCY` and `CANCEL_REQUESTED` show the outcome node as in progress, because the gateway is still recovering on its own. Only `ESCALATED` reads "needs a human". The node logic is `pipelineStages` in `frontend/src/domain.js`, which has unit tests.

### 5.2 Status pill
Rounded, 12px text, icon + label. Classes: `state-completed`, `state-blocked`, `state-escalated`, `state-verifying`, `state-active`.

### 5.3 Intent timeline
Vertical list, newest at bottom, monospace timestamps, event icon, one-line summary, evidence chip (e.g. `ATT-001`, `EFF-1`, `WH-88`) that opens a side drawer with raw JSON.

### 5.4 Data tables
Sticky header, 1px borders, monospace ID columns, right-aligned tabular money, row hover highlight, inline actions (e.g. **Resolve ✓** on open review cases), keyboard-navigable.

### 5.5 Metric cards
Large number, label, delta vs previous window (*planned*; the cards show the number for the selected window). Cards: Completed, Blocked, Verifying, Escalated, Duplicates suppressed, Auto-resolved rate, Median time to verified.

### 5.6 Investigator panel (AI)
Violet-bordered card labelled **AI-generated · advisory**. Shows classification, summary, evidence refs, recommended action and the **policy verdict** (permitted / not permitted + rule). The "Apply" button is disabled when the policy verdict is not permitted.

### 5.7 Scenario demo cards
Four one-click cards with category badges: `SAFETY BARRIER` (unauthorized amount), `ACTIVE RECONCILIATION` (lost response), `DUPLICATE SUPPRESSION` (restart), `HUMAN ESCALATION` (incorrect completed effect). Hover elevation 2px.

### 5.8 Live console
Monospace, autoscroll with pause-on-scroll-up, level colors (info slate, warn amber, error rose, verified emerald).

### 5.9 Audit verification badge
"Chain verified ✓ (N entries)" in emerald or "Chain broken at #K" in rose with link to the entry (*as built:* the badge names the entry and its chain; a direct link is *planned*). Shown in the top bar for roles that may verify.

## 6. Page inventory
| Page | Contents |
|------|----------|
| Overview | metric cards, the four demo scenario cards (simulator mode), recent intents, live console |
| Intents | filterable table, detail view with pipeline + timeline + attempts + effects |
| Exceptions | stuck/unknown cases, investigate action |
| Review queue | open cases, resolve dialog |
| Reconciliation | runs, mismatches |
| Audit | log search, chain verification |
| Experiments | benchmark summary tables and charts |
| Admin | users, service tokens, policies, providers |
| Login | email + password; the session survives reloads through the refresh cookie |

## 7. Responsive behavior
Breakpoints: Desktop 1440, Laptop 1024, Tablet 768. Below 1024 the sidebar collapses to icons; below 768 tables become card lists. Mobile is out of scope for v1 beyond readability.

*As built:* at 390 px no page scrolls horizontally. Wide tables scroll inside their own container.

## 8. Accessibility
- WCAG 2.1 AA contrast; focus rings (2px cyan) on all interactive elements.
- Status never conveyed by color alone.
- Respect `prefers-reduced-motion` (disable pulses/hover lifts).
- Money and IDs are selectable and copyable; ARIA labels on pipeline nodes.

## 9. Token file
Implement tokens once in `frontend/src/styles/tokens.css` as CSS variables; components read variables only (no hard-coded hex).

```css
:root {
  --bg-deep:#0a0d14; --bg-secondary:#101522;
  --surface-glass:rgba(18,24,38,.75); --border:rgba(255,255,255,.08);
  --text:#f8fafc; --text-muted:#94a3b8;
  --accent-cyan:#00e5ff; --accent-emerald:#10b981; --accent-rose:#f43f5e;
  --accent-amber:#f59e0b; --accent-indigo:#6366f1; --accent-violet:#a78bfa;
  --font-sans:'Outfit',system-ui,sans-serif;
  --font-mono:'JetBrains Mono',ui-monospace,monospace;
  --radius-md:10px; --radius-lg:16px;
}
```
