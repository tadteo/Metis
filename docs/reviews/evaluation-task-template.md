# Evaluation task-template review

Base: `0047ecf`. Independent reviewer: coordinating root agent, before commit.
Scope: the remaining locally authored public evaluation research objective.

The reviewer requested moving this AI input into a versioned task resource while
preserving its role as task input, not inventing a chat-agent identity. The registered
`evaluation` template declares purpose, version, artifact and input variables.
The catalog rejects undeclared/missing variables, includes template bytes in its
digest/snapshot, and renders the same original objective. `prepare_suite` honors
configured specification bundles.

The reviewer approved the template boundary, strict variable checks and exact original
objective regression. The complete final focused suite passed: 101 tests across catalog,
Laya transport/provenance, writer prompts, task templates, public evaluation, agents,
architecture and official writer fixtures. Ruff passed and strict mypy passed for all
six changed implementation modules. The objective regression preserves every existing
train/test, protected-evaluator and significance restriction; no scientific criterion
was relaxed. These are software checks, not evidence of scientific capability parity.
