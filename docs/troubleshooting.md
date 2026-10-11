# Troubleshooting Metis

[Documentation](README.md) · [Getting started](getting-started.md) · [User guide](usage.md)

Inspect the reported error and the run's complete receipt before retrying. Failed
attempts are part of the research record. Setup checks make no model calls; a
successful check confirms checked local prerequisites, not provider access or a
scientific result.

## Installation and console

| Symptom | Next action |
|---|---|
| `uv` is not found | Follow the [official uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/) and reopen your shell if its PATH changed. |
| Python is too old or dependencies are missing | From the Metis checkout, run `uv sync --frozen`, then use `uv run --no-sync metis`. Python 3.11+ is required. |
| `metis` is not found | Use `uv run --no-sync metis` from the checkout; the package name is `metis-research`. |
| Browser cannot reach the console | Keep `metis serve` running, use the printed loopback URL, and check its terminal error. If 8765 is occupied, use `uv run --no-sync metis serve --port 8766`. |
| TUI will not open | Use an interactive terminal with `uv run --no-sync metis tui`; scripts and pipes should use the CLI. |
| A saved run is missing | Check the controller connection and state directory. `AUTORESEARCH_HOME` or `--state-dir` must match the original run; the database can also be separated with `AUTORESEARCH_DB_DIR` / `--db-dir`. |

## Models, credentials and quotas

| Symptom | Next action |
|---|---|
| Key missing, or disappeared after restart | Use **Settings → Available to Metis → Configure**, or **＋ Add provider**, on the controller host. Session-only storage expires when the server stops. Environment variables must be present in the process that launches Metis; `.env` is not loaded automatically. |
| Vault unavailable | Choose **Keep key → This server session**, or supply the named environment variable. A previously saved vault key cannot be inspected or removed until vault access returns. |
| HTTP 401/403 or unavailable model | Check the selected provider, endpoint, model ID, key and account entitlement. Local readiness does not authenticate against the provider. |
| No eligible model / prompt above a limit | Inspect `uv run --no-sync metis settings check`. Enable a suitable model and check its context/JSON capabilities, project permissions and actual free/paid plan. Create a new run when changing routing. |
| HTTP 429 or quota wait | Check the provider's quota and recorded reset time. [Quota waiting](usage.md#wait-for-provider-quota-opt-in) is opt-in; keep a runner active to advance after the scheduled time. Use `resume --clear-quota` only after deliberately changing a key or plan. |
| Budget exhausted | Inspect costs and the limiting call, experiment or duration count. Deliberately update the necessary absolute limit, then resume. The provider's bill and compute costs are separate from Metis's estimates. |

See [provider setup](usage.md#add-providers-from-presets), [model routing](model-routing.md)
and [accounting](accounting.md). Keep keys out of logs and public issue reports.

## Experiments and manuscript writing

| Symptom | Next action |
|---|---|
| Docker unavailable / image missing | Start the daemon and run **Check setup**. Prepare the dependency image required by the project; experiments have no network by default. |
| Podman, Apptainer or sandbox check fails | Follow the backend's prerequisites and limits in [execution options](execution-options.md), then recheck. |
| Wrong experiment Python or missing package | In the browser use **New research → Execution → Python environment**, or TUI **Settings → Execution**, to choose the environment prefix; or prepare the selected container image. Environments must work without activation hooks. |
| Source, data or evaluator missing | Check paths on the controller and execution host, admitted-file patterns and protected inputs. On Slurm, compute nodes need access to the workspace. |
| Writer fails despite working experiments | Follow [PaperOrchestra setup](paper-orchestra.md#setup). Its pinned assets, runtime, credentials and execution settings are separate; read its compile/request diagnostics. Native Anthropic text models currently require a compatible model for writing roles. |
| Citation or integrity check unresolved | Inspect the retrieval or protected-evaluator receipt. Restore actual evidence/access; a supplied reference or model assertion cannot replace verification. |

The [startup table](usage.md#resolve-common-startup-problems) has additional backend
diagnostics. [Remote connections](remote.md) covers host identity, MFA, shared
storage and the requirement for a persistent host-local SQLite directory.

## Saved runs and upgrades

| Symptom | Next action |
|---|---|
| Resume reports behavior/package drift | Use the recorded installation and unchanged source for that run. Updated settings apply to future runs; an upgrade cannot silently replace archived behavior. Read [behavior identity](reproducibility.md#ai-behavior-identity). |
| Pause appears slow | Wait for the active durable checkpoint. Pause does not immediately kill a running call or experiment. |
| Uncertain interrupted experiment or writer | Inspect scheduler/process state and receipts before resuming. Do not blindly resubmit while work may still be running; see [reproducibility](reproducibility.md) and [writer recovery](paper-orchestra.md#checkpoints-and-artifacts). |
| SSH disconnected but work continues | The remote controller continues after a tunnel closes. Reconnect to the same physical host; disconnect is not pause or cancellation. |

## Report a problem

Use the [GitHub bug form](https://github.com/tadteo/Metis/issues/new?template=bug_report.yml).
Include the Metis commit (`git rev-parse HEAD`), OS/Python, backend, exact command,
expected behavior and a minimal **redacted** error or synthetic reproduction. Say
which setup checks passed. Do not upload your private Store, raw research prompts,
keys, SSH dashboard capability URL or unreviewed exports. Follow
[SECURITY.md](../SECURITY.md) for a security issue.
