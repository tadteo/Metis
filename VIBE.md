# Metis — a living place of inquiry

Metis should feel like an ancient but living intelligence whose domain the user enters:
part laboratory, part archive, part temple of inquiry. The experience is calm, precise,
curious and quietly Greek. Cream and charcoal, generous space and deliberate typography
make the work feel considered. Terracotta marks a choice or a point of attention.

This is the authority for product aesthetic, interface voice and interaction design
across GUI, TUI and CLI. Read it before changing layout, navigation, onboarding,
settings, appearance or user-facing copy. The [development workflow](docs/development.md)
controls delivery; [architecture](docs/architecture.md) controls module boundaries;
[scientific contracts](docs/paper-spec.md) control research behavior. Aesthetic work
must preserve those contracts and complete evidence. This guide does not change the
instructions used by scientific agents.

## Voice: gracious host, rigorous scientist

**“Metis welcomes you. What question brings you here?”**

Speak with warmth at the entrance and precision at the point of action. Use concise,
timeless language. Welcome questions, follow evidence and make room to revise beliefs.
Treat uncertainty as something to investigate. Confidence comes from stating what is
known, what is missing and what the user can do next. Keep mythic character in the
identity and atmosphere; name actions, costs, errors and credentials literally.

| Situation | Direction | Example |
|---|---|---|
| Welcome | Invite a question. | What question brings you here? |
| Missing setup | Name the prerequisite and its next step. | Add a source directory, then check setup. |
| Saved progress | State what was saved and its scope. | Settings saved for future runs. |
| No evidence | Describe the record accurately. | No measured results recorded yet. |
| Uncertain outcome | Separate observation from conclusion. | This result needs further evidence. |
| Execution failure | Preserve the failure and offer inspection. | The experiment failed. Open its receipt to inspect the error. |

Use short action labels such as **New research**, **Check setup**, **Save settings**,
**Start**, **Pause** and **Review evidence**. Use contextual explanations beside the
control that needs them. Avoid claims of omniscience, mystical promises, theatrical
mythology and generic assistant chatter. Synthetic examples remain explicitly synthetic.

## Visual language: charcoal, cream, a trace of terracotta

The exact matched light/dark values live in
[interface.json](src/autoresearch/assets/interface.json); use its semantic roles.
It is the colour authority, so update shared tokens and their consumers together
instead of maintaining independent per-interface palettes.

- Let warm charcoal and cream carry backgrounds, surfaces, text and primary controls.
  Dark mode uses brown charcoal and warm light text; light mode uses cream and dark ink.
- Use terracotta sparingly for active indicators, small marks, links, focus and selected
  states. Keep large surfaces quiet. Use labelled status colours for outcomes.
- Build hierarchy with proportion, spacing, typography and fine borders. Group related
  content; leave separation between a question, its actions and supporting evidence.
- In the GUI, use restrained editorial headings and readable body text. Monospace suits
  metadata, commands and measurements. In the TUI, use alignment, weight and spacing
  within the user's terminal font. Keep decorative Greek or pixel motifs secondary.
- Keep text and focus readable in both themes. Convey status with words as well as
  colour. Controls need clear labels, keyboard access and a visible focused state.

Home may carry a self-building architectural temple: a local, finite animation with
rotation and a single corner replay icon. Keep pause/reset available by keyboard. Respect reduced motion and keep inquiry actions
primary. The temple is an identity metaphor, never a research-progress indicator.
The browser uses block geometry from `static/temple.json`; the terminal uses a simpler
structural outline so columns and pediments stay legible in character cells. Both
share the packaged timing and initial view. Their renderers are `static/temple.js`
and `tui_temple.py` / `temple.py`. Keep the art free of framing rules and ground grids.

The mood is editorial and architectural. The supplied moodboard and references inform
proportion and restraint; usability decides how those qualities become working screens.

## Interaction: one clear place to begin

Home welcomes a question and offers a clear next step. Carry the question into setup.
Explain missing code, data, model or execution prerequisites where the user can resolve
them. Preserve partial setup and edits when moving between sections. Reopen those choices
through Settings. Keep creating an inquiry separate from starting research.

