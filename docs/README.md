# Metis documentation

Metis takes a research question through literature, experiments, review and manuscript
writing while keeping the complete attempt history. These guides describe the current
repository. Metis is an experimental preview; read the [fidelity report](fidelity.md)
for the distinction between implemented behavior and measured scientific capability.

## Start here

1. [Getting started](getting-started.md): install, run the offline demo, configure
   models and compute, start a live inquiry, and update safely.
2. [Using Metis](usage.md): web/TUI navigation, provider presets, settings and run controls.
3. [CLI reference](cli.md): command help generated from the current argument parser.
4. [Troubleshooting](troubleshooting.md): installation, credentials, quotas, compute
   and saved-run recovery.

No model account is needed for the synthetic demo. Live research can incur API and
compute charges. Creating a run and checking setup do not start model calls.

## Configure your workspace

| Topic | Guide |
|---|---|
| Providers, role routing, model selection and quotas | [Model routing](model-routing.md) |
| Global, workspace and project model settings | [Settings inheritance](settings-inheritance.md) |
| Containers, native sandbox, environments, GPU and Slurm | [Execution options](execution-options.md) |
| SSH controllers, MFA, reconnection and storage | [Remote connections](remote.md) |
| Manuscript runtime, reference assets and PDF generation | [PaperOrchestra](paper-orchestra.md) |
| Model costs, reservations and operational limits | [Accounting](accounting.md) |
| Private data, credentials and execution trust boundaries | [Security and privacy](../SECURITY.md) |
| Optional non-generative advisory adapter | [Laya](laya.md) |

## Understand and verify research

| Topic | Guide |
|---|---|
| Recorded runs, protocols, resume and behavior identity | [Reproducibility](reproducibility.md) |
| Scientific contracts, stopping rules and local deviations | [Paper specification](paper-spec.md) |
| Implementation evidence and unmeasured capability | [Fidelity report](fidelity.md) |
| Public tasks, real baselines and paired ablations | [Capability evaluation](evaluation.md) |
| Independent experiment/protocol inspection | [Inspection](inspection.md) |
| Numerical, statistical and citation claims | [Claim integrity](claim-integrity.md) |
| Registered paired analysis and reproduction | [Statistical analysis](statistical-analysis.md) |
| Released review prompts and orchestration limits | [ScholarPeer](scholarpeer.md) |
| Literature provenance and paper identity | [Literature identity](literature-identity.md) |

The [public regression example](../examples/README.md) uses live models and can incur
charges. It is separate from the scripted offline demo. Software checks and synthetic
examples do not establish autonomous research quality or ScientistTwo parity.

## Develop and extend

Read [Contributing](../CONTRIBUTING.md) and [the development workflow](development.md)
before changing code. Update setup and usage docs in the same change as their behavior.
CI checks current-guide local links/images/anchors and generated command help; prose
accuracy and external source changes still require review.

- [Architecture](architecture.md): module boundaries, typed contracts and execution.
- [AI system](ai-system.md): versioned agents, prompts, tools and workflow.
- [Coding harness](coding-harness.md) and [coding worker design](coding-worker-design.md):
  repository editing, feedback, inspection and checkpoints.
- [Agentic execution patterns](agentic-execution-patterns.md): external execution and recovery.
- [Design and voice](../VIBE.md): shared interface aesthetic and acceptance evidence.
- [Primary-source audit](primary-source-audit.md) and
  [retrieval design](scientist-two-retrieval-design.md): scientific provenance.

[Plans](plans/), [independent reviews](reviews/) and [evidence](evidence/) preserve
historical development decisions and measurements. Use current guides for setup;
historical commands and limitations record what was true at that task's revision.
