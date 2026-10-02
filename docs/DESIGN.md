# Design System (DESIGN.md) — IntentGuard

## Design Philosophy
**High-Tech Financial Observability**: Modern, dark-mode glassmorphic interface with vibrant state signifiers, crisp data tables, and dynamic visual pipeline states.

## Typography
- **Primary Font**: `Outfit` (sans-serif, Google Fonts) — 300, 400, 500, 600, 700
- **Monospace Font**: `JetBrains Mono` (Google Fonts) — IDs, hashes, JSON payloads, console traces

## Curated Color Palette
- **Background Deep**: `#0a0d14`
- **Background Secondary**: `#101522`
- **Card Glass Surface**: `rgba(18, 24, 38, 0.75)` with `backdrop-filter: blur(14px)`
- **Border Default**: `rgba(255, 255, 255, 0.08)`
- **Accent Cyan (Active / Reconciliation)**: `#00e5ff` (Glow: `rgba(0, 229, 255, 0.2)`)
- **Accent Emerald (Completed / Verified)**: `#10b981` (Glow: `rgba(16, 185, 129, 0.2)`)
- **Accent Rose (Blocked / Outage)**: `#f43f5e` (Glow: `rgba(244, 63, 94, 0.2)`)
- **Accent Amber (Escalated / Discrepancy)**: `#f59e0b` (Glow: `rgba(245, 158, 11, 0.2)`)
- **Accent Indigo (Authorized / In-Flight)**: `#6366f1`
- **Text Main**: `#f8fafc`
- **Text Muted**: `#94a3b8`

## UI Components
### Visual State Machine Pipeline
- 5 sequential nodes: `Authorized` -> `Proposed` -> `Validated` -> `Executing` -> `Terminal` (`Completed`, `Blocked`, or `Escalated`).
- Active nodes pulsate with cyan glow.
- Completed nodes turn emerald.
- Blocked nodes turn crimson with immediate explanatory callout.

### Prescribed Demo Cards
- 4 interactive one-click scenario cards with distinct category badges (`SAFETY BARRIER`, `ACTIVE RECONCILIATION`, `DUPLICATE SUPPRESSION`, `HUMAN ESCALATION`).
- Smooth hover elevation (`transform: translateY(-2px)`).

### Data Tables
- Responsive, clean borders, monospaced identifier formatting, colored status pills (`state-completed`, `state-blocked`, `state-escalated`).
- In-place action buttons (e.g. `Resolve ✓` for open review cases).

## UX Requirements
- Responsive across Desktop (1440px), Laptop (1024px), and Tablet (768px).
- Zero full-page reloads (single-page application architecture with fetch API).
- Live execution console log with autoscroll for transparent operator observability.
