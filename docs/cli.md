# Metis CLI reference

[Documentation](README.md) · [Getting started](getting-started.md) · [User guide](usage.md)

Generated from the argument parser by `scripts/check_docs.py --write-cli`. Do not edit command help here; CI checks it against the source.

Run commands from the checkout as `uv run --no-sync metis …`. Place global `--state-dir` and `--db-dir` options before the command. `autoresearch` is a compatibility alias.

Creating a run does not execute it. `demo` runs the synthetic fixture immediately; `run` and `resume` start research and can incur charges. See the [user guide](usage.md) for settings recipes, control semantics and privacy.

## Commands

- [metis](#metis)
- [metis theme](#metis-theme)
- [metis setup](#metis-setup)
- [metis settings](#metis-settings)
- [metis init](#metis-init)
- [metis new](#metis-new)
- [metis run](#metis-run)
- [metis demo](#metis-demo)
- [metis status](#metis-status)
- [metis serve](#metis-serve)
- [metis fidelity](#metis-fidelity)
- [metis system](#metis-system)
- [metis validate-specs](#metis-validate-specs)
- [metis adopt-behavior](#metis-adopt-behavior)
- [metis evaluate](#metis-evaluate)
- [metis tui](#metis-tui)
- [metis check](#metis-check)
- [metis pause](#metis-pause)
- [metis resume](#metis-resume)
- [metis cancel-experiment](#metis-cancel-experiment)
- [metis intervene](#metis-intervene)
- [metis budget](#metis-budget)
- [metis export](#metis-export)
- [metis remote](#metis-remote)
- [metis remote hosts](#metis-remote-hosts)
- [metis remote list](#metis-remote-list)
- [metis remote add](#metis-remote-add)
- [metis remote login](#metis-remote-login)
- [metis remote check](#metis-remote-check)
- [metis remote install](#metis-remote-install)
- [metis remote connect](#metis-remote-connect)
- [metis remote status](#metis-remote-status)
- [metis remote disconnect](#metis-remote-disconnect)

## metis

```text
usage: metis [-h] [--state-dir STATE_DIR] [--db-dir DB_DIR] COMMAND ...

Metis · Research atelier

options:
  -h, --help            show this help message and exit
  --state-dir STATE_DIR
                        Private runtime root (or AUTORESEARCH_HOME)
  --db-dir DB_DIR       Separate SQLite directory (or AUTORESEARCH_DB_DIR)

Commands:
  COMMAND
    theme               Choose the shared charcoal / cream appearance
    setup               Guided first-time setup (no research execution)
    settings            Manage private defaults for future runs
    init                Write an example configuration
    new                 Create a research run
    run                 Execute until completion or a checkpoint limit
    demo                Run the complete offline demonstration
    status              Inspect a run, or list every run
    serve               Open the local web console
    fidelity            Validate and print the fidelity evidence matrix
    system              Inspect agents, prompts, routing and the workflow without model
                        calls
    validate-specs      Validate the AI specification bundle without execution
    adopt-behavior      Explicitly bind an unpinned legacy run to current AI behavior
    evaluate            Prepare, baseline, run or inspect real public research tasks
    tui                 Open the interactive terminal research console
    check               Check live configuration and execution readiness
    pause               Pause a checkpointed run
    resume              Resume a checkpointed run
    cancel-experiment   Cancel a pending Slurm experiment after pausing the run
    intervene           Record human feedback and optionally change stage
    budget              Explicitly update a paused run's budget limits
    export              Export a shareable summary, or opt into private data
    remote              Manage SSH research controllers and private tunnels

Start here: setup → tui / serve → new → run
Inspect: status · system · fidelity
Manage: settings · theme · pause · resume · budget · export
```

## metis theme

```text
usage: metis theme [-h] [{charcoal,cream}]

positional arguments:
  {charcoal,cream}

options:
  -h, --help        show this help message and exit
```

## metis setup

```text
usage: metis setup [-h] [--config CONFIG] [--check]

options:
  -h, --help       show this help message and exit
  --config CONFIG  Start from an existing configuration
  --check          Print readiness without interactive prompts
```

## metis settings

```text
usage: metis settings [-h] [--base-url BASE_URL] [--tier {free,paid}] [--no-key]
                      [--json] [--scope {global,workspace,project}] [--project PROJECT]
                      [{show,import,set,check,profile,inherit,preset}] [values ...]

positional arguments:
  {show,import,set,check,profile,inherit,preset}
  values                import FILE, set DOTTED.PATH JSON_VALUE, profile google-flash,
                        or preset list | show PROVIDER:MODEL | add PROVIDER:MODEL

options:
  -h, --help            show this help message and exit
  --base-url BASE_URL   preset add: endpoint for a local compatible server
  --tier {free,paid}    preset add: free tier (published free limits) or paid plan (no
                        rate limits)
  --no-key              preset add: do not prompt for an API key
  --json                preset list/show: machine-readable output
  --scope {global,workspace,project}
                        Edit inherited model defaults only
  --project PROJECT     Absolute project path for project model overrides
```

## metis init

```text
usage: metis init [-h] [--demo] [path]

positional arguments:
  path

options:
  -h, --help  show this help message and exit
  --demo      Configure offline demonstration mode
```

## metis new

```text
usage: metis new [-h] [--title TITLE] --objective OBJECTIVE [--config CONFIG] [--demo]
                 [--paper PAPER] [--project PROJECT] [--budget BUDGET] [--configured]

options:
  -h, --help            show this help message and exit
  --title TITLE
  --objective OBJECTIVE
  --config CONFIG
  --demo
  --paper PAPER         Associated PDF/text file, URL, DOI or arXiv ID; repeatable
  --project PROJECT     Optional existing project folder; copied privately
  --budget BUDGET       One model budget including research intake
  --configured          Use imported legacy experiment configuration
```

## metis run

```text
usage: metis run [-h] [--steps STEPS] id

positional arguments:
  id

options:
  -h, --help     show this help message and exit
  --steps STEPS
```

## metis demo

```text
usage: metis demo [-h] [--title TITLE] [--objective OBJECTIVE] [--steps STEPS]

options:
  -h, --help            show this help message and exit
  --title TITLE
  --objective OBJECTIVE
  --steps STEPS
```

## metis status

```text
usage: metis status [-h] [--json] [id]

positional arguments:
  id

options:
  -h, --help  show this help message and exit
  --json      Full machine-readable output (automatic in pipes)
```

## metis serve

```text
usage: metis serve [-h] [--port PORT] [--config CONFIG]

options:
  -h, --help       show this help message and exit
  --port PORT
  --config CONFIG
```

## metis fidelity

```text
usage: metis fidelity [-h]

options:
  -h, --help  show this help message and exit
```

## metis system

```text
usage: metis system [-h] [--config CONFIG] [--run RUN_ID] [--role ROLE] [--mermaid]

options:
  -h, --help       show this help message and exit
  --config CONFIG
  --run RUN_ID     Inspect the frozen definitions of an existing run
  --role ROLE      Inspect one agent and its resolved instructions
  --mermaid        Print the executable workflow as a Mermaid graph
```

## metis validate-specs

```text
usage: metis validate-specs [-h] [--config CONFIG]

options:
  -h, --help       show this help message and exit
  --config CONFIG
```

## metis adopt-behavior

```text
usage: metis adopt-behavior [-h] id

positional arguments:
  id

options:
  -h, --help  show this help message and exit
```

## metis evaluate

```text
usage: metis evaluate [-h] [--config CONFIG] [--reference-config REFERENCE_CONFIG]
                      [--variant VARIANT] [--steps STEPS]
                      {prepare,baseline,run,report,variants} directory

positional arguments:
  {prepare,baseline,run,report,variants}
  directory

options:
  -h, --help            show this help message and exit
  --config CONFIG
  --reference-config REFERENCE_CONFIG
  --variant VARIANT
  --steps STEPS
```

## metis tui

```text
usage: metis tui [-h] [--config CONFIG] [--run RUN_ID]

options:
  -h, --help       show this help message and exit
  --config CONFIG  Load configuration for new research projects
  --run RUN_ID     Select an existing run without starting it
```

## metis check

```text
usage: metis check [-h] --config CONFIG

options:
  -h, --help       show this help message and exit
  --config CONFIG
```

## metis pause

```text
usage: metis pause [-h] id

positional arguments:
  id

options:
  -h, --help  show this help message and exit
```

## metis resume

```text
usage: metis resume [-h] [--clear-quota] id

positional arguments:
  id

options:
  -h, --help     show this help message and exit
  --clear-quota  Forget recorded model quota exhaustion (after a key or tier change)
```

## metis cancel-experiment

```text
usage: metis cancel-experiment [-h] id

positional arguments:
  id

options:
  -h, --help  show this help message and exit
```

## metis intervene

```text
usage: metis intervene [-h] --note NOTE
                       [--stage {intake,limitations,verify_limitations,generate_ideas,novelty,filter_ideas,baseline,subset,subset_critic,subset_engineer,full,full_critic,full_engineer,evolve,select,ablation_plan,ablation,ablation_critic,ablation_refine,compare,draft,peer_review,rebuttal_plan,rebuttal,revise,meta_review,meta_refine,integrity,complete}]
                       id

positional arguments:
  id

options:
  -h, --help            show this help message and exit
  --note NOTE
  --stage {intake,limitations,verify_limitations,generate_ideas,novelty,filter_ideas,baseline,subset,subset_critic,subset_engineer,full,full_critic,full_engineer,evolve,select,ablation_plan,ablation,ablation_critic,ablation_refine,compare,draft,peer_review,rebuttal_plan,rebuttal,revise,meta_review,meta_refine,integrity,complete}
```

## metis budget

```text
usage: metis budget [-h] [--usd USD] [--calls CALLS] [--experiments EXPERIMENTS]
                    [--wall-seconds WALL_SECONDS]
                    id

positional arguments:
  id

options:
  -h, --help            show this help message and exit
  --usd USD
  --calls CALLS
  --experiments EXPERIMENTS
  --wall-seconds WALL_SECONDS
```

## metis export

```text
usage: metis export [-h] [--include-private] id target

positional arguments:
  id
  target

options:
  -h, --help         show this help message and exit
  --include-private  Include potentially sensitive research artifacts
```

## metis remote

```text
usage: metis remote [-h]
                    {hosts,list,add,login,check,install,connect,status,disconnect} ...

positional arguments:
  {hosts,list,add,login,check,install,connect,status,disconnect}
    hosts               List discovered SSH configuration hosts
    list                List saved remote profiles
    add                 Save a remote profile; does not connect or install
    login               Sign in through interactive SSH, including MFA
    check               Probe SSH and remote readiness without installing
    install             Explicitly install the remote research runtime
    connect             Start/reuse the remote controller and keep its tunnel open
    status              Inspect remote controller/tunnel status
    disconnect          Disconnect a managed local tunnel; remote research continues

options:
  -h, --help            show this help message and exit
```

## metis remote hosts

```text
usage: metis remote hosts [-h]

options:
  -h, --help  show this help message and exit
```

## metis remote list

```text
usage: metis remote list [-h]

options:
  -h, --help  show this help message and exit
```

## metis remote add

```text
usage: metis remote add [-h] --host HOST [--port PORT] [--identity-file IDENTITY_FILE]
                        [--directory DIRECTORY] [--python PYTHON]
                        [--remote-state-dir REMOTE_STATE_DIR]
                        [--remote-db-dir REMOTE_DB_DIR] [--remote-config REMOTE_CONFIG]
                        name

positional arguments:
  name

options:
  -h, --help            show this help message and exit
  --host HOST           SSH alias, hostname or user@hostname
  --port PORT           SSH port; otherwise use SSH configuration
  --identity-file IDENTITY_FILE
                        Local SSH identity path (never a password)
  --directory DIRECTORY
  --python PYTHON
  --remote-state-dir REMOTE_STATE_DIR
                        Remote research files and experiment workspaces (for example
                        project storage)
  --remote-db-dir REMOTE_DB_DIR
                        Controller SQLite directory on persistent host-local storage
  --remote-config REMOTE_CONFIG
```

## metis remote login

```text
usage: metis remote login [-h] name

positional arguments:
  name

options:
  -h, --help  show this help message and exit
```

## metis remote check

```text
usage: metis remote check [-h] name

positional arguments:
  name

options:
  -h, --help  show this help message and exit
```

## metis remote install

```text
usage: metis remote install [-h] name

positional arguments:
  name

options:
  -h, --help  show this help message and exit
```

## metis remote connect

```text
usage: metis remote connect [-h] [--open] name

positional arguments:
  name

options:
  -h, --help  show this help message and exit
  --open      Open the private dashboard in a browser
```

## metis remote status

```text
usage: metis remote status [-h] name

positional arguments:
  name

options:
  -h, --help  show this help message and exit
```

## metis remote disconnect

```text
usage: metis remote disconnect [-h] name

positional arguments:
  name

options:
  -h, --help  show this help message and exit
```
