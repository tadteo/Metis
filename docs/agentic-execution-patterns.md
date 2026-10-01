# Related research systems: execution and candidate isolation

Checked 2026-10-01 against primary papers and current public main branches. Main-branch code may differ from the experiments in each paper. Sakana's **AI Scientist-v2 (April 2025)** is a different project from **ScientistTwo (September 2026)**.

1. **AI Scientist-v2 genuinely executes candidates concurrently.** Paper §3.2.2 explicitly says several nodes are selected and their children executed simultaneously; §3.2.1 separates prototype, baseline tuning, research execution and ablations, carrying a selected node into the next stage and running replications. The paper's checkpoints are research-tree states/code candidates, not evidence of Git worktrees or automatic training-checkpoint recovery. [Paper](https://arxiv.org/html/2504.08066v1#S3.SS2.SSS2)

2. **Its implementation uses a bounded process pool, GPU allocation, and worker directories.** `ParallelAgent` caps worker count at detected GPU count when GPUs exist, creates `ProcessPoolExecutor`, assigns a GPU per selected worker, and sets `CUDA_VISIBLE_DEVICES`. Workers use `workspace/process_<process-name>/working`, not Git worktrees. Successful result handling saves experiment/plot code and moves NumPy/PNG artifacts into a node-ID/process-ID results directory. Submission occurs before result collection, confirming real concurrency. GPU leases are released in `finally`; worker-future timeouts are logged. This is single-controller, batch-style scheduling, not demonstrated durable cluster scheduling or global resource arbitration across controllers. The GPU bookkeeping is local to one `ParallelAgent`; CPU/memory quotas are not implemented in these paths. [Code, especially initialization, `_process_node_wrapper`, `step`](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/ai_scientist/treesearch/parallel_agent.py)

