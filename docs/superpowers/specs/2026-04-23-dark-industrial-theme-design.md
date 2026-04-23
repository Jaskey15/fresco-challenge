# Dark Industrial Theme — Design Spec

**Date:** 2026-04-23
**Scope:** Visual reskin of all three views (Upload, Processing, Results). No layout or interaction changes — purely color, typography, and styling.

## Direction

Dark & Clean industrial aesthetic. Restrained, professional, data-first. Monospace typography carries the personality; copper accent provides warmth and domain relevance (construction/hardware).

## Color Palette

### Backgrounds (three-tier depth)
| Token         | Hex       | Usage                              |
|---------------|-----------|-------------------------------------|
| `base`        | `#111318` | Page background, table area         |
| `surface`     | `#1e2028` | Cards, elevated panels, hover rows  |
| `elevated`    | `#262830` | Hover states, active inputs         |
| `pdf-surround`| `#16181d` | PDF viewer background               |

### Borders
| Token    | Hex       | Usage                    |
|----------|-----------|--------------------------|
| `border` | `#2e3038` | Panel dividers, table header border, card borders, input borders |

### Accent
| Token          | Hex       | Usage                                         |
|----------------|-----------|------------------------------------------------|
| `accent`       | `#d4956a` | Active tab, Download button, column headers, PDF bounding box, spinner, status badge, upload button |
| `accent-subtle`| `rgba(212,149,106,0.1)` | Badge background, hover tints |

### Text
| Token          | Hex       | Usage                          |
|----------------|-----------|--------------------------------|
| `text-primary` | `#e4e4e7` | Headings, descriptions, filenames |
| `text-secondary`| `#a1a1aa`| Catalog numbers, body text     |
| `text-muted`   | `#71717a` | QTY values, MFR/FINISH, notes  |
| `text-dim`     | `#52525b` | Placeholders, page labels, em-dashes |

### Semantic
| Token   | Hex       | Usage        |
|---------|-----------|--------------|
| `error` | `#ef4444` | Error messages, retry states |

## Typography

Two Google Fonts loaded via `<link>` in `index.html`:

- **JetBrains Mono** (weights: 600, 700) — headings, column headers, set tabs, set numbers, catalog numbers, filter input, status badge, page labels
- **DM Sans** (weights: 400, 500, 600) — body text, descriptions, notes, component names

### Hierarchy
| Element              | Font            | Size   | Weight | Color           | Extras                    |
|----------------------|-----------------|--------|--------|-----------------|---------------------------|
| Set title            | JetBrains Mono  | 17px   | 700    | `text-primary`  | `letter-spacing: 0.02em`  |
| Column headers       | JetBrains Mono  | 10px   | 600    | `accent`        | `letter-spacing: 0.1em`, uppercase |
| Set tabs             | JetBrains Mono  | 12px   | 700    | varies          | Active: accent bg, dark text. Inactive: surface bg, dim text |
| Component name       | DM Sans         | 13px   | 400    | `text-primary`  |                           |
| Catalog number       | JetBrains Mono  | 12px   | 400    | `text-secondary`|                           |
| Set description      | DM Sans         | 13px   | 400    | `text-muted`    |                           |
| Status badge         | JetBrains Mono  | 11px   | 400    | `accent`        | accent-subtle bg          |
| Page label           | JetBrains Mono  | 11px   | 400    | `text-dim`      |                           |

## Results View (primary)

### Top Bar
- Background: `surface` (#1e2028), bottom border
- Left side: Back arrow (`text-dim`) → filename (`text-primary`, JetBrains Mono 600) → status badge ("3 sets · 3 pages" in `accent` on `accent-subtle` bg)
- Right side: Download JSON button (solid `accent` bg, dark text)
- **Removed:** Show JSON button, LLM call count

### Set Tabs Row
- Background: `base`
- "3 SETS" label: JetBrains Mono, `text-dim`, small caps
- Active tab: `accent` background, dark text, rounded-4px
- Inactive tabs: `surface` bg, `border` border, `text-dim` text
- Filter input: `surface` bg, `border` border, JetBrains Mono, `text-muted` placeholder

### Set Header
- Status dot: 8x8px, `accent`, rounded-2px, subtle box-shadow
- Title: JetBrains Mono 17px 700
- Description line: DM Sans 13px, `text-muted`

### Data Table
- Column headers: JetBrains Mono 10px 600, `accent` colored, uppercase, wide letter-spacing
- Header row bottom border: `border`
- Row dividers: `surface` (subtle, not full border weight)
- Component names (DESCRIPTION): DM Sans, `text-primary`
- Data cells (QTY, MFR, FINISH): `text-muted`
- Catalog numbers: JetBrains Mono 12px, `text-secondary`
- Notes: DM Sans 12px, `text-muted`
- Em-dashes for empty cells: `text-dim`
- Hover: row background lightens to `surface`
- Edit indicators: keep existing behavior as-is (editing UX to be redesigned in a separate spec)

### PDF Viewer (left panel)
- Background: `pdf-surround` (#16181d)
- Page label: JetBrains Mono 11px, `text-dim`
- PDF pages: white, floating with `box-shadow: 0 2px 12px rgba(0,0,0,0.4)`
- Bounding boxes: 2px solid `accent`, `rgba(212,149,106,0.06)` fill
- Set labels: `accent` bg, dark text, left-edge positioned

## Upload View

No layout changes — color/font swap only.

- Page background: `base`
- Drag-drop zone: dashed `border` border, `text-primary` heading, `text-muted` subtitle
- Drag-over state: border lightens, subtle `accent-subtle` background tint
- Sample specbook cards: `surface` background, `border` border, copper hover highlight
- Upload/select button: solid `accent` background, dark text
- File icon emoji: keep as-is (no icon library added)

## Processing View

No layout changes — color/font swap only.

- Page background: `base`
- Spinner: `accent` colored (replace green)
- Phase label (current step): JetBrains Mono, `text-primary`
- Progress log entries: JetBrains Mono, `text-secondary`
- Error state: `error` red for message, retry button in `accent`

## Implementation Notes

- All styling remains 100% Tailwind utility classes — no custom CSS files
- Define CSS custom properties (via Tailwind v4 `@theme` in `index.css`) for the palette tokens so colors are centralized
- Google Fonts: add `<link>` tags to `index.html` for JetBrains Mono (600,700) and DM Sans (400,500,600)
- PDF bounding box color change requires updating `PdfViewer.tsx` inline styles
- The existing click-to-edit cell functionality stays as-is for now; editing UX redesign is a separate spec
- Transition: `transition-colors` on all interactive elements for smooth hover/state changes

## Out of Scope

- Editing UX redesign (row-level edit/delete/add — separate spec)
- Show JSON toggle (removed)
- LLM call count display (removed)
- Layout or structural changes
- Icon library addition
- Animation/motion beyond hover transitions
