# Product

## Register

product

## Users

VM Middle is used by manufacturing researchers, machining engineers, and platform operators who need to turn Digital Thread project data into Virtual Machining simulation jobs. They work with ISO 14649 and DP source projects, NC files, workplans, stock definitions, tool metadata, VM execution status, and simulation result registration.

Users are typically in an expert workflow. They need to scan project state quickly, identify missing or invalid machining data, correct stock or tool fields, start a VM job only when the project is ready, and verify whether results were uploaded back to the platform.

## Product Purpose

VM Middle connects ISO/DP manufacturing data with the UNI CNC Virtual Machining server. It collects project, material, cutting tool, and NC file data, generates `project.prj` and `ncdata.zip`, starts VM simulation jobs, polls job status, and registers VM results back into the source platform as `dt_file` assets.

The React frontend should make this pipeline visible and controllable. Success means a user can confidently create a VM project, inspect validation issues, fix editable data, start a simulation with the right result upload mode, and understand the current lifecycle state without reading raw API responses.

## Brand Personality

Precise, trustworthy, work-focused.

The interface should feel like an engineering operations console backed by KITECH's institutional identity. It should be calm, structured, and authoritative. It should not feel like a marketing page, a demo toy, or a decorative AI-generated dashboard.

## Anti-references

- Avoid oversized landing-page composition, hero sections, decorative cards, and promotional copy.
- Avoid generic SaaS gradients, purple-blue glow aesthetics, glassmorphism, and nested card layouts.
- Avoid low-density layouts that force excessive scrolling for table-heavy operational work.
- Avoid color as the only status indicator. Status must include text, iconography, or shape in addition to color.
- Avoid hiding core actions behind ambiguous icons or modal-first flows.

## Design Principles

1. Make state legible first. Every project should clearly show source, status, validation, workplan, and last VM activity.
2. Keep expert workflows dense but calm. Use compact tables, drawers, tabs, and panels without turning every section into a card.
3. Preserve the VM data contract. UI-only metadata must not pollute `project.prj` or VM upload payloads.
4. Prefer predictable controls. Tables, filters, segmented controls, radios, selects, and inline validation are better than invented interactions.
5. Surface risk early. Destructive, external, or irreversible actions such as VM start and JSON result upload need explicit context before the user triggers them.

## Accessibility & Inclusion

Target WCAG 2.1 AA for text, controls, focus states, and status indicators. The UI must support keyboard navigation for filtering, selecting projects, editing stock/process fields, opening and closing detail drawers, and triggering primary actions.

Color blindness considerations are important because the interface is status-heavy. Ready, running, needs-fix, completed, and failed states must not rely on color alone. Motion should be minimal and respect reduced-motion preferences.
