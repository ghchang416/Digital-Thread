# Design

## Design System Summary

VM Middle is a KITECH-branded product console for expert manufacturing workflows. The default visual strategy is restrained: neutral operational surfaces with KITECH blue for primary actions and KITECH green for limited success/accent moments.

The UI should support dense scanning, clear editing, and safe execution. It should feel institutional, precise, and modern without looking like a marketing site.

## Color

### Brand Palette

KITECH CI provides CMYK/Pantone guidance rather than direct web tokens. The React UI uses these web approximations as brand primitives.

| Token | Role | Value | Source note |
| --- | --- | --- | --- |
| `--kitech-blue` | Primary brand, key actions, focus, running/info | `#0047BB` | Pantone 2728C approximation |
| `--kitech-green` | Success accent, ready state, positive confirmation | `#84BD00` | Pantone 376C approximation |
| `--kitech-muted` | Institutional muted accent | `#736273` | CMYK 0,15,0,55 approximation |

### Semantic Tokens

Use semantic tokens in application code. Avoid hardcoding primitive brand values in components.

```css
:root {
  --color-primary: #0047bb;
  --color-primary-hover: #003a98;
  --color-primary-soft: #e7efff;

  --color-accent: #84bd00;
  --color-accent-soft: #edf8d2;

  --color-bg: #f5f7fb;
  --color-surface: #fbfcff;
  --color-surface-raised: #ffffff;
  --color-surface-subtle: #eef3f8;
  --color-border: #d6dee9;
  --color-border-strong: #b8c4d4;

  --color-text: #101828;
  --color-text-muted: #5f6b7a;
  --color-text-subtle: #7f8a99;

  --color-success: #087443;
  --color-success-soft: #e8f6ef;
  --color-warning: #a15c07;
  --color-warning-soft: #fff2d6;
  --color-danger: #b42318;
  --color-danger-soft: #fde7e7;
  --color-info: #0047bb;
  --color-info-soft: #e7efff;

  --focus-ring: #0047bb;
}
```

### Usage Rules

- Primary blue is for primary buttons, selected navigation, focus rings, active tabs, and running/info states.
- KITECH green is used sparingly for ready/success states and confirmation accents. Do not use it as a full-page theme.
- Warning and danger colors are operational semantics, not brand colors.
- Neutrals should carry most of the page. The interface should read as a work surface, not a brand campaign.
- Every status badge must include readable text.

## Typography

Use one product UI font stack:

```css
font-family: Inter, Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
```

Type scale:

| Role | Size | Weight | Use |
| --- | --- | --- | --- |
| Page title | 20px | 700 | Main console title |
| Section title | 16px | 700 | Panel headers |
| Card or row title | 14px | 700 | Project names, process labels |
| Body | 14px | 400 | Normal UI text |
| Compact body | 13px | 400 | Metadata, table cells |
| Label | 12px | 600 | Form labels, meta keys |
| Code/meta | 12px | 500 | IDs, gid/aid/eid, workplan tags |

Do not use fluid viewport-scaled typography. Keep product UI text stable across screen sizes.

## Layout

Desktop layout should prioritize three workflows:

1. Source project selection and VM creation.
2. VM project list scanning and filtering.
3. Detail inspection and editing in a drawer or resizable panel.

Recommended structure:

- Top app bar with product identity and API/docs actions.
- Left or first column for source project creation workflow.
- Main column for VM projects list.
- Detail drawer for selected project, optimized for editing and validation review.

Spacing:

| Token | Value | Use |
| --- | --- | --- |
| `--space-1` | 4px | Tight inline gaps |
| `--space-2` | 8px | Control internals |
| `--space-3` | 12px | Compact groups |
| `--space-4` | 16px | Panel padding |
| `--space-5` | 20px | Drawer body |
| `--space-6` | 24px | Major sections |

Use 8px radius for most controls and repeated items. Avoid large rounded pill surfaces except for compact status badges.

## Components

### Buttons

- Primary: filled KITECH blue.
- Secondary: neutral surface with strong border.
- Danger: danger text or fill only for destructive operations.
- Disabled: low contrast neutral but still legible.
- Loading state: preserve button width and label context.

### Status Badges

Statuses:

- `ready`: success text and soft green background.
- `needs-fix`: warning text and soft amber background.
- `running`: primary/info blue text and soft blue background.
- `completed`: success styling with completed label.
- `failed`: danger text and soft red background.

Each badge must include text. Do not rely on color alone.

### Tables and Lists

Project lists should support dense scanning:

- project display name or eid
- source
- status
- validation error count
- workplan id
- updated time

Use skeleton rows for loading. Use empty states that explain the next action.

### Forms

Stock and process editors should use explicit labels, inline validation, and stable control sizes. Process tool data should expose the nine tool fields as separate inputs, while preserving CSV serialization for backend compatibility.

### Drawers and Panels

Use a drawer for detail on smaller layouts and a side panel on wide layouts. The detail view should keep VM Start and validation visible without forcing the user to hunt through raw JSON.

## Motion

Motion should be limited to state transitions:

- drawer open/close
- row selection
- loading skeleton shimmer if subtle
- success/error notice enter/exit

Use 150-220ms ease-out transitions. Respect `prefers-reduced-motion`.

## Responsive Behavior

Breakpoints:

- 320px: single column, drawer becomes full screen.
- 768px: source selection and project list stack vertically.
- 1024px: two-column console layout.
- 1440px: wider list and detail surfaces with denser metadata.

Do not shrink text with viewport width. Reflow layout and truncate long IDs with copy affordances where needed.

## React Implementation Notes

- Use Vite + React + TypeScript.
- Use TanStack Query for server state and request deduplication.
- Fetch independent resources in parallel where possible.
- Avoid barrel imports for large libraries.
- Keep feature-specific logic under `src/features/*`.
- Keep API DTO types close to the API client.
- Derive display state during render when possible instead of mirroring it in effects.
- Use stable query keys for list filters, detail reads, annotations, stocks, and source projects.

## Quality Gates

Before shipping major UI changes:

- TypeScript build passes.
- Lint passes.
- Production build passes.
- Keyboard navigation works for list selection, drawer close, forms, and VM actions.
- Responsive views at 320px, 768px, 1024px, and 1440px are checked.
- `npx impeccable detect vm_middle/frontend` is run when the React app exists.
