# Typed advisory and writer material prompts

Follow-up to the AI-native architecture audit, based on `34e3395`. The maintainer review found
Laya's actual typed question and the writer's evidence-reporting guidance still embedded in Python.

The catalog now declares Laya's typed transport, actual model policy, schema, advisory callers,
and prompt scope. The typed endpoint receives those versioned question artifacts; receipts identify
actual redacted questions, request, model, schema, definition, catalog and run bundle. Cache entries
must follow the privacy setting and prompt revision. Laya remains advisory and cannot skip the
scientific reasoning call. The writer material guidance moves into a catalogued Markdown artifact;
materialization records its hash without replacing the pinned official upstream writing prompts.

Acceptance: typed contract negative fixtures, actual request receipt hashes, cache revision and
opt-out, preserved failed-call usage, primary-agent non-bypass, and custom writer prompt provenance.
Run affected agent/writer suites, Ruff and mypy. Obtain independent coordinator review before commit.

A final review also identified the evaluation objective as locally authored AI input.
Register it as a separate task template, not a fictional chat agent, preserve exact
rendered objective bytes, and include its source/version in the same catalog manifest.
