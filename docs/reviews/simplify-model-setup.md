# Independent review: model setup entry

Base: `83ab407`. Scope: the `codex/simplify-setup` changes described in `docs/plans/simplify-model-setup.md`. An independent agent read the diff and guidance without editing files.

The first review found two P2 issues. Invalid key-like input was mirrored into the help text before validation, and Settings' CSS-reordered steps disagreed with DOM/keyboard order. The implementation now clears syntactically invalid input on the field's input event before form handlers run, uses only validated variable names in help text, and moves the actual navigation nodes for each mode. Browser tests cover both paths; a browser walkthrough confirmed invalid input clears immediately and Settings accessibility order reads Model access → Project defaults → Review. The reviewer inspected both fixes and reported no remaining actionable issue.

Limitation: a value that itself matches the environment-variable naming pattern cannot be distinguished from a variable name without receiving or testing a credential. The form never uses that field as an API key. The guide now states the precise validation behavior. Readiness detects local configuration only; it does not authenticate with a provider. No live provider request or research-quality evaluation was reviewed.

The final review also found one P3 guide mismatch: README and usage still named old project setup options. Those labels now match the form. The reviewer checked the inspection-title change, guide wording and final labels, reran `node --test tests/test_web_ui.mjs` (46/46 passed), and reported no remaining actionable findings.
