# Inquiry reference alignment

Base: `61160a6`. The user says the delivered home screen does not match their supplied
reference. The current version over-emphasises the question as a display headline;
the reference instead uses a restrained question prompt in a spacious left entry
column, balanced by the temple surface on the right.

Boundary: browser-home layout and typography only. Preserve the just-reviewed
textarea, blank-input feedback, explicit non-executing handoff, navigation, theme
control and self-building temple integration. The TUI already has the matching
question-first semantics and needs no visual rewrite for this browser-reference fix.

Acceptance: at desktop width the workbench bar remains continuous with the main
surface; the question prompt is compact rather than poster-scale; the labelled entry
control is plainly interactive and has generous usable width; the temple remains in
the right column; no behavior changes.

Validation: desktop rendering was visually inspected against the supplied reference;
the 49 browser UI tests and diff check pass. Independent review found the initial
fixed grid tracks could overflow at 801–1100px widths; they were replaced with
shrinkable tracks and a bounded gap. The existing 800px single-column breakpoint
remains in force.