3. **Failure records and code lineage are first-class, while runtime isolation is modest.** The node stores code, parent/children, metric, exception data, runtime, plot/metric-parsing code and results directory. [Journal](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/ai_scientist/treesearch/journal.py). The interpreter starts a child process, captures output/exceptions, interrupts at a wall-time limit, and attempts termination if interruption fails; this is not container isolation. [Interpreter](https://github.com/SakanaAI/AI-Scientist-v2/blob/main/ai_scientist/treesearch/interpreter.py). The README recommends the operator run the system inside a controlled sandbox such as Docker; it does not promise one container per experiment. [README](https://github.com/SakanaAI/AI-Scientist-v2)

4. **AIDE's tree search does not itself establish concurrency.** Algorithm 1 proposes, evaluates, records and chooses the next base in a sequential loop. A node is a whole script; edges record draft/debug/improve ancestry. [Paper](https://arxiv.org/html/2502.13138v1#S3). The open-source CLI likewise initializes one interpreter and repeatedly calls `agent.step`, saves the journal, and continues. [Run loop](https://github.com/WecoAI/aideml/blob/main/aide/run.py). Its journal keeps full code, parent links, metrics, errors and runtime, so branches remain inspectable without Git branches. [Journal](https://github.com/WecoAI/aideml/blob/main/aide/journal.py)

5. **AIDE isolates process state, not each candidate's filesystem.** `Interpreter.run` defaults to resetting the child process between scripts but uses the same configured workspace directory and `runfile.py`. It captures exceptions and enforces timeouts with interrupt/termination. No GPU leasing or per-candidate CPU/memory quotas are shown in this interpreter. A new Python process does not imply a fresh directory, a container, or elimination of artifacts from previous candidates. [Interpreter](https://github.com/WecoAI/aideml/blob/main/aide/interpreter.py)

6. **Modern Weco product terminology extends lineage, but do not infer its scheduler from a tree diagram.** Official docs define nodes as code+score+parent, baseline as step 0, and derived runs as branches in a shared lineage; users can launch several subtrees and compare lineage-best. These docs establish branching and traceability, not exact Git-worktree/container/GPU-allocation internals. The commercial Weco platform and open-source AIDE reference build must be discussed separately. [Weco concepts](https://docs.weco.ai/concepts/how-weco-works), [AIDE README distinction](https://github.com/WecoAI/aideml)

Practical inference for Metis: maintain a candidate/source lineage separately from execution attempts; use worktrees or snapshots for independent editing, then immutable source inputs and attempt-specific artifacts for execution. Add bounded compute scheduling independently of search policy. A research-tree child need not be merged as a software feature; competing scientific hypotheses can remain separate measured alternatives.

## General coding-agent and experiment infrastructure

**Parallel coding:** Claude Code documents one worktree/branch per independent
session, preventing edits from colliding. Git worktrees share repository storage
and normally repository configuration. This gives checkout separation; it does not
allocate GPUs or provide an OS security boundary. [Claude Code](https://code.claude.com/docs/en/common-workflows#run-parallel-sessions-with-worktrees),
[Git worktree](https://git-scm.com/docs/git-worktree)

**Sandbox execution:** OpenHands documents a Docker runtime for agent command and
file operations, including a hosted runtime service. A sandbox is an execution
boundary; it is a separate concern from tracking candidate ancestry or selecting
which scientific results should advance. [Official runtime description](https://runtime.all-hands.dev/)

**Experiment scheduling:** Ray Tune expresses resource requests per trial and a
separate `max_concurrent_trials` cap. Actual concurrency depends on available
resources; GPU assignment sets `CUDA_VISIBLE_DEVICES`. Its docs explicitly warn
that resource requests are scheduling allocations, not automatically enforced
limits on the objective function. Trial directories must be unique, and recovery
can use recorded checkpoints. This is relevant infrastructure rather than a
scientific reasoning policy. [Resources](https://docs.ray.io/en/latest/tune/tutorials/tune-resources.html),
[Trial execution and recovery](https://docs.ray.io/en/latest/tune/api/doc/ray.tune.run.html)

**Cluster batches:** Slurm job arrays group similar jobs and can bound concurrent
tasks using `%`, for example `--array=0-5%2` for six tasks with at most two running.
Array tasks have their own identities; dependencies can wait for all tasks or
corresponding tasks. This is a natural option for fixed seed/parameter batches.
It does not replace recording each scientific attempt and its actual result.
[Slurm arrays](https://slurm.schedmd.com/job_array.html)

## Proposed application to Metis (recommendation, not implemented behavior)

Maintain three distinct identities:

- **Study:** one research question/paper, fixed evaluation protocol and budget.
- **Candidate revision:** one proposed implementation with recorded parentage.
  Parallel editing gets a private worktree or snapshot; publication of a revision
  freezes the experiment input. Worktrees fit an existing Git project, while
  current snapshots already handle non-Git inputs and preserve source isolation.
- **Execution attempt:** one candidate revision plus dataset/split, seed, parameters
  and environment identity. Each attempt has its own writable artifact directory,
  job identity, resource request and durable status, independent of editing.

For example, two candidate revisions tested with three seeds produce six jobs.
They need two candidate code histories and six result directories, not six separate
editable Git branches. With two available GPUs and one GPU per job, the dispatcher
can run two jobs while four wait. A retry creates a separately recorded attempt.
A running job must not read source being changed by a coding agent.

Use separate limits for coding agents and experiment jobs. On a shared controller,
resource admission must span its runs; on a cluster, rely on scheduler allocations.
Keep datasets/dependency images reusable and read-only where possible. Keep
checkpoints/results out of source branches. Allow asynchronous job completion, but
compare candidates only after the required evidence is complete or explicitly
failed/unresolved. Combining competing implementations creates a new candidate
requiring fresh evaluation; it is not merely a software merge.

The first useful Metis increment is bounded parallel seed repeats or fixed ablation
plans through its existing executors, with persisted per-attempt state, cancellation,
reconciliation after interruption and resource ownership. Candidate search can then
expand concurrently while preserving scientific stage dependencies. Adopting Ray
is optional; the current Slurm backend already reaches a scheduler. Git worktrees
are a code-management option, not a prerequisite for experiment parallelism.

Current behavior and limitations remain in [execution options](execution-options.md).
No scheduler or scientific policy was changed by this research note. No upstream
code was executed and no performance or research-quality equivalence is claimed.

## Retrieval limits

The current Ray checkpoint-guide URL and two attempted OpenHands documentation
routes were unavailable through the browser tool. The Ray execution API and
OpenHands official runtime page supported the narrower claims retained above.
