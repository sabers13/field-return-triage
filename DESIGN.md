# Field Return Triage — portfolio page

## Intent and scope

Public English case study for people evaluating the work, including nontechnical
visitors. Balanced density, calm and concrete. One continuous page answers:
“How does a complaint become a useful next test?” It hides version strings,
raw run identifiers and detailed scoring behind disclosures. Real evidence and
essential limits remain visible. Desktop and phone, light and dark.

Rebuild locally in the R8 lane: `web/`, `src/field_return_triage/report/` and
`dist/field-return-triage/`. Evidence under `results/`, the method, data and model
outputs are protected. No publication, remote creation or portfolio checkout
changes. DESIGN.md and local-review ignore entries are additive shared changes
documented in the R8 report. No Firstmate commands or settings.

## References and choice

Inspected the live portfolio homepage, AI Privacy Filter, and the remote GitHub
Pages HTML/CSS/JS for AI Privacy Filter and LIVECell Audit on 2026-11-02.
The owner requested this established template. Preserve its author header,
section underline, utility rail, one-click theme controls and action anatomy.
Use the portfolio skill's explicit established-style exception to the generic
three-new-directions procedure. Taste's split-stage composition informs the
problem/output pairing; it does not replace the selected portfolio tokens.

## Colors

| Token | Light | Dark |
|---|---|---|
| `--page` | #f9fafb | #030712 |
| `--surface` | #ffffff | #111827 |
| `--inset` | #f3f4f6 | #1a2232 |
| `--ink` | #111827 | #f9fafb |
| `--secondary` | #374151 | #d1d5db |
| `--muted` | #626d7f | #a6afbe |
| `--line` | #e5e7eb | #263246 |
| `--accent` | #2563eb | #60a5fa |
| `--accent-ink` | #1e40af | #bfdbfe |
| `--accent-soft` | #dbeafe | #192e4e |
| `--on-accent` | #ffffff | #0b0f19 |
| `--warning` / `--warning-soft` | #92400e / #fef3c7 | #fbbf24 / #362b18 |
| `--danger` / `--danger-soft` | #b91c1c / #fee2e2 | #fca5a5 / #3b202b |
| `--success` / `--success-soft` | #166534 / #dcfce7 | #86efac / #14352c |

Accent is for links, the selected case, verified clues and chart series. Warning
and danger identify routing and safety. Never use color as the only label.
Hairlines are functional separators in navigation, records and evidence tables.
No resting shadows, gradients, stock images or decorative chart cards.

## Type and geometry

Self-hosted Inter variable, SIL OFL, embedded at build time for offline use.
Brand 20px/1.3 bold; hero 44px/1.12 medium (32px on phone); section heading
28px/1.2 medium (26px phone); lead 18px/1.65; body 16px/1.6; small 13px/1.55.
Sentence case. Code alone uses the platform monospace face. Evidence uses
tabular numerals. Long identifiers wrap; narratives preserve exact wording.

Spacing scale: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80px. Max shell 1440px;
40px desktop gutters, 24px tablet, 16px phone. Utility rail 48px, gap 24px.
Hero columns 1.1:1, queue 260px:minmax(0,1fr). Radii: 24px primary surfaces,
16px inset panels, 8px actions, full pills. Border width 1px, focus width 2px.

## Components and state

Fixed author header: normal anchor links, active blue underline, project badge
and portfolio Back. Desktop utility rail: sun/moon and section shortcuts.
Phone utilities sit below the two-row header; never overlay content.
Buttons and standalone controls have at least 44px targets and visible focus.

The real-example browser contains all twelve committed cards, priority filters,
a selected record, a mobile select, exact highlighted spans, test reasons,
similar cases, versions and local accept/change/reset demonstrations. Case and
priority selection are reflected in the query string; Back restores selection.
Demo decisions exist in memory only. Only the theme preference is stored.
All reported values and CIs come from the embedded committed page data.
Missing/corrupt data produces a labelled error with source-code recovery link.
No-script visitors can read the project explanation and a real static example.
Downloads are generated locally from the embedded evidence, with explicit names.

## Responsive behavior

At 1100px reduce hero gap and header spacing. At 900px stack the hero, move the
utilities into a compact row, and remove duplicate rail navigation. At 700px
stack complaint and suggestion, replace the long case list with a native select,
and turn flow nodes into a vertical list. Below 600px the header uses two rows,
retains author/Back and all section links, and omits the redundant project badge.
At 375px readable table columns remain within the page. Large technical tables
use labelled scroll containers where necessary. Anchors clear the fixed header.

## Motion and quality

Fast 160ms, base 240ms; easing cubic-bezier(.22,1,.36,1). Only useful hover,
selection and disclosure feedback. Animate opacity/transform; no entrance
choreography, number count-ups or scroll scenes. Reduced motion disables smooth
scroll and transitions. Initial theme follows system until a manual selection,
with query overrides for review. Blocked storage never stops rendering.

Verify via make page, facts, lint/type checks for touched Python, secret/name
scans, real interactions and desktop/tablet/phone screenshots in both themes.
Inspect the production static file at /field-return-triage/ and measure mobile
loading. Report generic Taste warnings that contradict the chosen portfolio
contract instead of redesigning the brand to satisfy them.
