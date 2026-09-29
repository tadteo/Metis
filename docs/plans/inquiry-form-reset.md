# Inquiry form reset

Base: `f6ac9ba`. The user corrected the previous visual interpretation. On Home,
“Metis welcomes you.” is the top bar title. The content begins with only “What
question brings you here?” and gives the writing field the strongest emphasis.
This supersedes the placement and copy decisions in the earlier
`inquiry-entry-refinement` and `inquiry-reference-alignment` plans.

Scope: Home presentation in the browser and corresponding TUI welcome placement.
Preserve the current question handoff, theme, temple, saved research and setup flows.

Acceptance: the welcome is absent above the question; no extra introduction appears
between the question and field; the field has an explicit label, a clear writing cue
and visible focus; the existing button carries the question into setup without
creating a run. Home remains readable at desktop and narrow widths in both themes.

Check the actual rendered Home, including keyboard entry, then run the affected
browser and terminal tests and obtain independent review before integration.

Implementation and evidence: the browser top bar displays the welcome on Home and
the research workspace title while inspecting a run. The Home content has only the
question heading before a labelled textarea with a direct writing placeholder,
contrasting surface and focus state. The TUI welcome moved into its masthead and its
field guidance matches the browser. The unchanged handoff carries the question into
setup and creates no run.

Visual inspection used a temporary localhost server with synthetic text. Desktop
charcoal and cream renderings showed the welcome in the bar, question above the field,
and the temple beside it. At 390px the welcome remains visible and the form uses the
full column. Independent review found the form too narrow at 801–1000px; after raising
the single-column breakpoint to 1000px, the refreshed 900px cream rendering showed a
full-width form with the temple below. Keyboard entry, Tab to Continue, and Enter
opened setup with the question in Research question and no run created.

Validation: browser logic suite 49 passed; TUI, inquiry and temple suites 36 passed;
Ruff lint/format and `git diff --check` passed. No paid model or research execution.