Use a shared information hierarchy: Home, Research, Settings, Connections and a reachable
guide. Within research, lead with Overview, Experiments, Activity and Manuscript; put
specialist inspection behind a clearly labelled command or detail view. Use consistent
names across interfaces while respecting each medium:

In the GUI, the bottom-left connection status opens a compact picker near the top of
the screen. Keep the current local or SSH location visible in that status; let the
picker lead to detailed connection setup without filling the navigation column.

| Surface | Expected experience |
|---|---|
| GUI | Visible navigation, a focused main workspace, responsive forms and contextual actions. |
| TUI | The same destinations and research hierarchy; a sidebar when space permits, compact navigation otherwise, and scrollable reading areas. |
| CLI | Concise help, guided setup when interactive, explicit commands and reliable machine-readable output for scripts. |

Show the question, current state and next useful action before technical detail. Make
measurements and diagnostics readable, with complete original receipts reachable through
progressive disclosure. Preserve failed attempts and uncertain outcomes. A mounted widget
or stored record counts as accessible only when the user can actually reach and read it.

Keep GUI operations discoverable through visible navigation and inspection views; terminal
commands remain available for their surfaces. Display run
identity when execution actions are available; shortcuts must respect that context. Moving
between pages must leave keyboard focus on a visible control. Honour plain output and
terminal colour preferences; presentation must not change machine-readable output.

## Development structure and ownership

Keep shared product decisions shared and adapt their rendering to each surface.

| Concern | Source / ownership |
|---|---|
| Design intent and voice | This document; older [voice guide](docs/interface-voice.md) points here. |
| Theme values and persistence | [Colour tokens](src/autoresearch/assets/interface.json), [appearance](src/autoresearch/appearance.py). Appearance remains separate from research configuration. |
| GUI presentation | [HTML](src/autoresearch/static/index.html), [CSS](src/autoresearch/static/style.css), [browser interactions](src/autoresearch/static/app.js). |
| TUI presentation | [Layout and navigation](src/autoresearch/tui.py), [readable evidence projections](src/autoresearch/tui_reading.py). Complete records remain inspectable. |
| CLI presentation and setup | [Terminal style](src/autoresearch/terminal_style.py), [CLI](src/autoresearch/cli.py), [guided setup](src/autoresearch/setup_cli.py). |
| Shared setup rules | [Settings](src/autoresearch/settings.py) and [readiness checks](src/autoresearch/setup.py); reuse their rules across surfaces. |
| Usage and delivery | [User guide](docs/usage.md), [development workflow](docs/development.md), [contributing](CONTRIBUTING.md), persisted plans and independent reviews. |

For an interface change, record the user journey and affected surfaces in its task plan.
Use existing shared rules and tokens; keep presentation separate from engine decisions.
If a new shared convention is needed, update this guide with the reason. An intentional
change to the accepted aesthetic belongs in the plan and review, not an unexplained drift.

## Evidence before calling an interface finished

Scale validation to the change using [CONTRIBUTING.md](CONTRIBUTING.md). For affected
screens, inspect actual rendering and interaction, not only component existence:

- Check light and dark themes; check TUI at 80×24 and 120×40, and GUI at desktop and a
  narrow viewport. Confirm labels, selected states and primary actions remain readable.
- Follow the changed journey by keyboard, including returning from menus or dialogs.
  Expand and scroll complete records. Verify the final focused control is visible.
- Exercise relevant empty, missing-setup, saved-progress, busy and failure states.
  Confirm navigation retains edits and never starts research implicitly.
- Keep screenshots public and synthetic. Record what was visually inspected and what
  automated checks passed in the plan; obtain independent review through the normal
  development sequence. Passing software checks makes no claim about research quality.

For documentation-only changes, check pointers and source references and review the
instructions for consistency. Runtime tests are needed when executable behavior changes.

## Model settings

The browser Settings destination is a full page with global, workspace and project
scopes. State the loaded scope and inherited source beside explicit override
controls. Keep inquiry preparation in its focused dialog. Scoped model defaults
never imply shared credentials or changes to saved runs.

The default model view is a compact Available to Metis inventory beneath Appearance,
with local access status, Configure and Add model. System 1 / Laya is separate.
Project model permissions belong in project settings. Keep explicit routing and
scope inheritance behind Advanced model settings; new inquiries move from Project
to Review without a required model step. Preserve the inquiry form on that detour.
