"use strict";

// Research text is always rendered through textContent, never interpreted as HTML.
const $ = (selector) => document.querySelector(selector);
const state = {
  page: "research", theme: "charcoal", setupSection: "project", token: "", stages: [], runs: [], id: null, detail: null, events: [], behavior: null, behaviorKey: "",
  tab: "overview", reportId: null, reportRevision: "", reportDetailKey: "", ideaId: null, experimentId: null, eventId: null,
  eventFilter: "", revision: "", refreshing: false, historyRemaining: false,
  setupOpening: 0, modelScope: null, modelScopeRequest: 0, modelDrafts: new Map(),
  serverConfig: null, setupBase: null, setupRevision: 0, settingsRevision: 0, settingsMode: false,
  proposal: null, proposalPrepared: null, onboardingBusy: false,
  validatedKey: null, jsonDirty: false, setupBusy: false, connectionError: false,
  managedRemote: false, remoteLabel: "localhost", remoteProfiles: [], remoteName: "",
  remoteBusy: false, remoteDirty: false, remoteAuth: null, authBusy: false,
  connectionProfiles: [], connectionHosts: [], connectionKey: "local", connectionBusy: false,
  connectionNotice: "", connectionDashboards: new Map(), connectionPendingAuth: "",
};
let processView = null;
let processData = null;
let labels = {};
let phases = [];
function applyWorkflow(workflow) {
  labels = {};
  const grouped = new Map();
  for (const [stage, node] of Object.entries(workflow?.nodes || {})) {
    labels[stage] = node.label;
    if (!grouped.has(node.phase)) grouped.set(node.phase, []);
    grouped.get(node.phase).push(stage);
  }
  phases = [...grouped.entries()];
}
const clone = (value) => JSON.parse(JSON.stringify(value));
const json = (value) => JSON.stringify(value, null, 2);
const human = (value) => String(value ?? "").replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
const stageName = (value) => labels[value] || human(value);
const number = (value) => Number(value || 0).toLocaleString();
const money = (value) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: Number(value) > 0 && Number(value) < 0.01 ? 4 : 2 }).format(Number(value || 0));
const timestamp = (value) => { const date = new Date(value); return value && !Number.isNaN(date.getTime()) ? date.toLocaleString() : "Not recorded"; };
const shortTime = (value) => { const date = new Date(value); return value && !Number.isNaN(date.getTime()) ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : ""; };

function element(tag, className = "", text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function empty(text) { return element("p", "empty-message", text); }
function badge(text) { return element("span", `badge ${String(text).replace(/[^a-z_]/g, "")}`, human(text)); }
function showError(selector, message) {
  $(selector).textContent = message || "";
  $(selector).hidden = !message;
}
let toastTimer;
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 6500);
}
async function api(path, body) {
  const headers = { Authorization: `Bearer ${state.token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST", headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin", cache: "no-store",
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || `Request failed (${response.status})`);
    error.readiness = data.readiness;
    throw error;
  }
  return data;
}
function values(entries) {
  const list = element("dl", "key-values");
  for (const [name, value] of entries) {
    list.append(element("dt", "", name), element("dd", "", value === undefined || value === null || value === "" ? "Not configured" : value));
  }
  return list;
}
function rawDetails(title, value) {
  const details = element("details", "raw-details");
  details.append(element("summary", "", title), element("pre", "", typeof value === "string" ? value : json(value)));
  return details;
}
function textSection(root, title, text) {
  if (!text) return;
  root.append(element("h3", "", title), element("p", "", text));
}
function metricsTable(metrics) {
  const table = element("table", "metric-table");
  const body = element("tbody");
  for (const [metric, value] of Object.entries(metrics || {})) {
    const row = element("tr");
    row.append(element("th", "", metric), element("td", "", typeof value === "number" ? String(value) : value));
    body.append(row);
  }
  table.append(body);
  return table;
}
function navigate(tab) {
  state.tab = tab;
  $("#inspect-view").value = ["ideas", "system", "config", "fidelity"].includes(tab) ? tab : "";
  for (const button of document.querySelectorAll(".tab")) {
    const selected = button.dataset.tab === tab;
    button.classList.toggle("active", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  for (const view of document.querySelectorAll(".tab-view")) view.hidden = view.id !== `view-${tab}`;
}

function renderRuns() {
  $("#run-count").textContent = state.runs.length;
  const root = $("#run-list");
  root.replaceChildren();
  for (const run of state.runs) {
    const button = element("button", `run-item${run.id === state.id ? " active" : ""}`);
    button.append(element("strong", "", run.title), element("small", "", `${human(run.status)} · ${stageName(run.stage)}`));
    if (run.id === state.id) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => selectRun(run.id));
    root.append(button);
  }
  if (!state.runs.length) root.append(empty("No runs saved."));
}
async function selectRun(id) {
  state.page = "research";
  $("#settings-page").hidden = true;
  state.id = id;
  state.events = [];
  state.eventId = null;
  state.ideaId = null;
  state.experimentId = null;
  state.eventFilter = "";
  state.detail = null;
  state.behavior = null;
  state.behaviorKey = "";
  applyWorkflow({});
  state.revision = "";
  $("#event-filter").value = "";
  navigate("overview");
  renderRuns();
  try { await refreshDetail(); }
  catch (error) { showError("#global-error", error.message); }
}
async function refreshDetail() {
  const id = state.id;
  if (!id) return;
  const after = state.events.at(-1)?.seq || 0;
  const [detail, history, execution] = await Promise.all([
    api(`/api/runs/${encodeURIComponent(id)}`),
    api(`/api/runs/${encodeURIComponent(id)}/events?after=${after}`),
    typeof ResearchProcess === "undefined" ? null : api(`/api/runs/${encodeURIComponent(id)}/process`).catch(error => ({error: error.message})),
  ]);
  if (state.id !== id) return;
  state.detail = detail;
  processData = execution;
  const behaviorKey = `${id}:${detail.run?.behavior?.bundle_sha256 || "legacy"}`;
  if (!state.behavior || state.behaviorKey !== behaviorKey) {
    try {
      const behavior = await api(`/api/runs/${encodeURIComponent(id)}/behavior`);
      if (state.id !== id) return;
      state.behavior = behavior;
      state.behaviorKey = behaviorKey;
    } catch (error) {
      if (state.id !== id) return;
      state.behavior = {status: "unavailable", error: error.message, agents: {}, workflow: {}};
      state.behaviorKey = ""; // Retry after the operator restores the recorded artifact.
    }
    applyWorkflow(state.behavior.workflow);
  }
  const seen = new Set(state.events.map((event) => event.seq));
  state.events.push(...history.events.filter((event) => !seen.has(event.seq)));
  state.historyRemaining = history.events.length >= 2000;
  $("#load-history").hidden = !state.historyRemaining;
  if (typeof ResearchProcess !== "undefined") {
    if (!processView) processView = new ResearchProcess.View($("#research-process"), $("#agent-traces"), navigate);
    processView.update(processData, state.behavior.workflow, detail);
  }
  const revision = json([detail, state.events.length, state.behavior]);
  if (revision !== state.revision) {
    state.revision = revision;
    renderDetail();
  }
}
async function refresh() {
  if (state.refreshing) return;
  state.refreshing = true;
  try {
    state.runs = (await api("/api/runs")).runs;
    renderRuns();
    if (!state.id && state.runs.length && state.page !== "settings") await selectRun(state.runs[0].id);
    else if (state.id) await refreshDetail();
    else { $("#empty-workspace").hidden = state.page === "settings"; $("#research").hidden = true; }
    if (state.connectionError) showError("#global-error", "");
    state.connectionError = false;
    $("#connection-label").textContent = `Connected to ${state.remoteLabel}`;
    $("#connection-dot").style.background = "var(--good)";
  } catch (error) {
    state.connectionError = true;
    $("#connection-label").textContent = "Connection interrupted";
    $("#connection-dot").style.background = "var(--bad)";
    showError("#global-error", `${error.message}. If the server restarted, reload this page to renew the session.`);
  } finally { state.refreshing = false; }
}
function renderRunProblem(message) {
  const root = $("#run-alert");
  root.replaceChildren();
  const {run, working} = state.detail;
  const code = /Provider[^\n]*HTTP (\d{3})/.exec(message)?.[1];
  let title = "Research needs attention";
  let guidance = "Inspect the recorded error and Activity & traces before resuming.";
  if (code === "429") {
    title = "Model access blocked: rate limit or quota";
    guidance = "Check the API project's request and token limits, quota, and billing status. A temporary rate limit may clear after waiting; exhausted quota may need a reset or an account change. The saved error does not identify which limit was reached. Increasing the Metis run budget does not raise provider limits.";
  } else if (code && Number(code) >= 500) {
    title = "Model service unavailable";
    guidance = "The provider returned a server error. Wait and check its service status before trying again. This error alone does not mean your API key or billing is wrong.";
  } else if (code === "401" || code === "403") {
    title = "Model access denied";
    guidance = "Check the API credential, project permissions and access to the configured model. Settings changes apply to future runs; this run keeps its saved model configuration.";
  }
  root.append(element("h3", "", working ? "Retry in progress · previous error" : title));
  if (code) {
    // Use recorded activity, never guess a failed model from today's settings.
    const failure = state.events.findLastIndex(event => event.kind === "stage_error" && event.stage === run.stage && event.payload?.error === message);
    const started = failure < 0 ? null : state.events.slice(0, failure).findLast(event => event.kind === "agent_started" && event.stage === run.stage);
    if (started?.payload?.model) root.append(element("p", "", `Last recorded model attempt: ${started.payload.model}`));
    root.append(element("p", "", guidance));
    if (code === "429") {
      const link = element("a", "", "Gemini API limits and quota guidance");
      // Only offer Gemini-specific help when the recorded model identifies Gemini.
      if (/^gemini[-.]/i.test(started?.payload?.model || "")) {
        link.href = "https://ai.google.dev/gemini-api/docs/rate-limits";
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        root.append(link);
      }
    }
  } else root.append(element("p", "", guidance));
  root.append(element("p", "", working
    ? "Research is running. This is the previous recorded error, not confirmation of a new failure."
    : `Last saved stage: ${stageName(run.stage)}. No automatic retry is running. After resolving the cause, choose Resume research to continue from saved progress. New attempts may use the remaining run budget.`));
  const details = element("details", "raw-details");
  details.append(element("summary", "", "Technical details"), element("pre", "", message));
  root.append(details);
}
function modelProgressMessage() {
  const active = new Map();
  for (const event of state.events) {
    const p = event.payload || {};
    if (event.stage !== state.detail.run.stage || !p.call_id) continue;
    if (event.kind === "agent_progress") active.set(p.call_id, event);
    if (event.kind === "agent_completed" || event.kind === "agent_provider_failed") active.delete(p.call_id);
  }
  const latest = [...active.values()].findLast(event => ["waiting", "reasoning", "receiving"].includes(event.payload.status));
  if (!latest) return "";
  const p = latest.payload;
  const label = p.status === "reasoning" ? "Reasoning activity received" : p.status === "receiving" ? "Receiving an answer" : "Waiting for the provider's response";
  return `${p.model}: ${label}. ${Number(p.answer_chars) || 0} answer characters received. Last update: ${timestamp(latest.timestamp)}. Partial output is not accepted research; inspect Activity & traces for saved progress.`;
}
function renderDetail() {
  const { run, config, usage, working, paused, worker_error: workerError } = state.detail;
  const demo = config.mode === "demo";
  $("#empty-workspace").hidden = state.page !== "home";
  $("#research").hidden = state.page !== "research";
  $("#run-mode").textContent = demo ? "OFFLINE DEMO · SCRIPTED AGENTS / SYNTHETIC DATA" : "LIVE RESEARCH";
  $("#run-title").textContent = run.title;
  $("#run-objective").textContent = run.objective;
  $("#run-id").textContent = `Run ${run.id}`;
  $("#updated-at").textContent = `Last checkpoint: ${timestamp(run.updated_at)}`;
  const status = working ? (paused ? "pausing" : "running") : (paused ? "paused" : run.status);
  $("#run-status").className = `badge ${status}`;
  $("#run-status").textContent = human(status);
  const readiness = state.detail.readiness;
  const cannotStart = run.stage === "complete" || (!demo && readiness && !readiness.ready);
  $("#execute").hidden = working;
  $("#step").hidden = working;
  $("#execute").disabled = !!cannotStart;
  $("#step").disabled = !!cannotStart;
  $("#execute").textContent = run.version > 0 ? "Resume research" : "Start research";
  $("#pause").hidden = !working;
  $("#pause").disabled = !!paused;
  $("#intervene").disabled = working;
  $("#intervene").textContent = run.stage === "intake" ? "Answer research question" : "Add intervention";
  $("#edit-budget").disabled = working;
  $("#cancel-experiment").hidden = !run.pending_job_id;
  $("#cancel-experiment").disabled = working;
  let message = workerError || run.error || "";
  if (!message && run.pending_job_id) message = `Slurm job ${run.pending_job_id} is pending.${working ? " Monitoring scheduler status." : " Resume to monitor it, or cancel the pending experiment."}`;
  if (!message && run.stage === "complete" && run.outcome) message = human(run.outcome);
  if (!message && working) message = modelProgressMessage();
  if (!message && working) {
    const switched = state.events.findLast(event => event.kind === "provider_fallback" && event.stage === run.stage);
    if (switched) message = `Model fallback recorded: ${switched.payload.from_model} → ${switched.payload.to_model}. Attempts share this run's budget. See Activity & traces for the outcome.`;
  }
  if (!message && demo) message = "Demonstration results are synthetic. Scripted review scores and decisions are not independent scientific validation.";
  if (workerError || run.error) renderRunProblem(message);
  else $("#run-alert").textContent = message;
  $("#run-alert").hidden = !message;
  $("#run-alert").className = `notice ${workerError || run.error ? "error" : "info"}`;
  const readinessRoot = $("#readiness-summary");
  readinessRoot.replaceChildren();
  readinessRoot.hidden = demo || !readiness || readiness.ready;
  if (!readinessRoot.hidden) {
    const details = element("details", "readiness");
    details.open = true;
    details.append(element("summary", "", "Execution is blocked by setup checks"));
    appendChecks(details, readiness);
    readinessRoot.append(details);
  }
  $("#summary-stage").textContent = stageName(run.stage);
  $("#summary-checkpoint").textContent = `Round ${run.round || 0} · checkpoint ${run.version || 0}`;
  const experiments = run.experiments || [];
  const failures = experiments.filter((item) => ["failed", "timeout", "cancelled"].includes(item.status)).length;
  $("#summary-experiments").textContent = `${experiments.length} recorded`;
  $("#summary-failures").textContent = `${experiments.filter((item) => item.status === "completed").length} completed · ${failures} unsuccessful`;
  $("#summary-calls").textContent = `${number(usage.calls)} ${demo ? "scripted calls" : "model calls"}`;
  $("#summary-tokens").textContent = `${number(usage.input_tokens)} input / ${number(usage.output_tokens)} output tokens`;
  $("#summary-budget").textContent = `${money(usage.cost_usd)} / ${money(usage.budget_usd || config.budget.usd)}`;
  $("#summary-reserved").textContent = `${money(usage.reserved_usd)} reserved for in-flight calls`;
  $("#idea-count").textContent = run.ideas?.length || 0;
  $("#experiment-count").textContent = experiments.length;
  renderOverview();
  renderIdeas();
  renderExperiments();
  renderEvents();
  renderStageReports();
  renderManuscript();
  renderConfig();
  renderFidelity();
  renderSystem();
}
function renderOverview() {
  const { run, working } = state.detail;
  const current = $("#current-work");
  current.replaceChildren(values([
    ["Stage", stageName(run.stage)], ["Current idea", run.current_idea || "None"],
    ["Selected candidate", run.selected_idea || "None"],
    ["Queued candidates", run.queue?.length || 0],
  ]));
  const active = new Map();
  for (const event of state.events) {
    const key = `${event.stage}:${event.payload?.role}:${event.payload?.agent}`;
    if (event.kind === "agent_started") active.set(key, event);
    else if (["agent_completed", "agent_provider_failed"].includes(event.kind)) active.delete(key);
  }
  const running = [...active.values()].filter((event) => event.stage === run.stage);
  if (working && running.length) {
    current.append(element("h3", "", "Active agent calls"));
    for (const event of running) {
      const button = element("button", "activity-row");
      button.append(element("span", "", `${human(event.payload.role)} · agent ${event.payload.agent + 1} · ${event.payload.model}`));
      button.addEventListener("click", () => openEvent(event));
      current.append(button);
    }
  } else current.append(element("p", "", working ? "The worker is executing this stage. Agent and experiment events appear below as they are recorded." : run.stage === "complete" ? "This run has finished. Inspect its evidence, manuscript, and recorded reviews." : (run.error || state.detail.worker_error || run.status === "blocked") ? "Research needs attention. Read the problem and recovery guidance above before resuming." : "The run is stopped. Start it or execute one checkpoint using the controls above."));
  if (run.stage === "intake" && run.feedback) {
    current.append(element("h3", "", "A question before continuing"), element("p", "", run.feedback), element("p", "muted", "Save your answer with Answer research question, then choose Resume. Saving does not make model calls."));
  }
  if (run.research_brief && Object.keys(run.research_brief).length) current.append(rawDetails("Research brief and sources", run.research_brief));
  if (run.research_protocol && Object.keys(run.research_protocol).length) current.append(rawDetails("Established measurement protocol", run.research_protocol));
  const activity = $("#recent-activity");
  activity.replaceChildren();
  for (const event of state.events.slice(-8).reverse()) activity.append(activityButton(event));
  if (!state.events.length) activity.append(empty("No events recorded."));
  const memory = $("#research-memory");
  memory.replaceChildren();
  if (run.limitations?.length) {
    const list = element("ul", "plain-list");
    for (const limitation of run.limitations) list.append(element("li", "", limitation));
    memory.append(list);
  } else memory.append(element("p", "", "No limitations have been recorded at this checkpoint."));
  if (run.feedback) { memory.append(element("h3", "", "Latest feedback"), element("p", "", run.feedback)); }
  if (run.memory?.length) {
    const details = element("details", "raw-details");
    details.append(element("summary", "", `${run.memory.length} research observations`));
    for (const observation of run.memory) {
      const item = element("div", "review-card");
      item.append(element("h3", "", `${human(observation.kind)}${observation.stage ? ` · ${stageName(observation.stage)}` : ""}`));
      for (const key of ["note", "feedback", "reason", "failure"]) if (observation[key]) item.append(element("p", "", observation[key]));
      if (observation.metrics) item.append(metricsTable(observation.metrics));
      if (observation.id || observation.status) item.append(element("p", "muted", [observation.id, observation.status].filter(Boolean).join(" · ")));
      details.append(item);
    }
    memory.append(details);
  }
  const pipeline = $("#pipeline");
  pipeline.replaceChildren();
  if (!phases.length) pipeline.append(empty("The original workflow graph is unavailable for this run. Inspect its recorded stage and events."));
  for (const [name, stages] of phases) {
    const group = element("section", "phase");
    group.append(element("h3", "", name));
    for (const stage of stages) {
      const visits = state.events.filter((event) => event.kind === "transition" && (event.payload?.from || event.stage) === stage).length;
      const currentStage = stage === run.stage;
      const button = element("button", `stage-row${currentStage ? " current" : visits ? " visited" : ""}`);
      button.append(element("span", "", stageName(stage)), element("small", "", currentStage ? "CURRENT" : visits ? `${visits} visit${visits === 1 ? "" : "s"}` : "Not visited"));
      button.addEventListener("click", () => { state.eventFilter = stage; $("#event-filter").value = stage; state.eventId = null; navigate("activity"); renderEvents(); });
      group.append(button);
    }
    pipeline.append(group);
  }
}
function activityButton(event) {
  const button = element("button", "activity-row");
  const text = element("span", "", human(event.kind));
  text.append(element("small", "", `${stageName(event.stage)}${event.payload?.role ? ` · ${human(event.payload.role)}` : ""}`));
  button.append(text, element("time", "", shortTime(event.timestamp)));
  button.addEventListener("click", () => openEvent(event));
  return button;
}
function openEvent(event) {
  state.eventId = event.seq;
  state.eventFilter = "";
  $("#event-filter").value = "";
  navigate("activity");
  renderEvents();
}
function renderIdeas() {
  const ideas = state.detail.run.ideas || [];
  const list = $("#idea-list");
  const detail = $("#idea-detail");
  list.replaceChildren();
  detail.replaceChildren();
  if (!ideas.length) { list.append(empty("No hypotheses generated yet.")); detail.append(empty(`Current checkpoint: ${stageName(state.detail.run.stage)}.`)); return; }
  if (!ideas.some((idea) => idea.id === state.ideaId)) state.ideaId = state.detail.run.selected_idea || ideas[0].id;
  for (const idea of ideas) {
    const button = element("button", `item-button${idea.id === state.ideaId ? " active" : ""}`);
    button.append(element("strong", "", idea.title), element("small", "", `${idea.id} · round ${idea.round}`), badge(idea.status));
    if (idea.id === state.detail.run.selected_idea) button.append(element("small", "", "Selected candidate"));
    button.addEventListener("click", () => { state.ideaId = idea.id; renderIdeas(); });
    list.append(button);
  }
  const idea = ideas.find((item) => item.id === state.ideaId);
  detail.append(element("h2", "", idea.title), badge(idea.status));
  textSection(detail, "Hypothesis", idea.hypothesis);
  textSection(detail, "Rationale", idea.rationale);
  detail.append(values([["Idea ID", idea.id], ["Generation round", idea.round], ["Novelty score", idea.novelty ? `${idea.novelty} / 10` : "Not scored"], ["Workspace", idea.workspace || "No implementation workspace"]]));
  detail.append(element("h3", "", "Parent ideas"));
  if (!idea.parents?.length) detail.append(element("p", "", "Seed hypothesis; no parent ideas."));
  for (const parentId of idea.parents || []) {
    const parent = ideas.find((item) => item.id === parentId);
    if (!parent) { detail.append(element("p", "", parentId)); continue; }
    const button = element("button", "text-button", `${parent.title} (${parentId})`);
    button.addEventListener("click", () => { state.ideaId = parentId; renderIdeas(); });
    detail.append(button);
  }
  if (Object.keys(idea.metrics || {}).length) { detail.append(element("h3", "", "Recorded metrics"), metricsTable(idea.metrics)); }
  detail.append(element("h3", "", "Evidence"));
  if (!idea.evidence?.length) detail.append(element("p", "", "No evidence IDs attached to this idea."));
  for (const id of idea.evidence || []) {
    const reference = state.detail.run.evidence?.find((item) => item.id === id);
    detail.append(element("p", "", reference ? `${id}: ${reference.title}` : id));
    if (reference?.excerpt) detail.append(element("p", "", reference.excerpt));
    if (reference?.url && /^https?:\/\//i.test(reference.url)) {
      const link = element("a", "text-button", "Open source"); link.href = reference.url; link.target = "_blank"; link.rel = "noopener noreferrer"; detail.append(link);
    }
  }
}
function renderExperiments() {
  const experiments = state.detail.run.experiments || [];
  const list = $("#experiment-list");
  const detail = $("#experiment-detail");
  list.replaceChildren();
  detail.replaceChildren();
  if (!experiments.length) { list.append(empty("No experiments have executed.")); detail.append(empty("Experiment commands, measured results, and failures will be recorded when execution reaches baseline reproduction.")); return; }
  if (!experiments.some((item) => item.id === state.experimentId)) state.experimentId = experiments.at(-1).id;
  for (const experiment of [...experiments].reverse()) {
    const button = element("button", `item-button${experiment.id === state.experimentId ? " active" : ""}`);
    button.append(element("strong", "", experiment.id), element("small", "", `${human(experiment.provenance?.kind || "experiment")} · seed ${experiment.provenance?.seed ?? "not recorded"}`), badge(experiment.status));
    button.addEventListener("click", () => { state.experimentId = experiment.id; renderExperiments(); });
    list.append(button);
  }
  const experiment = experiments.find((item) => item.id === state.experimentId);
  detail.append(element("h2", "", experiment.id), badge(experiment.status));
  detail.append(values([["Duration", `${Number(experiment.duration_seconds || 0).toFixed(2)} seconds`], ["Exit code", experiment.exit_code ?? "Not recorded"], ["Scheduler job", experiment.job_id || "Not applicable"], ["Backend", experiment.provenance?.backend], ["Workspace", experiment.provenance?.workspace]]));
  if (Object.keys(experiment.metrics || {}).length) detail.append(element("h3", "", "Measured results"), metricsTable(experiment.metrics));
  else detail.append(element("p", "", "No metrics were produced for this execution."));
  if (experiment.provenance?.argv) detail.append(element("h3", "", "Executed command arguments"), element("pre", "", json(experiment.provenance.argv)));
  for (const [title, content] of [["Standard output", experiment.stdout], ["Standard error", experiment.stderr]]) {
    detail.append(element("h3", "", title), content ? element("pre", "", content) : element("p", "muted", "No output recorded."));
  }
  detail.append(rawDetails("Complete execution provenance", experiment.provenance || {}));
}
function renderStageReports() {
  const reports = state.detail.stage_reports || [];
  const revision = `${state.id}:${reports.at(-1)?.seq || 0}:${state.reportId}`;
  if (revision === state.reportRevision) return; // Keep selection, scroll and focus during polling.
  const list = $("#report-list"), detail = $("#report-detail");
  const focused = document.activeElement;
  const focusReport = focused?.dataset?.reportId;
  const scroll = list.scrollTop;
  list.replaceChildren();
  if (!reports.length) {
    detail.replaceChildren();
    state.reportDetailKey = "";
    list.append(empty("No stage reports recorded yet."));
    detail.append(empty("Reports appear after an attempted stage checkpoint. For earlier runs, inspect Activity & traces."));
    state.reportRevision = revision;
    return;
  }
  if (!reports.some(report => report.seq === state.reportId)) state.reportId = reports.at(-1).seq;
  for (const report of [...reports].reverse()) {
    const data = report.payload;
    const button = element("button", `item-button${report.seq === state.reportId ? " active" : ""}`);
    button.dataset.reportId = String(report.seq);
    button.setAttribute("aria-pressed", String(report.seq === state.reportId));
    button.append(element("strong", "", stageName(data.stage)), element("small", "", `Checkpoint ${data.checkpoint} · ${timestamp(report.timestamp)}`), badge(data.status));
    button.addEventListener("click", () => { state.reportId = report.seq; state.reportRevision = ""; renderStageReports(); });
    list.append(button);
    if (focusReport === String(report.seq)) button.focus();
  }
  list.scrollTop = scroll;
  state.reportRevision = `${state.id}:${reports.at(-1)?.seq || 0}:${state.reportId}`;
  const detailKey = `${state.id}:${state.reportId}`;
  if (state.reportDetailKey === detailKey) return;
  state.reportDetailKey = detailKey;
  detail.replaceChildren();
  const report = reports.find(item => item.seq === state.reportId), data = report.payload;
  const toolbar = element("div", "view-toolbar");
  const download = element("button", "button secondary", "Download Markdown");
  download.disabled = true;
  toolbar.append(download);
  const reading = element("div", "report-prose");
  reading.append(empty("Loading report…"));
  detail.append(toolbar, reading, rawDetails("Original report record", report));
  loadReportDocument(report, detailKey, reading, download);
}

async function loadReportDocument(report, key, reading, download) {
  const runId = state.id;
  try {
    const reportDoc = await api(`/api/runs/${encodeURIComponent(runId)}/reports/${report.seq}`);
    if (state.id !== runId || state.reportDetailKey !== key) return;
    reading.replaceChildren(markdownNodes(reportDoc.tokens));
    download.disabled = false;
    download.addEventListener("click", () => {
      const url = URL.createObjectURL(new Blob([reportDoc.markdown], {type: "text/markdown;charset=utf-8"}));
      const link = element("a");
      link.href = url; link.download = `stage-report-${runId}-${report.payload.checkpoint}.md`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  } catch (error) {
    if (state.id !== runId || state.reportDetailKey !== key) return;
    const retry = element("button", "button secondary", "Retry report");
    retry.addEventListener("click", () => { reading.replaceChildren(empty("Loading report…")); loadReportDocument(report, key, reading, download); });
    reading.replaceChildren(element("p", "", `Could not format this report: ${error.message}. The original record remains available below.`), retry);
  }
}

function markdownNodes(tokens) {
  const root = element("div");
  const stack = [root];
  const allowed = new Set(["p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "strong", "em", "s", "table", "thead", "tbody", "tr", "th", "td", "hr"]);
  for (const token of tokens || []) {
    const parent = stack.at(-1);
    if (token.nesting === -1) { if (stack.length > 1) stack.pop(); continue; }
    if (token.type === "inline") { parent.append(...markdownNodes(token.children).children); continue; }
    if (token.type === "fence" || token.type === "code_block") {
      const pre = element("pre"); pre.append(element("code", "", token.content)); parent.append(pre); continue;
    }
    if (token.type === "code_inline") { parent.append(element("code", "", token.content)); continue; }
    if (["softbreak", "hardbreak"].includes(token.type)) { parent.append(element("br")); continue; }
    if (token.type === "image") { parent.append(element("span", "", `[Image: ${token.content}]`)); continue; }
    if (token.type === "text") { parent.append(element("span", "", token.content)); continue; }
    let node;
    if (token.type === "link_open") {
      const href = token.attrs?.href || "";
      node = element(/^https?:\/\//i.test(href) ? "a" : "span");
      if (/^https?:\/\//i.test(href)) { node.href = href; node.target = "_blank"; node.rel = "noopener noreferrer"; }
    } else node = element(allowed.has(token.tag) ? token.tag : "span");
    if (token.tag === "ol" && /^\d+$/.test(String(token.attrs?.start || ""))) node.setAttribute("start", token.attrs.start);
    parent.append(node);
    if (token.nesting === 1) stack.push(node);
  }
  return root;

}

function renderEvents() {
  const list = $("#event-list");
  const detail = $("#event-detail");
  const scroll = list.scrollTop;
  list.replaceChildren();
  detail.replaceChildren();
  const events = state.events.filter((event) => !state.eventFilter || event.stage === state.eventFilter || event.payload?.from === state.eventFilter);
  $("#event-count").textContent = `${events.length} shown / ${state.events.length} loaded${state.historyRemaining ? " · more history available" : ""}`;
  if (!events.length) { list.append(empty("No recorded events match this stage.")); detail.append(empty("Select another stage or return to All stages.")); return; }
  if (!events.some((event) => event.seq === state.eventId)) state.eventId = events.at(-1).seq;
  for (const event of [...events].reverse()) {
    const button = element("button", `item-button${event.seq === state.eventId ? " active" : ""}`);
    button.append(element("strong", "", human(event.kind)), element("small", "", `${stageName(event.stage)} · ${shortTime(event.timestamp)}`));
    if (event.payload?.role) button.append(element("small", "", `${human(event.payload.role)} · agent ${(event.payload.agent ?? 0) + 1}`));
    button.addEventListener("click", () => { state.eventId = event.seq; renderEvents(); });
    list.append(button);
  }
  list.scrollTop = scroll;
  const event = events.find((item) => item.seq === state.eventId);
  const payload = event.payload || {};
  detail.append(element("h2", "", human(event.kind)), values([["Event", event.seq], ["Recorded", timestamp(event.timestamp)], ["Stage", stageName(event.stage)]]));
  const metadata = ["role", "agent", "model", "decision", "reason", "error", "status", "from", "to", "selected_id"].filter((key) => payload[key] !== undefined).map((key) => [human(key), typeof payload[key] === "object" ? json(payload[key]) : human(payload[key])]);
  if (metadata.length) detail.append(values(metadata));
  if (payload.prompt) detail.append(element("h3", "", "Agent prompt"), element("pre", "", payload.prompt));
  if (payload.system) detail.append(rawDetails("System instructions", payload.system));
  if (payload.output) {
    const output = payload.output;
    detail.append(element("h3", "", "Agent result"));
    if (typeof output === "string") detail.append(element("pre", "", output));
    else {
      for (const key of ["summary", "feedback", "manuscript"]) if (output[key]) detail.append(element("p", "", output[key]));
      if (output.decision) detail.append(badge(output.decision));
      if (output.concerns?.length) {
        const concerns = element("ul", "plain-list");
        for (const concern of output.concerns) concerns.append(element("li", "", concern));
        detail.append(concerns);
      }
      detail.append(rawDetails("Structured agent output", output));
    }
  }
  if (event.kind.startsWith("agent_") && !payload.prompt && !payload.output) detail.append(element("p", "muted", `This event contains metadata. Run trace privacy mode: ${state.detail.config.privacy.traces}.`));
  detail.append(rawDetails("Complete recorded event", event));
}
function renderManuscript() {
  const { run, artifacts } = state.detail;
  const manuscript = $("#manuscript");
  manuscript.replaceChildren();
  $("#manuscript-status").textContent = run.manuscript ? "Latest saved draft" : "Not drafted";
  if (!run.manuscript) manuscript.append(empty(`No manuscript exists at the ${stageName(run.stage)} checkpoint.`));
  else {
    for (const line of run.manuscript.split("\n")) {
      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      manuscript.append(heading ? element(`h${heading[1].length}`, "", heading[2]) : document.createTextNode(`${line}\n`));
    }
  }
  const reviews = $("#reviews");
  reviews.replaceChildren();
  if (!run.reviews?.length) reviews.append(empty("No peer or meta-reviews recorded."));
  for (const [index, review] of (run.reviews || []).entries()) {
    const card = element("section", "review-card");
    card.append(element("h3", "", `${human(review.stage || review.role || "Review")} ${index + 1}`));
    for (const key of ["summary", "feedback"]) if (review[key]) card.append(element("p", "", review[key]));
    if (review.score !== undefined) card.append(element("p", "", `Model-assigned review score: ${review.score} / 10`));
    if (review.concerns?.length) {
      const concerns = element("ul", "plain-list");
      for (const concern of review.concerns) concerns.append(element("li", "", concern));
      card.append(concerns);
    }
    card.append(rawDetails("Complete review record", review));
    reviews.append(card);
  }
  const files = $("#artifacts");
  files.replaceChildren();
  if (!artifacts?.length) files.append(empty("No artifact files saved."));
  for (const artifact of artifacts || []) {
    const row = element("div", "artifact-row");
    const label = element("div");
    label.append(element("strong", "", artifact.path), element("small", "", `${human(artifact.kind)} · ${number(artifact.size)} bytes`));
    label.title = `SHA-256: ${artifact.sha256}`;
    const download = element("button", "button secondary", "Download");
    download.addEventListener("click", () => downloadArtifact(artifact, download));
    row.append(label, download); files.append(row);
  }
}
async function downloadArtifact(artifact, button) {
  button.disabled = true;
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(state.id)}/artifacts/${encodeURIComponent(artifact.id)}`, { headers: { Authorization: `Bearer ${state.token}` }, credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error((await response.json()).error);
    const url = URL.createObjectURL(await response.blob());
    const link = element("a");
    link.href = url; link.download = artifact.path.split("/").at(-1);
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { showError("#global-error", error.message); }
  finally { button.disabled = false; }
}
function renderConfig() {
  const config = state.detail.config;
  const root = $("#config-summary");
  root.replaceChildren();
  const sections = [
    ["Model & routing", [["Mode", config.mode], ["Primary model", config.provider.model], ["API endpoint", config.provider.base_url], ["Credential variable", config.provider.api_key_env], ["Cheap model", config.cheap_provider?.model || "Not configured"], ["Frontier model", config.frontier_provider?.model || "Not configured"], ["Critics per decision", config.pipeline.critics], ["Agents per role", config.pipeline.agents_per_role]]],
    ["Project & evidence", [["Project folder", config.project.source_dir || "No project folder selected"], ["Baseline arguments", json(config.project.baseline_argv)], ["Evaluator arguments", json(config.project.evaluator_argv)], ["Protected paths", config.project.protected_paths.join(", ") || "None"], ["Primary metric", `${config.project.primary_metric} (${config.project.metrics[config.project.primary_metric]})`], ["Published SOTA", Object.entries(config.project.sota).map(([key, value]) => `${key}: ${value}`).join("; ") || "Not configured"], ["Seeds", config.project.seeds.join(", ")]]],
    ["Execution & persistence", [["Backend", config.execution.backend], ["Docker image", config.execution.backend === "docker" ? config.execution.docker_image : "Not applicable"], ["Slurm partition", config.execution.slurm_partition || "Cluster default"], ["Local code permitted", config.execution.allow_local ? "Yes" : "No"], ["Trace privacy", config.privacy.traces], ["Response cache", config.privacy.cache ? "Enabled" : "Disabled"]]],
    ["Limits", [["Maximum model cost", money(config.budget.usd)], ["Maximum model calls", number(config.budget.max_calls)], ["Maximum experiments", number(config.budget.max_experiments)], ["Maximum duration", `${number(config.budget.wall_seconds)} seconds`]]],
    ["Research backends", [["Writer", "Pinned official PaperOrchestra"], ["Writer runtime", config.paper_orchestra?.backend], ["Reviewer", `ScholarPeer Appendix G · ${config.scholarpeer?.venue || "ICLR"}`], ["Literature providers", (config.literature?.providers || []).join(", ")], ["Laya typed triage", config.laya?.enabled ? "Enabled (advisory)" : "Not enabled"], ["Held-out model", config.heldout_provider?.model || "Not configured"], ["Model calls incl. writer", state.detail.usage.model_calls_attempted]]],
  ];
  for (const [title, entries] of sections) {
    const section = element("section", "config-section");
    section.append(element("h3", "", title), values(entries)); root.append(section);
  }
  $("#configuration").textContent = json(config);
}

function renderSystem() {
  const root = $("#ai-system");
  root.replaceChildren();
  const info = state.behavior;
  if (!info) { root.append(empty("No AI specification recorded.")); return; }
  if (info.error) root.append(empty(`Recorded AI behavior is unavailable or untrusted: ${info.error}. The run journal remains inspectable.`));
  root.append(values([["Behavior bundle", info.identity?.bundle_sha256 || "Legacy run: provenance not pinned"], ["Workflow", info.workflow?.id], ["Workflow version", info.workflow?.version]]));
  if (Object.keys(info.extensions || {}).length || Object.keys(info.external_adapters || {}).length) {
    root.append(rawDetails("Configured adapter identities", {injected: info.extensions || {}, commands: info.external_adapters || {}}));
  }
  const graph = element("section", "config-section");
  graph.append(element("h3", "", "Workflow and feedback"));
  for (const [stage, node] of Object.entries(info.workflow?.nodes || {})) {
    const card = element("details", "raw-details");
    card.append(element("summary", "", `${node.label}: ${(node.transitions || []).map(edge => stageName(edge.target)).join(" → ") || "terminal"}`));
    card.append(values([["Agents", node.agents.join(", ")], ["Inputs", json(node.inputs)], ["Outputs", json(node.outputs)], ["Limits", json(node.limits)]]));
    card.append(rawDetails("Transition conditions and evidence gates", node.transitions));
    graph.append(card);
  }
  root.append(graph);
  for (const [role, agent] of Object.entries(info.agents || {})) {
    const card = element("section", "config-section");
    card.append(element("h3", "", `${human(role)} · ${agent.resolved_model}`));
    card.append(element("p", "", agent.purpose));
    card.append(values([["Provider / routing", `${agent.resolved_provider} / ${agent.routing_reason}`], ["Tools", agent.tools.join(", ") || "None"], ["Inputs", json(agent.inputs)], ["Output contract", agent.output_schema], ["Prompt version", agent.version], ["Prompt SHA-256", agent.prompt_sha256], ["Escalation", json(agent.escalation)]]));
    const instructionLabel = agent.prompt_scope === "upstream_native" ? "Local adapter/demo instructions (official writer prompts come from pinned upstream)" : "Resolved instructions";
    card.append(rawDetails(instructionLabel, info.prompts?.[role] || "Not recorded"), rawDetails("Agent definition", agent));
    root.append(card);
  }
}

function renderFidelity() {
  const root = $("#fidelity-matrix");
  if (!root) return;
  const matrix = state.detail.fidelity;
  root.replaceChildren();
  root.append(element("p", "panel-note", "Paper fidelity and tested scientific capability are separate. Live capability parity is unmeasured; the offline demo checks plumbing only."));
  for (const component of matrix?.components || []) {
    const section = element("section", "config-section");
    section.append(element("h3", "", `${human(component.component)} · ${component.status}`));
    section.append(values([["Category", human(component.category)], ["Published behavior", component.published_behavior], ["Implementation", component.implementation], ["Validation", component.test_evaluation.join(", ")], ["Remaining gap", component.remaining_gap]]));
    root.append(section);
  }
}

function appendChecks(root, readiness, editable = false) {
  for (const check of readiness.checks || []) {
    const row = element("div", `readiness-check ${check.status}`);
    const description = element("div");
    description.append(element("strong", "", human(check.name)), element("p", "", check.message));
    if (editable && check.status !== "ok") {
      const section = check.name.startsWith("provider") ? "model" : check.name === "source" ? "project" : ["baseline", "evaluator", "protected-evaluator", "metrics", "datasets", "protocol"].includes(check.name) ? "data" : /docker|execution|dependencies/.test(check.name) ? "execution" : "advanced";
      const fix = element("button", "text-button", `Edit ${section} →`);
      fix.type = "button";
      fix.addEventListener("click", () => { setSetupSection(section); if (section === "data") $("#onboarding-manual").open = true; });
      description.append(fix);
    }
    row.append(element("span", "check-status", check.status), description);
    root.append(row);
  }
}
function showReadiness(readiness, inspection = null, inspectionError = "", actions = []) {
  const root = $("#setup-readiness");
  root.hidden = false;
  root.replaceChildren(element("h3", "", readiness.ready ? "Ready to create an idle run" : "Before research begins"));
  root.append(element("p", "panel-note", "These checks do not run training, verify a model response or establish scientific validity. Start can make paid calls; one Step may contain multiple calls or an experiment."));
  for (const action of actions) root.append(element("p", "notice", action));
  if (!readiness.ready) {
    const steps = readiness.guidance || [];
    if (steps.length) {
      root.append(element("p", "", "Metis checks what it can locally. Work through these steps before creating a run:"));
      for (const step of steps) {
        const row = element("div", "setup-guidance-step");
        const heading = element("div", "setup-guidance-heading");
        heading.append(element("span", "setup-guidance-owner", step.owner === "metis" ? "Metis can help" : "Your input"), element("strong", "", step.title));
        row.append(heading, element("p", "", step.message));
        if (step.title === "Inspect the project" && inspection) {
          const baseline = inspection.candidates?.baseline || [];
          const evaluator = inspection.candidates?.evaluator || [];
          row.append(element("p", "setup-candidates", `Possible commands: ${baseline.length ? baseline.join(", ") : "no baseline file identified"}; evaluation: ${evaluator.length ? evaluator.join(", ") : "no evaluator file identified"}. File names are unverified.`));
        }
        if (step.title === "Inspect the project" && inspectionError) row.append(element("p", "notice", `Metis could not inspect this folder: ${inspectionError}. Use Inspect project to retry, or review the details manually.`));
        const label = step.title === "Inspect the project" && inspectionError ? "Retry project inspection →" : step.owner === "metis" ? "Review findings and AI preparation →" : `Open ${step.section} →`;
        const action = element("button", "text-button", label);
        action.type = "button";
        action.addEventListener("click", () => {
          setSetupSection(step.section);
          if (step.title === "Inspect the project" && inspectionError) return inspectProject().then(report => { if (report) showReadiness(readiness, report); });
          if (step.section === "project" && step.owner === "metis") { $("#onboarding-existing").open = true; $("#onboarding-ai-options").open = true; }
          if (step.section === "project" && step.owner === "you") $("#setup-source").focus();
          if (step.section === "advanced") { $("#advanced-setup").open = true; $("#setup-json").focus(); }
        });
        row.append(action);
        root.append(row);
      }
    }
  }
  const warnings = (readiness.checks || []).filter(check => check.status === "warning");
  const later = warnings.filter(check => ["paper-orchestra", "writer-pricing"].includes(check.name));
  const details = element("details", "raw-details");
  details.append(element("summary", "", "All setup diagnostics"));
  appendChecks(details, {checks: (readiness.checks || []).filter(check => check.status !== "ok" && !later.includes(check))}, true);
  root.append(details);
  if (later.length) {
    const deferred = element("details", "raw-details");
    deferred.append(element("summary", "", "Before manuscript writing · prerequisites still needed"));
    appendChecks(deferred, {checks: later}, true);
    root.append(deferred);
  }
  const passed = element("details", "raw-details");
  passed.append(element("summary", "", "Passed configuration checks"));
  appendChecks(passed, {checks: (readiness.checks || []).filter(check => check.status === "ok")});
  root.append(passed);
}

function formatCommand(argv) {
  return argv.map(arg => /^[a-zA-Z0-9_./:=,@%+-]+$/.test(arg) ? arg : "'" + arg.replaceAll("'", "'\\''") + "'").join(" ");
}
function parseCommand(text) {
  if (text.trim().startsWith("[")) {
    const result = JSON.parse(text);
    if (!Array.isArray(result) || result.some(arg => typeof arg !== "string" || !arg.length)) throw new Error("Command arguments must be nonempty strings.");
    return result;
  }
  const result = []; let word = "", quote = "", escaped = false, active = false;
  for (const char of text.trim()) {
    if (escaped) { word += char; escaped = false; active = true; continue; }
    if (char === "\\" && quote !== "'") { escaped = true; active = true; continue; }
    if (quote) { if (char === quote) quote = ""; else word += char; active = true; continue; }
    if (char === "'" || char === '"') { quote = char; active = true; continue; }
    if (/\s/.test(char)) { if (active) { result.push(word); word = ""; active = false; } continue; }
    if (/[|;&<>`$]/.test(char)) throw new Error("Shell operators and expansion are unsupported. Use a project script or quote a literal argument.");
    word += char; active = true;
  }
  if (quote || escaped) throw new Error("Close the command's quotes or complete the escaped character.");
  if (active) result.push(word);
  if (result.some(arg => !arg.length)) throw new Error("Command arguments must be nonempty strings.");
  return result;
}
function onboardingBusy(busy) {
  state.onboardingBusy = busy;
  for (const selector of ["#inspect-project", "#prepare-proposal", "#generate-proposal", "#apply-proposal", "#load-proposals"]) $(selector).disabled = busy;
}
function renderInspection(report, root) {
  root.replaceChildren(element("h3", "", "Project inspection")); root.hidden = false;
  root.append(values([["Folder on this server", report.source_dir], ["Files inventoried", report.files.length], ["Excerpts available to AI", report.documents.length]]));
  for (const warning of report.warnings) root.append(element("p", "notice", warning));
  for (const [role, paths] of Object.entries(report.candidates)) root.append(element("p", "", `${human(role)} candidates: ${paths.join(", ") || "none identified by filename"}`));
  const excerpts = element("details", "raw-details"); excerpts.append(element("summary", "", "Review the exact excerpts · known credentials redacted"));
  for (const doc of report.documents) excerpts.append(rawDetails(doc.path, doc.excerpt));
  root.append(excerpts);
}
function closeFolderPicker() {
  state.folderRequest = (state.folderRequest || 0) + 1;
  state.folderSelection = null;
  $("#project-folder-picker").hidden = true;
}
async function browseProjectFolders(path = "") {
  const request = state.folderRequest = (state.folderRequest || 0) + 1;
  const opening = state.setupOpening;
  state.folderSelection = null;
  $("#project-folder-picker").hidden = false;
  $("#project-folder-select").disabled = true;
  $("#project-folder-up").disabled = true;
  $("#project-folder-list").replaceChildren();
  $("#project-folder-note").textContent = "Loading folders…";
  try {
    const result = await api("/api/folders/browse", {path});
    if (request !== state.folderRequest || opening !== state.setupOpening) return;
    state.folderSelection = result;
    $("#project-folder-location").value = result.path;
    for (const folder of result.folders) {
      const button = element("button", "button secondary", folder.name);
      button.type = "button";
      button.addEventListener("click", () => browseProjectFolders(folder.path));
      $("#project-folder-list").append(button);
    }
    $("#project-folder-note").textContent = result.truncated ? "Some folders are omitted. Enter a more specific location to find them." : result.folders.length ? "Open a folder to explore it, or use the current location." : "No visible subfolders. You can use this folder.";
    $("#project-folder-select").disabled = false;
    $("#project-folder-up").disabled = result.path === result.parent;
    $("#project-folder-location").focus();
  } catch (error) {
    if (request !== state.folderRequest || opening !== state.setupOpening) return;
    $("#project-folder-note").textContent = error.message;
    $("#project-folder-location").focus();
  }
}
async function useProjectFolder(path) {
  $("#setup-source").value = path;
  invalidateSetup();
  closeFolderPicker();
  $("#project-folder-status").textContent = `Project folder: ${path}`;
  $("#setup-source").focus();
  await refreshProjectModels();
}
async function createProjectFolder() {
  if (state.folderCreating) return false;
  const opening = state.setupOpening;
  const source = $("#setup-source").value;
  state.folderCreating = true;
  $("#project-folder-create").disabled = true;
  $("#project-folder-status").textContent = "Creating a project folder…";
  try {
    const result = await api("/api/folders/create", {name: runTitle().slice(0, 200) || "research"});
    if (opening !== state.setupOpening) return false;
    if (source !== $("#setup-source").value) {
      $("#project-folder-status").textContent = `Created ${result.path}. Your newer folder selection was kept.`;
      return false;
    }
    await useProjectFolder(result.path);
    if (opening !== state.setupOpening) return false;
    $("#project-folder-status").textContent = `Created ${result.path}. Agents will develop the project after you start research.`;
    return true;
  } catch (error) {
    if (opening === state.setupOpening) { $("#project-folder-status").textContent = error.message; showError("#setup-error", error.message); }
    return false;
  } finally { state.folderCreating = false; $("#project-folder-create").disabled = false; }
}
$("#project-folder-browse").addEventListener("click", () => browseProjectFolders($("#setup-source").value.trim()));
$("#project-folder-go").addEventListener("click", () => browseProjectFolders($("#project-folder-location").value.trim()));
$("#project-folder-location").addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); browseProjectFolders(event.target.value.trim()); } });
$("#project-folder-up").addEventListener("click", () => { if (state.folderSelection) browseProjectFolders(state.folderSelection.parent); });
$("#project-folder-select").addEventListener("click", () => { if (state.folderSelection) useProjectFolder(state.folderSelection.path); });
$("#project-folder-cancel").addEventListener("click", () => { closeFolderPicker(); $("#project-folder-browse").focus(); });
$("#project-folder-create").addEventListener("click", createProjectFolder);

async function inspectProject() {
  $("#onboarding-existing").open = true;
  const revision = state.setupRevision; onboardingBusy(true); showError("#setup-error", "");
  $("#onboarding-status").textContent = "Reading project files; no commands or model calls…";
  try {
    const report = await api("/api/onboarding/inspect", {source_dir: $("#setup-source").value});
    if (revision !== state.setupRevision) throw new Error("Setup changed during inspection. Inspect the current folder again.");
    renderInspection(report, $("#onboarding-report"));
    $("#onboarding-ai-options").open = true;
    $("#onboarding-status").textContent = "Inspection complete. Review the excerpts before preparing an AI request.";
    return report;
  } catch (error) { showError("#setup-error", error.message); $("#onboarding-status").textContent = "Inspection did not complete."; return null; }
  finally { onboardingBusy(false); }
}
async function prepareProposal() {
  const revision = state.setupRevision; onboardingBusy(true); showError("#setup-error", "");
  state.proposalPrepared = null; $("#generate-proposal").hidden = true;
  try {
    const config = readSetup();
    const objective = $("#setup-objective").value || config.project.specification;
    const prepared = await api("/api/onboarding/prepare", {config, objective, maximum_usd: Number($("#onboarding-budget").value)});
    if (revision !== state.setupRevision) throw new Error("Setup changed while preparing. Preview again before sending.");
    state.proposalPrepared = {record: prepared, revision};
    $("#onboarding-report").hidden = true;
    renderInspection(prepared.inspection, $("#onboarding-preview"));
    $("#onboarding-preview").append(rawDetails("Exact outbound AI request · includes current project settings", prepared.request_preview));
    $("#onboarding-preview").append(values([["Model", prepared.model], ["Preparation spending limit", money(prepared.maximum_usd)], ["Research objective", prepared.objective]]));
    $("#generate-proposal").hidden = false;
    $("#onboarding-status").textContent = "No model call yet. Sending this preview authorizes one bounded AI preparation request. Excerpts may contain private research; review them above.";
  } catch (error) { showError("#setup-error", error.message); }
  finally { onboardingBusy(false); }
}
const proposalLabels = {
  "project.baseline_argv": "Run the reference method", "project.evaluator_argv": "Measure the results",
  "project.protected_paths": "Keep these evaluation files unchanged", "project.include": "Files to include in the research copy",
  "project.metrics": "Measurements and improvement direction", "project.primary_metric": "Main measurement",
  "project.sota": "Full-benchmark reference values", "project.baseline_expected": "Expected baseline results",
  "project.specification": "Research protocol", "project.dataset_manifest": "Dataset provenance",
  "project.seeds": "Random seeds", "project.experiment_timeout": "Experiment time limit (seconds)",
  "execution.backend": "Where experiments run", "execution.docker_image": "Experiment container",
  "execution.slurm_partition": "Cluster partition", "execution.slurm_account": "Cluster allocation account",
};
function suggestionValue(suggestion) {
  if (suggestion.field.endsWith("_argv") && Array.isArray(suggestion.value) && suggestion.value.every(arg => typeof arg === "string")) return formatCommand(suggestion.value);
  if (Array.isArray(suggestion.value)) return suggestion.value.every(value => typeof value === "string" || typeof value === "number") ? suggestion.value.join("\n") : json(suggestion.value);
  if (typeof suggestion.value === "string") return suggestion.value;
  if (suggestion.value && typeof suggestion.value === "object") return Object.entries(suggestion.value).map(([key,value]) => `${key}: ${value === "max" ? "higher is better" : value === "min" ? "lower is better" : value}`).join("\n");
  return String(suggestion.value);
}
function renderProposal(record) {
  state.proposal = record;
  $("#onboarding-preview").hidden = true; $("#onboarding-report").hidden = true;
  $("#onboarding-ai-options").open = false;
  const root = $("#onboarding-result"); root.hidden = false;
  root.replaceChildren(element("h3", "", "Your setup proposal"));
  root.append(values([["Preparation", record.id], ["Status", record.status], ["Model", record.model], ["Cost at configured rates", record.usage ? money(record.usage.cost_usd) + (record.usage.estimated ? " (estimated)" : "") : "Not settled"]]));
  $("#apply-proposal").hidden = record.status !== "complete";
  if (record.status !== "complete") {
    root.append(element("p", "notice", record.error || (record.status === "running" ? "The request is running or was interrupted. Its outcome is uncertain until a saved result is available; it will not be replayed automatically." : "Prepared only; no model call made.")));
    return;
  }
  const proposal = record.proposal;
  root.append(element("p", "", proposal.summary));
  root.append(element("p", "panel-note", "Suggestions are unverified. Select the settings you want to copy into the form. Applying them does not save settings, write files or start research."));
  proposal.suggestions.forEach((suggestion, index) => {
    const label = element("label", "proposal-choice");
    const checkbox = element("input"); checkbox.type = "checkbox"; checkbox.dataset.suggestion = String(index);
    const description = element("div");
    description.append(element("strong", "", proposalLabels[suggestion.field] || suggestion.field), element("pre", "", suggestionValue(suggestion)), element("p", "", suggestion.reason), element("small", "", `Evidence: ${suggestion.evidence.join(", ")}`));
    label.append(checkbox, description); root.append(label);
  });
  for (const [label, entries] of [["Questions to resolve", proposal.questions], ["Integration work still needed", proposal.blockers]]) {
    if (entries.length) { root.append(element("h4", "", label)); for (const entry of entries) root.append(element("p", "notice", entry)); }
  }
  if (proposal.drafts.length) root.append(element("h4", "", "Draft integration files · not installed or tested"));
  for (const draft of proposal.drafts) root.append(rawDetails(`${draft.path} — ${draft.purpose}`, draft.content));
  root.tabIndex = -1; root.focus();
  root.append(element("p", "panel-note", "Answer missing questions in the objective or project instructions and preview a new request if needed. Every preparation keeps its own receipt."));
}
async function generateProposal() {
  const prepared = state.proposalPrepared;
  if (!prepared || prepared.revision !== state.setupRevision) { showError("#setup-error", "Setup changed. Preview the current request before sending."); return; }
  onboardingBusy(true); $("#generate-proposal").hidden = true; state.proposalPrepared = null;
  $("#onboarding-status").textContent = "AI is preparing a proposal. This can take a few minutes; no research is running.";
  try {
    const result = await api("/api/onboarding/generate", {id: prepared.record.id});
    renderProposal(result);
    $("#onboarding-status").textContent = "Preparation recorded. Review its result below.";
  } catch (error) {
    showError("#setup-error", error.message);
    $("#onboarding-status").textContent = "The request may have reached the provider. Use Previous preparations to inspect its receipt before requesting another.";
  } finally { onboardingBusy(false); }
}
async function applyProposal() {
  if (!state.proposal) return;
  const revision = state.setupRevision;
  const selected = [...document.querySelectorAll("[data-suggestion]")].filter(node => node.checked).map(node => Number(node.dataset.suggestion));
  if (!selected.length) { showError("#setup-error", "Select at least one suggested setting to apply."); return; }
  onboardingBusy(true);
  try {
    const result = await api("/api/onboarding/apply", {id: state.proposal.id, config: readSetup(), selected});
    if (revision !== state.setupRevision) throw new Error("Setup changed while applying. Review the latest form before applying again.");
    populateSetup(result.config); setSetupSection("data"); $("#onboarding-manual").open = true;
    $("#onboarding-status").textContent = "Selected suggestions copied into the form. Review them, then check setup. Draft files remain uninstalled.";
  } catch (error) { showError("#setup-error", error.message); }
  finally { onboardingBusy(false); }
}
async function loadProposals() {
  onboardingBusy(true);
  try {
    const {proposals} = await api("/api/onboarding");
    const root = $("#onboarding-result"); root.hidden = false; root.replaceChildren(element("h3", "", "Previous preparations"));
    $("#apply-proposal").hidden = true;
    if (!proposals.length) root.append(empty("No saved preparations yet."));
    for (const record of proposals) {
      const button = element("button", "text-button", `${record.source_dir} · ${record.status} · ${record.usage ? money(record.usage.cost_usd) : "not settled"}`); button.type = "button";
      button.addEventListener("click", () => renderProposal(record)); root.append(button);
    }
  } catch (error) { showError("#setup-error", error.message); }
  finally { onboardingBusy(false); }
}
function renderSetupReview(config, readiness) {
  const root = $("#setup-review-summary");
  root.replaceChildren(element("h3", "", "Before you create this run"));
  root.append(values([["Preparation", "Initial agent · included in the project budget"], ["Run name", runTitle() || "Set a research question in Project"], ["Project", config.project.source_dir], ["Objective", $("#setup-objective").value || "Set the research question in Project"], ["Experiments and measurement", "Established and checked by the research agents"], ["Execution", config.execution.backend], ["Experiment scheduling", "One experiment at a time per run; private source snapshots"], ["Resources per job", config.execution.backend === "local" ? "Unmanaged host resources" : `${config.execution.cpus} CPUs · ${config.execution.memory_mb} MiB · ${config.execution.gpus} GPUs`], ["Model", config.provider.model], ["Research model budget", money(config.budget.usd)]]));
  const files = readiness.source_files || [];
  const count = readiness.source_file_count || 0;
  const more = count - files.length;
  const fileSummary = count ? `${count} project files selected\n${files.join("\n")}${more > 0 ? `\n… and ${more} more` : ""}` : "Project files will appear after this folder passes setup.";
  root.append(rawDetails("Project files Metis will copy", fileSummary));
  root.append(element("p", "notice", "Create saves an idle run with a private copy of selected project files. Start begins the research workflow, including model calls and later experiments. Configuration checks are not a successful smoke experiment; a Step is one workflow checkpoint, not necessarily one experiment."));
}
function runTitle() {
  return $("#setup-run-title").value.trim() || $("#setup-objective").value.trim().replace(/\s+/g, " ").slice(0, 80);
}

function mergeConfig(base, extra) {
  const output = clone(base);
  for (const [key, value] of Object.entries(extra)) {
    if (["__proto__", "prototype", "constructor"].includes(key)) throw new Error("Invalid configuration key.");
    output[key] = value && typeof value === "object" && !Array.isArray(value) && output[key] && typeof output[key] === "object" && !Array.isArray(output[key]) ? mergeConfig(output[key], value) : clone(value);
  }
  return output;
}
function renderModelStatus(readiness) {
  const root = $("#setup-model-status");
  const rawName = $("#setup-key-env").value.trim();
  const name = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(rawName) ? rawName : "the named variable";
  $("#setup-key-name").textContent = name;
  const check = readiness?.checks?.find(item => item.name === "provider:default");
  root.className = `notice${check?.status === "error" ? " error" : ""}`;
  if (!check) { root.textContent = "Access for these edits has not been checked. Choose Check setup when ready."; return; }
  if (check.status !== "ok") {
    root.textContent = check.message;
    return;
  }
  let local = false;
  try { local = ["localhost", "127.0.0.1", "[::1]"].includes(new URL($("#setup-base-url").value).hostname); } catch { /* Readiness owns URL validation. */ }
  root.textContent = local ? "Local model configuration passed. No model request was made." : `${check.message} No model request was made.`;
}
function credentialName() {
  const target = $("#setup-credential-target").value;
  if (target === "google") return "GEMINI_API_KEY";
  return $(target === "laya" ? "#setup-laya-key-env" : "#setup-key-env").value.trim();
}
function renderRoutingStatus() {
  const config = state.setupBase;
  if (!config) return;
  const flashRoles = Object.entries(config.role_providers || {}).filter(([, provider]) => provider.name === "google").length;
  $("#setup-routing-status").textContent = `Primary: ${$("#setup-model").value}. Budget route: ${config.cheap_provider?.model || "primary model"}. Google role overrides: ${flashRoles}. Review all overrides in ${state.settingsMode ? "Advanced model routing" : "Advanced JSON"}.`;
}
async function applyGoogleProfile() {
  showError("#setup-error", "");
  $("#setup-google-profile").disabled = true;
  try {
    if (state.modelJsonDirty) throw new Error("Apply the model JSON edits before changing routing.");
    const config = readSetup();
    if (!state.settingsMode) state.runModelOverrides = true;
    const revision = state.setupRevision;
    const result = await api("/api/settings/model-profile", {config, profile: "google-flash"});
    if (revision !== state.setupRevision) throw new Error("Settings changed while preparing routing. Apply Google routing again to keep the current edits.");
    populateSetup(result.config);
    if (state.modelScope) {
      $("#model-settings-json").value = json(Object.fromEntries([...modelRoutingKeys, "laya"].map(key => [key, result.config[key]])));
      updateModelScopeControls();
    }
    $("#setup-credential-target").value = "google";
    $("#setup-api-key").value = "";
    await refreshCredentialStatus();
    $("#setup-api-key").focus();
    toast(state.settingsMode ? "Google routing added to the form. Connect its key and save settings when ready." : "Google routing added for this inquiry. Connect its key and check setup when ready.");
  } catch (error) { showError("#setup-error", error.message); }
  finally { $("#setup-google-profile").disabled = false; }
}
async function refreshCredentialStatus() {
  const name = credentialName();
  const root = $("#setup-credential-status");
  if (!/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(name)) { root.textContent = "Enter a valid key variable name."; return; }
  const result = await api("/api/credentials", {action: "status", name});
  if (name !== credentialName()) return;
  const labels = {vault: "Saved in this host's credential vault.", session: "Available for this server session only.", environment: "Available from this server's environment.", missing: "No key connected yet."};
  root.textContent = `${labels[result.source]} ${result.vault_available ? "Host vault available." : "Host vault unavailable. A previously saved vault key cannot be checked until access returns."}`;
  if (!result.vault_available) $("#setup-key-persistence").value = "session";
}
function lockCredentialControls(locked) {
  for (const id of ["setup-credential-target", "setup-api-key", "setup-key-env", "setup-laya-key-env", "setup-save-key", "setup-clear-key"]) $(`#${id}`).disabled = locked;
}
async function saveApiKey() {
  const field = $("#setup-api-key");
  const secret = field.value;
  field.value = "";
  showError("#setup-error", "");
  const name = credentialName();
  invalidateSetup();
  lockCredentialControls(true);
  try {
    const result = await api("/api/credentials", {action: "save", name, secret, persistence: $("#setup-key-persistence").value});
    if (name !== credentialName()) return;
    $("#setup-credential-status").textContent = result.source === "vault" ? "Saved in this host's credential vault." : result.vault_available ? "Saved for this server session only." : "Saved for this server session. A previous vault key could reappear if vault access returns.";
    invalidateSetup();
    renderModelStatus(null);
    toast(state.settingsMode ? "API key connected on this execution host." : "API key connected. Choose Check setup to review all prerequisites.");
  } catch (error) { showError("#setup-error", error.message); }
  finally { lockCredentialControls(false); updateModelScopeControls(); }
}
async function clearApiKey() {
  const name = credentialName();
  invalidateSetup();
  lockCredentialControls(true);
  $("#setup-api-key").value = "";
  showError("#setup-error", "");
  try {
    const result = await api("/api/credentials", {action: "clear", name});
    if (name !== credentialName()) return;
    $("#setup-credential-status").textContent = result.vault_unverified ? "Session key removed. Host vault was unavailable, so any older vault key could not be checked or removed." : result.source === "environment" ? "Saved key removed. A key remains available from this server's environment." : "Saved key removed.";
  } catch (error) { $("#setup-credential-status").textContent = "Key removal could not be fully verified."; showError("#setup-error", error.message); }
  finally { lockCredentialControls(false); invalidateSetup(); renderModelStatus(null); updateModelScopeControls(); }
}
async function openSetup(config, settingsMode = false, question = "") {
  closeFolderPicker();
  $("#project-folder-status").textContent = "";
  $("#setup-paper-links").value = "";
  $("#setup-paper-files").value = "";
  $("#onboarding-existing").open = false;
  $("#onboarding-manual").open = false;
  const opening = ++state.setupOpening;
  state.modelScopeRequest += 1;
  if (!settingsMode && state.modelScope) rememberModelDraft();
  state.setupRevision += 1;
  state.proposal = null; state.proposalPrepared = null;
  for (const selector of ["#onboarding-report", "#onboarding-preview", "#onboarding-result", "#generate-proposal", "#apply-proposal"]) $(selector).hidden = true;
  $("#onboarding-status").textContent = "";
  state.settingsMode = settingsMode;
  state.runModelOverrides = !!config;
  state.projectModelPending = null; state.projectModelError = "";
  $("#setup-profile-help").textContent = settingsMode ? "This edits the form. Save settings to use it for future runs. No model request is made." : "This changes only the new inquiry. Check setup before creating the run. No model request is made.";
  $("#setup-credential-target").value = "primary";
  $("#setup-key-help").open = false;
  $("#setup-provider-details").open = false;
  $("#setup-title").textContent = settingsMode ? "Workspace settings" : "Prepare your inquiry";
  $("#setup-description").textContent = settingsMode ? "Connect a model once and save reusable settings for future inquiries." : "Bring your question. Choose a project folder or let Metis create one when you check setup.";
  const projectNav = document.querySelector('.setup-section-button[data-section="project"]');
  const modelNav = document.querySelector('.setup-section-button[data-section="model"]');
  if (settingsMode) projectNav.before(modelNav);
  else $("#setup-more").append(modelNav);
  projectNav.textContent = settingsMode ? "02 Project defaults" : "01 Project";
  modelNav.textContent = settingsMode ? "01 Model access" : "Model overrides";
  $("#run-identity-fields").hidden = settingsMode;
  $("#setup-objective").required = !settingsMode;
  $("#save-settings").hidden = !settingsMode;
  $("#save-settings").disabled = true;
  $("#create-live").hidden = settingsMode;
  setSetupSection(settingsMode ? "model" : "project");
  if (settingsMode) {
    state.page = "settings";
    $("#model-settings-editor").append($("#setup-form"));
    $("#settings-page").hidden = false;
    $("#empty-workspace").hidden = true;
    $("#research").hidden = true;
  } else {
    state.modelScope = null;
    state.modelJsonDirty = false;
    for (const id of ["setup-model", "setup-base-url", "setup-key-env", "setup-google-profile", "setup-laya-enabled", "setup-laya-url", "setup-laya-model", "setup-laya-key-env", "setup-laya-cost"]) $(`#${id}`).disabled = false;
    if (state.page === "settings") showHome();
    $("#setup-dialog").append($("#setup-form"));
    $("#setup-dialog").showModal();
  }
  $("#setup-close").hidden = settingsMode;
  $("#setup-nav").hidden = settingsMode;
  $("#setup-back").hidden = settingsMode;
  $("#setup-next").hidden = settingsMode;
  $("#validate-setup").hidden = settingsMode;
  $("#setup-title").textContent = settingsMode ? "Models and decision advice" : "Prepare your inquiry";
  $("#setup-loading").hidden = false;
  showError("#setup-error", "");
  $("#setup-readiness").hidden = true;
  $("#create-live").disabled = true;
  $("#validate-setup").disabled = true;
  state.setupBase = null;
  state.validatedKey = null;
  try {
    const defaults = await api("/api/config");
    if (opening !== state.setupOpening) return;
    state.serverConfig = defaults.config;
    state.settingsRevision = defaults.revision;
    populateSetup(config ? mergeConfig(defaults.config, config) : defaults.config);
    try { await refreshCredentialStatus(); } catch (error) { $("#setup-credential-status").textContent = error.message; }
    if (opening !== state.setupOpening) return;
    renderModelStatus(defaults.readiness && !config ? defaults.readiness : null);
    $("#setup-run-title").value = "";
    $("#setup-objective").value = question;
    if (settingsMode) await loadModelScope(false);
    if (opening !== state.setupOpening) return;

    $(settingsMode ? "#model-settings-title" : "#setup-objective").focus();
  } catch (error) { showError("#setup-error", error.message); }
  finally { if (opening !== state.setupOpening) return; $("#setup-loading").hidden = true; $("#validate-setup").disabled = !state.setupBase; $("#save-settings").disabled = !state.setupBase || (settingsMode && !state.modelScope); if (settingsMode) updateModelScopeControls(); }
}
function populateSetup(config) {
  state.setupBase = clone(config);
  state.setupBase.mode = "live";
  const project = state.setupBase.project;
  const provider = state.setupBase.provider;
  const execution = state.setupBase.execution;
  $("#setup-source").value = project.source_dir || "";
  $("#setup-baseline").value = formatCommand(project.baseline_argv || []);
  $("#setup-evaluator").value = formatCommand(project.evaluator_argv || []);
  $("#setup-protected").value = (project.protected_paths || []).join("\n");
  $("#setup-metric").value = project.primary_metric;
  $("#setup-direction").value = project.metrics[project.primary_metric] || "max";
  $("#setup-sota").value = project.sota[project.primary_metric] ?? "";
  $("#setup-budget").value = state.setupBase.budget.usd;
  $("#setup-model").value = provider.model;
  $("#setup-key-env").value = provider.api_key_env;
  $("#setup-api-key").value = "";
  $("#setup-base-url").value = provider.base_url;
  const laya = state.setupBase.laya || {};
  $("#setup-laya-enabled").checked = !!laya.enabled;
  $("#setup-laya-details").open = !!laya.enabled;
  $("#setup-laya-url").value = laya.base_url || "http://127.0.0.1:8000";
  $("#setup-laya-model").value = laya.model || "multilingual";
  $("#setup-laya-key-env").value = laya.api_key_env || "LAYA_API_KEY";
  $("#setup-laya-cost").value = laya.cost_per_call_usd ?? 0;
  renderRoutingStatus();
  $("#setup-backend").value = execution.backend;
  $("#setup-cpus").value = execution.cpus ?? 2;
  $("#setup-memory").value = execution.memory_mb ?? 4096;
  $("#setup-gpus").value = execution.gpus ?? 0;
  $("#setup-docker-image").value = execution.docker_image || "";
  $("#setup-slurm-partition").value = execution.slurm_partition || "";
  $("#setup-slurm-account").value = execution.slurm_account || "";
  $("#setup-allow-local").checked = !!execution.allow_local;
  $("#setup-specification").value = project.specification || "";
  $("#setup-datasets").value = json(project.dataset_manifest || {});
  $("#setup-mounts").value = json(execution.readonly_mounts || {});
  $("#setup-max-calls").value = state.setupBase.budget.max_calls;
  $("#setup-max-experiments").value = state.setupBase.budget.max_experiments;
  $("#setup-wall").value = state.setupBase.budget.wall_seconds;
  $("#setup-traces").value = state.setupBase.privacy.traces;
  $("#setup-cache").checked = state.setupBase.privacy.cache;
  $("#setup-json").value = json(state.setupBase);
  state.jsonDirty = false;
  invalidateSetup();
  renderModelStatus(null);
  showBackendFields();
}
function invalidateSetup() {
  state.setupRevision += 1;
  state.validatedKey = null;
  $("#create-live").disabled = true;
  $("#validation-state").textContent = state.settingsMode ? "Unsaved edits. Save progress or check missing prerequisites." : "Validate setup before creating a run.";
  $("#setup-readiness").hidden = true;
}
function showBackendFields() {
  const backend = $("#setup-backend").value;
  $("#docker-options").hidden = backend !== "docker";
  $("#slurm-partition-options").hidden = backend !== "slurm";
  $("#slurm-account-options").hidden = backend !== "slurm";
  $("#local-options").hidden = backend !== "local";
  for (const value of ["docker", "slurm", "local"]) $(`#execution-${value}-help`).hidden = backend !== value;
  for (const value of ["cpus", "memory", "gpus"]) $(`#execution-${value}-options`).hidden = backend === "local";
  $("#execution-resource-help").hidden = backend === "local";
}
function stringArray(selector, name) {
  let value;
  try { value = JSON.parse($(selector).value); }
  catch { throw new Error(`${name} must be a JSON string array, for example ["python3", "train.py"].`); }
  if (!Array.isArray(value) || value.some((part) => typeof part !== "string" || !part.length)) throw new Error(`${name} must contain only nonempty strings.`);
  return value;
}
function readSetup() {
  if (!state.setupBase) throw new Error("Server configuration has not loaded.");
  if (state.jsonDirty) throw new Error("Advanced JSON has unapplied edits. Click Apply JSON to form before validating.");
  const config = clone(state.setupBase);
  config.mode = "live";
  if (!state.settingsMode) config.entry_mode = "agent";
  const previousMetric = config.project.primary_metric;
  const metric = $("#setup-metric").value.trim() || "score";
  if (!metric) throw new Error("A primary metric name is required.");
  if (metric !== previousMetric) {
    delete config.project.metrics[previousMetric];
    delete config.project.sota[previousMetric];
    delete config.project.baseline_expected[previousMetric];
    if (config.project.metric_units) delete config.project.metric_units[previousMetric];
  }
  config.project.source_dir = $("#setup-source").value.trim();
  config.project.baseline_argv = parseCommand($("#setup-baseline").value);
  config.project.evaluator_argv = parseCommand($("#setup-evaluator").value);
  config.project.protected_paths = $("#setup-protected").value.trim().startsWith("[") ? stringArray("#setup-protected", "Protected paths") : $("#setup-protected").value.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
  config.project.primary_metric = metric;
  config.project.metrics[metric] = $("#setup-direction").value;
  if ($("#setup-sota").value === "") delete config.project.sota[metric];
  else config.project.sota[metric] = Number($("#setup-sota").value);
  config.budget.usd = Number($("#setup-budget").value);
  config.provider.model = $("#setup-model").value.trim();
  config.provider.base_url = $("#setup-base-url").value.trim();
  const keyName = $("#setup-key-env").value.trim();
  if (keyName.length > 128 || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(keyName)) {
    $("#setup-key-env").value = "";
    renderModelStatus(null);
    setSetupSection("model");
    $("#setup-key-env").focus();
    throw new Error("Enter a key variable name, such as XAI_API_KEY, not an API key. Then save the key above.");
  }
  config.provider.api_key_env = keyName;
  const layaKey = $("#setup-laya-key-env").value.trim();
  if (!/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(layaKey)) {
    $("#setup-laya-key-env").value = "";
    setSetupSection("model");
    $("#setup-laya-details").open = true;
    $("#setup-laya-key-env").focus();
    throw new Error("Enter a Laya key variable name, such as LAYA_API_KEY. Save the secret using Key for above.");
  }
  config.laya = {...(config.laya || {}), enabled: $("#setup-laya-enabled").checked,
    base_url: $("#setup-laya-url").value.trim(), model: $("#setup-laya-model").value.trim(),
    api_key_env: layaKey, cost_per_call_usd: Number($("#setup-laya-cost").value)};
  config.execution.backend = $("#setup-backend").value;
  config.execution.cpus = Number($("#setup-cpus").value);
  config.execution.memory_mb = Number($("#setup-memory").value);
  config.execution.gpus = Number($("#setup-gpus").value);
  config.execution.docker_image = $("#setup-docker-image").value.trim();
  config.execution.slurm_partition = $("#setup-slurm-partition").value.trim();
  config.execution.slurm_account = $("#setup-slurm-account").value.trim();
  config.execution.allow_local = $("#setup-allow-local").checked;
  config.project.specification = $("#setup-specification").value;
  config.project.dataset_manifest = JSON.parse($("#setup-datasets").value);
  config.execution.readonly_mounts = JSON.parse($("#setup-mounts").value);
  config.budget.max_calls = Number($("#setup-max-calls").value);
  config.budget.max_experiments = Number($("#setup-max-experiments").value);
  config.budget.wall_seconds = Number($("#setup-wall").value);
  config.privacy.traces = $("#setup-traces").value;
  config.privacy.cache = $("#setup-cache").checked;
  if (config.model_inventory && JSON.stringify(config.provider) !== JSON.stringify(state.setupBase.provider)) config.model_inventory = null;
  return config;
}
async function saveSettings() {
  if (state.modelScope) { await saveModelScope(); return; }
  showError("#setup-error", "");
  $("#save-settings").disabled = true;
  const revision = state.setupRevision;
  try {
    const config = readSetup();
    const result = await api("/api/settings", {config, revision: state.settingsRevision});
    state.settingsRevision = result.revision;
    state.serverConfig = clone(config);
    $("#validation-state").textContent = revision === state.setupRevision ? "Settings saved for future runs. Check setup for missing prerequisites." : "Earlier edits saved; newer changes are still unsaved.";
    toast("Settings saved privately. Existing runs are unchanged; no research started.");
  } catch (error) { showError("#setup-error", error.message); }
  finally { $("#save-settings").disabled = false; }
}

const modelRoutingKeys = ["model_inventory", "allowed_models", "provider", "cheap_provider", "frontier_provider", "role_providers", "role_panels"];
function modelDraftKey(scope, project) { return `${scope}:${project}`; }
function rememberModelDraft() {
  if (!state.modelScope) return;
  const config = readSetup();
  const key = modelDraftKey(state.modelScope.scope, state.modelScope.project);
  const routing = $("#model-settings-routing").checked;
  const laya = $("#model-settings-laya").checked;
  const changed = [...modelRoutingKeys, "laya"].some(name => JSON.stringify(config[name]) !== JSON.stringify(state.modelScope.config[name]));
  if (!changed && !state.modelJsonDirty && routing === modelRoutingKeys.some(name => Object.hasOwn(state.modelScope.overrides, name)) && laya === Object.hasOwn(state.modelScope.overrides, "laya")) {
    state.modelDrafts.delete(key); return;
  }
  state.modelDrafts.set(key, {
    snapshot: clone(state.modelScope), config,
    modelJSON: $("#model-settings-json").value, modelJsonDirty: !!state.modelJsonDirty,
    routing: $("#model-settings-routing").checked, laya: $("#model-settings-laya").checked,
  });
}
async function openModelSettings() {
  if (typeof openInventory === "function") return openInventory();
  if (state.modelScope && state.settingsMode) {
    state.page = "settings";
    $("#settings-page").hidden = false;
    $("#research").hidden = true;
    $("#empty-workspace").hidden = true;
    $("#model-settings-title").focus();
    return;
  }
  await openSetup(undefined, true);
}
function updateModelScopeControls() {
  const current = state.modelScope;
  if (!current) return;
  const global = current.scope === "global";
  const locked = global && current.managed;
  $("#model-settings-overrides").hidden = global;
  const routing = !locked && (global || $("#model-settings-routing").checked);
  const laya = !locked && (global || $("#model-settings-laya").checked);
  for (const id of ["setup-model", "setup-base-url", "setup-key-env", "setup-google-profile"]) $(`#${id}`).disabled = !routing;
  for (const id of ["setup-laya-enabled", "setup-laya-url", "setup-laya-model", "setup-laya-key-env", "setup-laya-cost"]) $(`#${id}`).disabled = !laya;
  $("#model-settings-json").disabled = locked;
  $("#model-settings-json-apply").disabled = locked;
  $("#save-settings").disabled = locked;
  $("#model-settings-origin").textContent = global
    ? current.managed ? "Global defaults are managed from your local console. Choose this workspace or a project to override them." : "Editing global defaults for local and connected SSH workspaces."
    : `${current.scope === "project" ? current.project : "This workspace"}: unchecked groups follow ${current.scope === "project" ? "workspace settings" : "global defaults"}.${current.legacy ? " Previous workspace choices were preserved as overrides." : ""}`;
}
async function loadModelScope(remember = true, reload = false) {
  const scope = $("#model-settings-scope").value || "global";
  const project = scope === "project" ? $("#model-settings-project").value.trim() : "";
  const request = ++state.modelScopeRequest;
  const editRevision = state.setupRevision;
  showError("#setup-error", "");
  try {
    if (remember) rememberModelDraft();
    const key = modelDraftKey(scope, project);
    const draft = reload ? null : state.modelDrafts.get(key);
    const result = draft?.snapshot || await api("/api/settings/models", {scope, project});
    if (request !== state.modelScopeRequest || editRevision !== state.setupRevision) return;
    state.modelScope = result;
    populateSetup(draft?.config || result.config);
    $("#model-settings-routing").checked = draft ? draft.routing : modelRoutingKeys.some(key => Object.hasOwn(result.overrides, key));
    $("#model-settings-laya").checked = draft ? draft.laya : Object.hasOwn(result.overrides, "laya");
    $("#setup-readiness").hidden = true;
    $("#validation-state").textContent = draft ? "Unsaved edits restored for this scope." : "Saved values loaded. Changes apply to future runs.";
    $("#model-settings-json").value = draft?.modelJSON || json(Object.fromEntries([...modelRoutingKeys, "laya"].map(key => [key, result.config[key]])));
    state.modelJsonDirty = !!draft?.modelJsonDirty;
    updateModelScopeControls();
    await refreshCredentialStatus();
  } catch (error) { showError("#setup-error", error.message); }
}
function inheritModelGroup(group) {
  if (!state.modelScope) return;
  const config = readSetup();
  const keys = group === "laya" ? ["laya"] : modelRoutingKeys;
  for (const key of keys) config[key] = clone(state.modelScope.inherited[key]);
  populateSetup(config);
  updateModelScopeControls();
}
async function saveModelScope() {
  if (state.modelJsonDirty) { showError("#setup-error", "Apply model JSON edits before saving."); return; }
  const scope = state.modelScope;
  const revision = state.setupRevision;
  $("#save-settings").disabled = true;
  showError("#setup-error", "");
  try {
    const config = readSetup();
    const overrides = {};
    if (scope.scope === "global" || $("#model-settings-routing").checked) for (const key of modelRoutingKeys) overrides[key] = config[key];
    if (scope.scope === "global" || $("#model-settings-laya").checked) overrides.laya = config.laya;
    const result = await api("/api/settings/models", {scope: scope.scope, project: scope.project, revision: scope.revision, overrides});
    if (state.modelScope !== scope) return;
    state.modelScope = result;
    state.modelDrafts.delete(modelDraftKey(scope.scope, scope.project));
    $("#validation-state").textContent = revision === state.setupRevision ? `${human(scope.scope)} settings saved for future runs.` : "Earlier edits saved; newer changes are still unsaved.";
    const sync = Object.entries(result.sync || {}).map(([name, status]) => `${name}: ${status}`).join(" · ");
    $("#model-settings-sync").hidden = !sync;
    $("#model-settings-sync").textContent = sync;
    updateModelScopeControls();
  } catch (error) { showError("#setup-error", error.message); }
  finally { updateModelScopeControls(); }
}
$("#model-settings-json").addEventListener("input", () => { state.modelJsonDirty = true; invalidateSetup(); });
$("#model-settings-json-apply").addEventListener("click", async () => {
  const scope = state.modelScope;
  const revision = state.setupRevision;
  try {
    const values = JSON.parse($("#model-settings-json").value);
    if (Object.keys(values).some(key => ![...modelRoutingKeys, "laya"].includes(key))) throw new Error("Only model routing and Laya keys belong here.");
    const result = await api("/api/settings/validate", {config: {...readSetup(), ...values}});
    if (scope !== state.modelScope || revision !== state.setupRevision) throw new Error("Settings changed while validating JSON. Apply again.");
    populateSetup(result.config);
    state.modelJsonDirty = false;
    if (modelRoutingKeys.some(key => Object.hasOwn(values, key))) $("#model-settings-routing").checked = true;
    if (Object.hasOwn(values, "laya")) $("#model-settings-laya").checked = true;
    updateModelScopeControls();
  } catch (error) { showError("#setup-error", error.message); }
});
$("#model-settings-load").addEventListener("click", () => loadModelScope());
$("#model-settings-reload").addEventListener("click", () => loadModelScope(false, true));
$("#model-settings-scope").addEventListener("change", () => { $("#model-settings-project-label").hidden = $("#model-settings-scope").value !== "project"; });
for (const group of ["routing", "laya"]) $(`#model-settings-${group}`).addEventListener("change", () => {
  if (!$(`#model-settings-${group}`).checked) inheritModelGroup(group);
  invalidateSetup(); updateModelScopeControls();
});
$("#model-settings-inherit").addEventListener("click", () => {
  $("#model-settings-routing").checked = false; $("#model-settings-laya").checked = false;
  inheritModelGroup("routing"); inheritModelGroup("laya");
});

async function openGuide() {
  $("#guide-dialog").showModal();
  $("#welcome-guide-text").textContent = "Loading getting started guide…";
  try { $("#welcome-guide-text").textContent = (await api("/api/config")).guide; }
  catch (error) { $("#welcome-guide-text").textContent = error.message; }
}
async function validateSetup() {
  if (state.folderCreating) return;
  const opening = state.setupOpening;
  if (!$("#setup-source").value.trim() && !state.settingsMode) {
    if (!await createProjectFolder()) return;
  }
  let resolving;
  do { resolving = state.projectModelPending; if (resolving) await resolving; } while (resolving !== state.projectModelPending);
  if (opening !== state.setupOpening) return;
  if (state.projectModelError && !state.runModelOverrides) { showError("#setup-error", state.projectModelError); return; }
  showError("#setup-error", "");

  let config;
  try { config = readSetup(); }
  catch (error) { showError("#setup-error", error.message); return; }
  const revision = state.setupRevision;
  state.setupBusy = true;
  $("#validate-setup").disabled = true;
  $("#create-live").disabled = true;
  $("#validation-state").textContent = "Checking project files and execution setup…";
  try {
    let readiness = await api("/api/preflight", { config });
    if (revision !== state.setupRevision) { $("#validation-state").textContent = "Setup changed while validation was running. Validate again."; return; }
    let actions = [];
    const sourceNeedsSelection = config.project.source_dir && (readiness.guidance?.some(step => step.checks.includes("source")) || readiness.checks?.some(check => ["baseline", "evaluator"].includes(check.name) && check.status === "error" && check.message.includes("missing from the selected project files")) || readiness.guidance?.some(step => step.checks.includes("protected-evaluator")));
    if (sourceNeedsSelection || readiness.guidance?.some(step => step.owner === "metis" && step.checks.includes("docker-image"))) {
      const recovered = await api("/api/onboarding/recover", {config});
      if (revision !== state.setupRevision) { $("#validation-state").textContent = "Setup changed while Metis was preparing it. Check the current settings again."; return; }
      config = recovered.config;
      readiness = recovered.readiness;
      actions = recovered.actions || [];
      state.setupBase = clone(config);
      $("#setup-docker-image").value = config.execution.docker_image;
      $("#setup-json").value = json(config);
    }
    let inspection = null;
    let inspectionError = "";
    if (!readiness.ready && readiness.guidance?.some(step => step.title === "Inspect the project")) {
      try {
        inspection = await api("/api/onboarding/inspect", {source_dir: config.project.source_dir});
        if (revision !== state.setupRevision) { $("#validation-state").textContent = "Setup changed while inspection was running. Validate again."; return; }
        renderInspection(inspection, $("#onboarding-report"));
      } catch (error) { inspectionError = error.message; }
    }
    if (revision !== state.setupRevision) { $("#validation-state").textContent = "Setup changed while inspection was running. Validate again."; return; }
    showReadiness(readiness, inspection, inspectionError, actions);
    renderModelStatus(readiness);
    renderSetupReview(config, readiness);
    setSetupSection("review");
    state.validatedKey = readiness.ready ? JSON.stringify(config) : null;
    $("#create-live").disabled = !readiness.ready;
    $("#validation-state").textContent = readiness.ready ? "Validated. Creating the run will not start execution." : "Follow the next steps, then check setup again.";
    $("#setup-json").value = json(config);
    state.setupBase = clone(config);
  } catch (error) {
    if (error.readiness) showReadiness(error.readiness);
    showError("#setup-error", error.message);
    $("#validation-state").textContent = "Validation did not pass.";
  } finally { state.setupBusy = false; $("#validate-setup").disabled = false; }
}
async function createLive(event) {
  event.preventDefault();
  if (state.settingsMode) { await saveSettings(); return; }
  for (const selector of ["#setup-objective"]) {
    if (!$(selector).checkValidity()) {
      setSetupSection("project");
      $(selector).reportValidity();
      return;
    }
  }
  if (!$("#setup-objective").value.trim()) {
    setSetupSection("project");
    $("#setup-objective").focus();
    showError("#setup-error", "Enter a research question before creating a run.");
    return;
  }
  showError("#setup-error", "");
  let config;
  try {
    config = readSetup();
    if (state.validatedKey !== JSON.stringify(config)) throw new Error("Validate the current setup before creating a run.");
  } catch (error) { showError("#setup-error", error.message); return; }
  $("#create-live").disabled = true;
  try {
    const papers = $("#setup-paper-links").value.split(/\r?\n/).map(value => value.trim()).filter(Boolean).map(locator => ({name: locator, locator}));
    for (const file of ($("#setup-paper-files").files || [])) {
      if (file.size > 10000000) throw new Error("Each associated paper must be at most 10 MB.");
      const content_base64 = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1]); reader.onerror = () => reject(new Error("Could not read the selected paper.")); reader.readAsDataURL(file); });
      papers.push({name: file.name, content_base64});
    }
    const { run } = await api("/api/runs", { title: runTitle(), objective: $("#setup-objective").value, demo: false, config, papers });
    $("#setup-dialog").close();
    await selectRun(run.id);
    await refresh();
    toast("Live run created. Use Start research when you are ready to execute.");
  } catch (error) {
    if (error.readiness) {
      showReadiness(error.readiness);
      if (!error.readiness.ready) state.validatedKey = null;
    }
    showError("#setup-error", error.message);
  } finally { $("#create-live").disabled = !state.validatedKey; }
}
async function applyAdvanced() {
  const revision = state.setupRevision;
  try {
    const parsed = JSON.parse($("#setup-json").value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Configuration must be a JSON object.");
    const normalized = await api("/api/settings/validate", {config: parsed});
    if (revision !== state.setupRevision) throw new Error("Settings changed while applying JSON. Apply the current JSON again.");
    populateSetup(normalized.config);
    showError("#setup-error", "");
    $("#setup-readiness").hidden = true;
    toast("Configuration applied. Review the fields and validate the setup.");
  } catch (error) { showError("#setup-error", `Cannot apply configuration: ${error.message}`); }
}
async function runAction(action, body = {}) {
  if (!state.id) return;
  try {
    showError("#global-error", "");
    await api(`/api/runs/${encodeURIComponent(state.id)}/${action}`, body);
    if (action === "pause") toast("Pause requested. The current checkpoint must finish before the run stops.");
    else if (action === "cancel-experiment") toast("Cancellation recorded. The run remains paused.");
    await refresh();
  } catch (error) { showError("#global-error", error.message); }
}

const remoteFields = {
  name: "#remote-name", host: "#remote-host", port: "#remote-port",
  identity_file: "#remote-identity-file", directory: "#remote-directory", python: "#remote-python",
  state_dir: "#remote-state-dir", db_dir: "#remote-db-dir", config_path: "#remote-config-path",
};
function connectionProfile() {
  if (!state.connectionKey.startsWith("profile:")) return null;
  return state.connectionProfiles.find(profile => profile.name === state.connectionKey.slice(8)) || null;
}
function connectionOption(key, title, subtitle, status, icon) {
  const button = element("button", `connection-option${state.connectionKey === key ? " selected" : ""}`);
  button.type = "button"; button.dataset.key = key;
  button.setAttribute("aria-pressed", String(state.connectionKey === key));
  const copy = element("span", "connection-option-copy");
  copy.append(element("strong", "", title), element("small", "", subtitle));
  button.append(element("span", "connection-option-icon", icon), copy, element("span", "connection-option-state", status));
  button.addEventListener("click", () => {
    state.connectionKey = key; state.connectionNotice = "";
    renderConnectionPicker();
    for (const option of $("#connection-options").children) if (option.dataset.key === key) option.focus();
  });
  return button;
}
function renderConnectionPicker() {
  const root = $("#connection-options"); root.replaceChildren();
  const primary = $("#connection-primary"), dashboard = $("#connection-dashboard");
  const details = $("#connection-details"), disconnect = $("#connection-disconnect");
  dashboard.hidden = true; dashboard.removeAttribute("href"); details.hidden = true; disconnect.hidden = true;
  $("#connection-search").disabled = state.managedRemote;
  $("#connection-add").hidden = state.managedRemote;
  if (state.managedRemote) {
    root.append(connectionOption("remote", state.remoteLabel, "Remote research workspace", "Current", "⌁"));
    $("#connection-guidance").textContent = "Research is running on this host. Use the local console to manage SSH connections.";
    primary.hidden = true;
  } else {
    const query = $("#connection-search").value.trim().toLowerCase();
    root.append(connectionOption("local", "This computer", "Local research workspace", "Current", "⌂"));
    const matching = state.connectionProfiles.filter(profile => `${profile.name} ${profile.host}`.toLowerCase().includes(query));
    for (const profile of matching) {
      root.append(connectionOption(`profile:${profile.name}`, profile.name, profile.host,
        state.connectionDashboards.has(profile.name) ? "Connected" : "Saved", "⌁"));
    }
    const savedHosts = new Set(state.connectionProfiles.map(profile => profile.host));
    for (const host of state.connectionHosts.filter(host => !savedHosts.has(host) && host.toLowerCase().includes(query))) {
      root.append(connectionOption(`alias:${host}`, host, "SSH configuration", "Set up", "⌁"));
    }
    const profile = connectionProfile();
    const alias = state.connectionKey.startsWith("alias:") ? state.connectionKey.slice(6) : "";
    primary.hidden = false; primary.disabled = state.connectionBusy;
    if (profile) {
      const url = state.connectionDashboards.get(profile.name);
      $("#connection-guidance").textContent = url
        ? "The SSH tunnel is open. Your research continues on the remote host after disconnecting."
        : "Connect using your local SSH client. Sign in and check the host if setup needs attention.";
      primary.hidden = !!url; primary.textContent = `Connect to ${profile.name}`;
      details.hidden = false; details.textContent = "Connection settings";
      disconnect.hidden = !url;
      dashboard.hidden = !url;
      if (url) dashboard.href = url;
    } else if (alias) {
      $("#connection-guidance").textContent = "Save this SSH alias as a connection, then sign in and check its runtime.";
      primary.textContent = "Set up host";
    } else {
      $("#connection-guidance").textContent = "Research and settings in this local console.";
      primary.textContent = "Stay on this computer";
    }
  }
  $("#connection-picker-status").textContent = state.connectionNotice;
  $("#connection-picker-status").hidden = !state.connectionNotice;
}
function searchConnections() {
  const query = $("#connection-search").value.trim().toLowerCase();
  const profile = state.connectionProfiles.find(item => `${item.name} ${item.host}`.toLowerCase().includes(query));
  const savedHosts = new Set(state.connectionProfiles.map(item => item.host));
  const alias = state.connectionHosts.find(host => !savedHosts.has(host) && host.toLowerCase().includes(query));
  state.connectionKey = profile ? `profile:${profile.name}` : alias ? `alias:${alias}` : "local";
  renderConnectionPicker();
}
async function openConnectionPicker() {
  if ($("#remote-dialog").open || $("#ssh-auth-dialog").open) return;
  $("#connection-picker").showModal();
  $("#connection-switch").setAttribute("aria-expanded", "true");
  $("#connection-search").value = "";
  $("#connection-add").open = false;
  $("#connection-new-host").value = "";
  state.connectionNotice = state.managedRemote ? "" : "Loading SSH connections…";
  renderConnectionPicker();
  $("#connection-search").focus();
  if (state.managedRemote) return;
  try {
    const data = await api("/api/remotes");
    state.connectionProfiles = data.profiles || [];
    state.connectionHosts = data.hosts || [];
    const statuses = await Promise.all(state.connectionProfiles.map(async profile => {
      try {
        const status = await api(`/api/remotes/${encodeURIComponent(profile.name)}/status`);
        return [profile.name, status.status === "connected" ? remoteDashboardURL(status.url) : null];
      } catch { return [profile.name, null]; }
    }));
    state.connectionDashboards = new Map(statuses.filter(([, url]) => url));
    if (state.connectionKey === "local" && state.connectionProfiles.length) {
      const connected = state.connectionProfiles.find(profile => state.connectionDashboards.has(profile.name));
      state.connectionKey = `profile:${(connected || state.connectionProfiles[0]).name}`;
    }
    if (state.connectionKey.startsWith("profile:") && !connectionProfile()) state.connectionKey = "local";
    state.connectionNotice = "";
  } catch (error) { state.connectionNotice = `Could not load SSH connections: ${error.message}`; }
  if ($("#connection-picker").open) {
    if ($("#connection-search").value.trim()) searchConnections();
    else renderConnectionPicker();
  }
}
function connectionName(host) {
  return host.replace(/^[^@]+@/, "").replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64) || "remote";
}
function unusedConnectionName(host) {
  const base = connectionName(host);
  const saved = new Set(state.remoteProfiles.map(profile => profile.name));
  let name = base, index = 2;
  while (saved.has(name)) {
    const suffix = `-${index++}`;
    name = `${base.slice(0, 64 - suffix.length)}${suffix}`;
  }
  return name;
}
async function openRemoteSettings(profileName = "", host = "") {
  $("#connection-picker").close();
  $("#remote-dialog").showModal(); showError("#remote-error", "");
  if (state.remoteDirty) {
    $("#remote-status").textContent = "Your unsaved connection draft is still here. Save it, or choose New connection to discard it before switching profiles.";
    return;
  }
  state.remoteBusy = true; remoteControls();
  try {
    await loadRemotes(profileName);
    if (host) {
      fillRemote({name: unusedConnectionName(host), host});
      state.remoteDirty = true; remoteControls();
      $("#remote-status").textContent = "Review this host, then save the connection before signing in.";
    }
  } catch (error) { showError("#remote-error", error.message); }
  finally { state.remoteBusy = false; remoteControls(); }
}
async function finishConnection(name) {
  state.connectionBusy = true; state.connectionNotice = `Connecting to ${name}…`; renderConnectionPicker();
  try {
    const result = await api(`/api/remotes/${encodeURIComponent(name)}/connect`, {});
    const url = result.status === "connected" ? remoteDashboardURL(result.url) : null;
    if (url) {
      state.connectionDashboards.set(name, url);
      state.connectionNotice = `${name} connected. Open its remote dashboard to continue.`;
    } else {
      state.connectionDashboards.delete(name);
      state.connectionNotice = result.message || "Connection needs attention. Open connection settings.";
    }
  } catch (error) { state.connectionNotice = `Connection failed: ${error.message}`; }
  finally { state.connectionBusy = false; renderConnectionPicker(); }
}
async function connectFromPicker() {
  const profile = connectionProfile();
  if (!profile || state.connectionBusy) return;
  state.connectionBusy = true; state.connectionNotice = `Signing in to ${profile.name}…`; renderConnectionPicker();
  try {
    const result = await api(`/api/remotes/${encodeURIComponent(profile.name)}/authenticate`, {});
    if (result.status === "authenticated") await finishConnection(profile.name);
    else if (result.status === "authenticating") {
      state.connectionPendingAuth = profile.name;
      renderAuthentication(result);
      $("#ssh-auth-dialog").showModal(); $("#ssh-auth-answer").focus();
      authTimer = setTimeout(pollAuthentication, 750);
      state.connectionNotice = "Answer the SSH prompt to continue connecting.";
    } else state.connectionNotice = result.message || "SSH sign in needs attention.";
  } catch (error) { state.connectionNotice = `SSH sign in failed: ${error.message}`; }
  finally { state.connectionBusy = false; renderConnectionPicker(); }
}
async function disconnectFromPicker() {
  const profile = connectionProfile();
  if (!profile || state.connectionBusy) return;
  state.connectionBusy = true; renderConnectionPicker();
  try {
    const result = await api(`/api/remotes/${encodeURIComponent(profile.name)}/disconnect`, {});
    state.connectionDashboards.delete(profile.name);
    state.connectionNotice = result.message || "Tunnel closed. Remote research continues.";
  } catch (error) { state.connectionNotice = `Disconnect failed: ${error.message}`; }
  finally { state.connectionBusy = false; renderConnectionPicker(); }
}
function remoteControls() {
  for (const selector of ["#remote-profile", "#remote-save", ...Object.values(remoteFields)]) $(selector).disabled = state.remoteBusy;
  for (const action of ["sign-in", "probe", "install", "connect", "disconnect"]) {
    $(`#remote-${action}`).disabled = state.remoteBusy || state.remoteDirty || !state.remoteName;
  }
}
function fillRemote(profile = {}) {
  for (const [key, selector] of Object.entries(remoteFields)) {
    $(selector).value = String(profile[key] ?? ({ directory: "~/.local/share/autoresearch/remote", python: "python3" }[key] || ""));
  }
  state.remoteName = profile.name || "";
  state.remoteDirty = false;
  $("#remote-open").hidden = true;
  $("#remote-open").removeAttribute("href");
  $("#remote-connect").textContent = "Connect";
  $("#remote-report").replaceChildren(); $("#remote-report").hidden = true;
  $("#remote-status").textContent = state.remoteName ? "Connection saved. Sign in or check the remote runtime." : "Enter a host and save the connection.";
  remoteControls();
}
function readRemote() {
  const profile = {};
  for (const [key, selector] of Object.entries(remoteFields)) profile[key] = $(selector).value.trim() || null;
  if (profile.port !== null) profile.port = Number(profile.port);
  return profile;
}
async function loadRemotes(selected = state.remoteName) {
  const data = await api("/api/remotes");
  state.remoteProfiles = data.profiles;
  $("#ssh-hosts").replaceChildren();
  for (const host of data.hosts) {
    const option = element("option", "", host); option.value = host; $("#ssh-hosts").append(option);
  }
  $("#remote-profile").replaceChildren();
  const blank = element("option", "", "New connection"); blank.value = ""; $("#remote-profile").append(blank);
  for (const profile of data.profiles) {
    const option = element("option", "", `${profile.name} · ${profile.host}`); option.value = profile.name; $("#remote-profile").append(option);
  }
  $("#remote-profile").value = selected;
  fillRemote(data.profiles.find(profile => profile.name === selected));
}
function remoteDashboardURL(value) {
  try {
    const url = new URL(value);
    const loopbackHosts = ["127.0.0.1", "localhost"];
    if (url.protocol !== "http:" || !loopbackHosts.includes(url.hostname) || !loopbackHosts.includes(location.hostname) || !url.port || url.username || url.password || url.pathname !== "/" || url.search) return null;
    const token = new URLSearchParams(url.hash.slice(1)).get("remote-token");
    // Keep navigation same-site: the managed controller rejects cross-site requests,
    // and localhost and 127.0.0.1 are distinct sites even though both use loopback.
    url.hostname = location.hostname;
    return /^[A-Za-z0-9_-]{16,512}$/.test(token || "") ? url.href : null;
  } catch { return null; }
}
function renderRemoteStatus(result) {
  const status = result.status || "complete";
  $("#remote-status").textContent = `${result.host || $("#remote-host").value}: ${human(status)}${result.message ? ` · ${result.message}` : ""}`;
  const candidate = result.url === undefined ? $("#remote-open").href : result.url;
  const url = status === "connected" ? remoteDashboardURL(candidate) : null;
  $("#remote-open").hidden = !url;
  if (url) $("#remote-open").href = url;
  else $("#remote-open").removeAttribute("href");
  $("#remote-connect").textContent = status === "connected" ? "Reconnect" : "Connect";
}
function renderRemoteReport(action, result) {
  const root = $("#remote-report"); root.replaceChildren(); root.hidden = false;
  root.append(element("h3", "", action === "probe" ? "Last remote check" : "Last runtime installation"));
  const success = result.ready === false || result.status === "error" || result.status === "failed" || result.error ? "Needs attention" : human(result.status || (result.ready ? "ready" : "completed"));
  root.append(element("p", "", `${success}${result.message ? ` · ${result.message}` : ""}`));
  if (result.error) root.append(element("p", "notice error", result.error));
  for (const problem of result.problems || []) root.append(element("p", "notice error", typeof problem === "string" ? problem : json(problem)));
  if (result.research_dir) root.append(element("p", "", `Research files: ${result.research_dir}`));
  if (result.database_dir) root.append(element("p", "", `Database: ${result.database_dir}`));
  const diagnostics = Object.fromEntries(["python", "python_version", "python_candidates", "database_filesystem", "slurm"].filter(key => result[key] !== undefined).map(key => [key, result[key]]));
  if (Object.keys(diagnostics).length) root.append(rawDetails("Runtime and database checks", diagnostics));
}
async function remoteAction(action) {
  if (state.remoteBusy || !state.remoteName || state.remoteDirty) return;
  state.remoteBusy = true; remoteControls(); showError("#remote-error", "");
  $("#remote-status").textContent = `${human(action)} in progress…`;
  try {
    const result = await api(`/api/remotes/${encodeURIComponent(state.remoteName)}/${action}`, {});
    if (["probe", "install"].includes(action)) {
      renderRemoteReport(action, result);
      $("#remote-status").textContent = `${human(action)} completed. See the report below.`;
    } else renderRemoteStatus(result);
  } catch (error) {
    showError("#remote-error", error.message); $("#remote-status").textContent = `${human(action)} failed.`;
    if (["probe", "install"].includes(action)) renderRemoteReport(action, {status: "failed", error: error.message});
  }
  finally { state.remoteBusy = false; remoteControls(); }
}
async function refreshRemoteStatus() {
  if (state.managedRemote || !$("#remote-dialog").open || !state.remoteName || state.remoteBusy || state.remoteDirty) return;
  const name = state.remoteName;
  try {
    const result = await api(`/api/remotes/${encodeURIComponent(name)}/status`);
    if (state.remoteName === name && !state.remoteBusy && !state.remoteDirty) renderRemoteStatus(result);
  } catch (error) { showError("#remote-error", error.message); }
}
let authTimer;
function renderAuthentication(result) {
  state.remoteAuth = result;
  $("#ssh-auth-output").textContent = result.output || "";
  $("#ssh-auth-output").scrollTop = $("#ssh-auth-output").scrollHeight;
  $("#ssh-auth-status").textContent = result.message || human(result.status);
  const active = result.status === "authenticating";
  $("#ssh-auth-answer").disabled = !active || state.authBusy;
  $("#ssh-auth-send").disabled = !active || state.authBusy;
  $("#ssh-auth-cancel").textContent = active ? "Cancel sign in" : "Close";
  if (!active) { clearTimeout(authTimer); $("#ssh-auth-answer").value = ""; }
  if (!active && state.connectionPendingAuth) {
    const name = state.connectionPendingAuth;
    state.connectionPendingAuth = "";
    if (result.status === "authenticated") {
      if ($("#ssh-auth-dialog").open) $("#ssh-auth-dialog").close();
      void finishConnection(name);
    }
    else {
      state.connectionNotice = result.message || "SSH sign in did not complete.";
      renderConnectionPicker();
    }
  }
}
async function pollAuthentication() {
  const session = state.remoteAuth?.session_id;
  if (!session || state.remoteAuth.status !== "authenticating") return;
  try {
    const result = await api(`/api/remotes/authentication/${encodeURIComponent(session)}`);
    if (state.remoteAuth?.session_id === session && state.remoteAuth.status === "authenticating") renderAuthentication(result);
  } catch (error) { showError("#ssh-auth-error", error.message); }
  if (state.remoteAuth?.session_id === session && state.remoteAuth.status === "authenticating") authTimer = setTimeout(pollAuthentication, 750);
}
async function startAuthentication() {
  if (state.remoteBusy || !state.remoteName || state.remoteDirty) return;
  state.remoteBusy = true; remoteControls(); showError("#remote-error", "");
  showError("#ssh-auth-error", ""); $("#ssh-auth-answer").value = "";
  try {
    const result = await api(`/api/remotes/${encodeURIComponent(state.remoteName)}/authenticate`, {});
    renderAuthentication(result);
    $("#ssh-auth-dialog").showModal(); $("#ssh-auth-answer").focus();
    authTimer = setTimeout(pollAuthentication, 750);
  } catch (error) { showError("#remote-error", error.message); state.remoteBusy = false; remoteControls(); }
}
async function answerAuthentication(event) {
  event.preventDefault();
  if (state.authBusy || state.remoteAuth?.status !== "authenticating") return;
  const answer = $("#ssh-auth-answer").value;
  $("#ssh-auth-answer").value = "";
  state.authBusy = true; renderAuthentication(state.remoteAuth); showError("#ssh-auth-error", "");
  try {
    const result = await api(`/api/remotes/authentication/${encodeURIComponent(state.remoteAuth.session_id)}/answer`, {answer});
    renderAuthentication(result);
  } catch (error) { showError("#ssh-auth-error", error.message); }
  finally { state.authBusy = false; renderAuthentication(state.remoteAuth); if ($("#ssh-auth-dialog").open) $("#ssh-auth-answer").focus(); }
}
async function cancelAuthentication() {
  if (state.authBusy) return;
  state.authBusy = true; $("#ssh-auth-answer").value = ""; clearTimeout(authTimer);
  try {
    if (state.remoteAuth?.status === "authenticating") {
      renderAuthentication(await api(`/api/remotes/authentication/${encodeURIComponent(state.remoteAuth.session_id)}/cancel`, {}));
    }
    state.remoteAuth = null;
    state.connectionPendingAuth = "";
    $("#ssh-auth-output").textContent = "";
    $("#ssh-auth-dialog").close();
    state.remoteBusy = false; remoteControls();
    await refreshRemoteStatus();
  } catch (error) { showError("#ssh-auth-error", error.message); authTimer = setTimeout(pollAuthentication, 750); }
  finally { state.authBusy = false; if (state.remoteAuth) renderAuthentication(state.remoteAuth); }
}

$("#connection-switch").addEventListener("click", openConnectionPicker);
$("#connection-picker").addEventListener("close", () => { $("#connection-switch").setAttribute("aria-expanded", "false"); $("#connection-switch").focus(); });
$("#connection-picker").addEventListener("keydown", event => { if (event.key === "Escape") { event.preventDefault(); $("#connection-picker").close(); } });
$("#connection-search").addEventListener("input", searchConnections);
$("#connection-primary").addEventListener("click", () => {
  if (state.connectionKey === "local") $("#connection-picker").close();
  else if (state.connectionKey.startsWith("alias:")) void openRemoteSettings("", state.connectionKey.slice(6));
  else void connectFromPicker();
});
$("#connection-details").addEventListener("click", () => { const profile = connectionProfile(); if (profile) void openRemoteSettings(profile.name); });
$("#connection-disconnect").addEventListener("click", disconnectFromPicker);
$("#connection-add-form").addEventListener("submit", event => {
  event.preventDefault();
  const host = $("#connection-new-host").value.trim();
  if (host) void openRemoteSettings("", host);
});
$("#remote-profile").addEventListener("change", () => { fillRemote(state.remoteProfiles.find(profile => profile.name === $("#remote-profile").value)); refreshRemoteStatus(); });
for (const selector of Object.values(remoteFields)) $(selector).addEventListener("input", () => { state.remoteDirty = true; $("#remote-open").hidden = true; $("#remote-open").removeAttribute("href"); remoteControls(); });
$("#remote-form").addEventListener("submit", async event => {
  event.preventDefault(); if (state.remoteBusy) return;
  state.remoteBusy = true; remoteControls(); showError("#remote-error", "");
  try { const profile = readRemote(); await api("/api/remotes", profile); await loadRemotes(profile.name); }
  catch (error) { showError("#remote-error", error.message); }
  finally { state.remoteBusy = false; remoteControls(); }
});
for (const action of ["probe", "install", "connect", "disconnect"]) $(`#remote-${action}`).addEventListener("click", () => remoteAction(action));
$("#remote-sign-in").addEventListener("click", startAuthentication);
$("#ssh-auth-form").addEventListener("submit", answerAuthentication);
$("#ssh-auth-cancel").addEventListener("click", cancelAuthentication);
$("#ssh-auth-dialog").addEventListener("cancel", event => { event.preventDefault(); cancelAuthentication(); });
const setupSections = ["project", "data", "model", "execution", "limits", "advanced", "review"];
function setSetupSection(section) {
  if (!setupSections.includes(section)) return;
  state.setupSection = section;
  $("#setup-more").open = ["data", "model", "limits", "advanced"].includes(section);
  for (const panel of document.querySelectorAll(".setup-section")) panel.hidden = panel.dataset.section !== section;
  for (const button of document.querySelectorAll(".setup-section-button")) {
    if (button.dataset.section === section) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  }
  $("#setup-back").disabled = section === (state.settingsMode ? "model" : "project");
  $("#setup-next").hidden = section === "review";
  $("#setup-next").textContent = section === (state.settingsMode ? "model" : "project") ? (state.settingsMode ? "Project defaults →" : "Choose execution →") : "Review setup →";
  $("#setup-title").focus();
}
function showHome() {
  state.page = "home";
  $("#settings-page").hidden = true;
  $("#empty-workspace").hidden = false;
  $("#research").hidden = true;
  $("#main").focus();
}
function applyTheme(theme) {
  state.theme = theme === "cream" ? "cream" : "charcoal";
  document.documentElement.dataset.theme = state.theme;
  const label = `Switch to ${state.theme === "cream" ? "charcoal dark" : "cream light"} theme`;
  $("#theme-toggle").setAttribute("aria-label", `Switch to ${state.theme === "cream" ? "dark" : "light"} theme`);
  $("#theme-toggle").setAttribute("title", label);
  $("#theme-label").textContent = `Switch to ${state.theme === "cream" ? "dark" : "light"} theme`;
}
async function toggleTheme() {
  $("#theme-toggle").disabled = true;
  try {
    const result = await api("/api/appearance", {theme: state.theme === "charcoal" ? "cream" : "charcoal"});
    applyTheme(result.theme);
  } catch (error) { showError("#global-error", error.message); }
  finally { $("#theme-toggle").disabled = false; }
}
for (const button of document.querySelectorAll(".setup-section-button")) button.addEventListener("click", () => setSetupSection(button.dataset.section));
$("#inspect-project").addEventListener("click", inspectProject);
$("#prepare-proposal").addEventListener("click", prepareProposal);
$("#generate-proposal").addEventListener("click", generateProposal);
$("#apply-proposal").addEventListener("click", applyProposal);
$("#load-proposals").addEventListener("click", loadProposals);
$("#setup-back").addEventListener("click", () => setSetupSection(state.setupSection === "review" ? "execution" : (state.settingsMode ? "model" : "project")));
$("#setup-next").addEventListener("click", () => setSetupSection(state.setupSection === (state.settingsMode ? "model" : "project") ? (state.settingsMode ? "project" : "execution") : "review"));
$("#open-home").addEventListener("click", (event) => { event.preventDefault(); showHome(); });
$("#theme-toggle").addEventListener("click", toggleTheme);
$("#inspect-view").addEventListener("change", () => { if ($("#inspect-view").value) navigate($("#inspect-view").value); });
$("#welcome-runs").addEventListener("click", () => {
  if (state.runs.length) selectRun(state.runs[0].id);
  else toast("No research yet. Create a run or try the offline demo to begin.");
});

$("#open-guide").addEventListener("click", openGuide);
$("#open-settings").addEventListener("click", openModelSettings);
$("#welcome-settings").addEventListener("click", openModelSettings);
$("#guide-configure").addEventListener("click", () => { $("#guide-dialog").close(); openModelSettings(); });
$("#welcome-demo").addEventListener("click", () => { showError("#demo-error", ""); $("#demo-dialog").showModal(); });
$("#save-settings").addEventListener("click", saveSettings);
$("#new-live").addEventListener("click", () => openSetup());
function beginInquiry(event) {
  event?.preventDefault();
  const question = $("#home-question").value.trim();
  if (!question) {
    $("#home-question-status").textContent = "Write the question you want to investigate, then continue to setup.";
    $("#home-question").focus();
    return;
  }
  $("#home-question-status").textContent = "Opening setup with your question. No research has been created.";
  openSetup(undefined, false, question);
}
$("#empty-create").addEventListener("click", beginInquiry);
$("#new-demo").addEventListener("click", () => { showError("#demo-error", ""); $("#demo-dialog").showModal(); $("#demo-run-title").focus(); });
$("#refresh").addEventListener("click", refresh);
$("#reuse-config").addEventListener("click", () => openSetup(state.detail.config));
$("#execute").addEventListener("click", () => runAction("resume"));
$("#step").addEventListener("click", () => runAction("resume", { steps: 1 }));
$("#pause").addEventListener("click", () => runAction("pause"));
$("#cancel-experiment").addEventListener("click", () => runAction("cancel-experiment"));
$("#all-activity").addEventListener("click", () => { state.eventFilter = ""; $("#event-filter").value = ""; navigate("activity"); renderEvents(); });
$("#event-filter").addEventListener("change", () => { state.eventFilter = $("#event-filter").value; state.eventId = null; renderEvents(); });
$("#load-history").addEventListener("click", refresh);
for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => navigate(tab.dataset.tab));
for (const button of document.querySelectorAll(".close-dialog")) button.addEventListener("click", () => { if (button.closest("dialog") === $("#setup-dialog")) $("#setup-api-key").value = ""; button.closest("dialog").close(); });
$("#setup-dialog").addEventListener("close", () => { $("#setup-api-key").value = ""; closeFolderPicker(); state.setupOpening += 1; });
$("#setup-dialog").addEventListener("cancel", () => { $("#setup-api-key").value = ""; });
$("#setup-form").addEventListener("input", (event) => { if (!state.settingsMode && ["setup-model", "setup-base-url", "setup-key-env", "setup-laya-enabled", "setup-laya-url", "setup-laya-model", "setup-laya-cost", "setup-laya-key-env", "setup-json"].includes(event.target.id)) state.runModelOverrides = true; if (event.target.id === "setup-api-key") return; if (event.target.id === "setup-json") state.jsonDirty = true; invalidateSetup(); if (["setup-model", "setup-base-url", "setup-key-env"].includes(event.target.id)) renderModelStatus(null); });
function refreshProjectModels() {
  if (state.settingsMode || state.runModelOverrides) return;
  state.projectModelError = "";
  state.projectModelPending = (async () => {
  const opening = state.setupOpening;
  const project = $("#setup-source").value.trim();
  try {
    const result = await api("/api/settings/models", {scope: project ? "project" : "workspace", project});
    if (opening !== state.setupOpening || project !== $("#setup-source").value.trim() || state.settingsMode || state.runModelOverrides) return;
    const config = readSetup();
    for (const key of [...modelRoutingKeys, "laya"]) config[key] = result.config[key];
    populateSetup(config);
  } catch (error) { if (opening !== state.setupOpening || project !== $("#setup-source").value.trim()) return; state.projectModelError = error.message; showError("#setup-error", error.message); }
  })();
  return state.projectModelPending;
}
$("#setup-source").addEventListener("change", refreshProjectModels);
$("#setup-key-env").addEventListener("input", (event) => {
  const value = event.target.value.trim();
  $("#setup-credential-status").textContent = "Key reference changed. Status has not been checked.";
  if (value && !/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(value)) {
    event.target.value = "";
    showError("#setup-error", "Enter only a variable name, such as XAI_API_KEY. Paste the API key in the field above.");
  } else showError("#setup-error", "");
});

$("#setup-key-env").addEventListener("change", () => { refreshCredentialStatus().catch((error) => { $("#setup-credential-status").textContent = error.message; }); });
$("#setup-google-profile").addEventListener("click", applyGoogleProfile);
$("#setup-credential-target").addEventListener("change", () => {
  $("#setup-api-key").value = "";
  $("#setup-credential-status").textContent = "Checking this key reference…";
  refreshCredentialStatus().catch(error => { $("#setup-credential-status").textContent = error.message; });
});
$("#setup-laya-enabled").addEventListener("change", () => { $("#setup-laya-details").open = $("#setup-laya-enabled").checked; });
$("#setup-laya-key-env").addEventListener("input", event => {
  const value = event.target.value.trim();
  if (value && !/^[A-Za-z_][A-Za-z0-9_]{0,127}$/.test(value)) {
    event.target.value = "";
    showError("#setup-error", "Enter only a variable name, such as LAYA_API_KEY. Save the secret using Key for above.");
  }
  if ($("#setup-credential-target").value === "laya") $("#setup-credential-status").textContent = "Key reference changed. Status has not been checked.";
});
$("#setup-laya-key-env").addEventListener("change", () => {
  if ($("#setup-credential-target").value === "laya") refreshCredentialStatus().catch(error => { $("#setup-credential-status").textContent = error.message; });
});
$("#setup-save-key").addEventListener("click", saveApiKey);
$("#setup-clear-key").addEventListener("click", clearApiKey);
$("#setup-form").addEventListener("change", invalidateSetup);
$("#setup-backend").addEventListener("change", showBackendFields);
$("#validate-setup").addEventListener("click", validateSetup);
$("#setup-form").addEventListener("submit", createLive);
$("#apply-config-json").addEventListener("click", applyAdvanced);
$("#refresh-config-json").addEventListener("click", () => {
  try {
    if (state.jsonDirty) throw new Error("Apply the edited JSON first; refreshing would discard those edits.");
    $("#setup-json").value = json(readSetup());
    showError("#setup-error", "");
  } catch (error) { showError("#setup-error", error.message); }
});
$("#import-config").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 1024 * 1024) { showError("#setup-error", "Configuration file exceeds the 1 MiB import limit."); return; }
  $("#setup-json").value = await file.text();
  state.jsonDirty = true;
  invalidateSetup();
  applyAdvanced();
  event.target.value = "";
});
$("#demo-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#create-demo").disabled = true;
  showError("#demo-error", "");
  try {
    const { run } = await api("/api/runs", { title: $("#demo-run-title").value, objective: "Exercise the complete workflow with scripted agents and a deterministic synthetic regression benchmark. This is an orchestration demonstration, not independent scientific validation.", demo: true });
    $("#demo-dialog").close();
    await selectRun(run.id);
    await refresh();
    toast("Offline demo created. Start it explicitly to execute the workflow.");
  } catch (error) { showError("#demo-error", error.message); }
  finally { $("#create-demo").disabled = false; }
});
$("#intervene").addEventListener("click", () => { showError("#intervene-error", ""); $("#intervene-dialog").showModal(); $("#intervention-note").focus(); });
$("#intervene-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter; button.disabled = true;
  try {
    const body = { note: $("#intervention-note").value };
    if ($("#intervention-stage").value) body.stage = $("#intervention-stage").value;
    await api(`/api/runs/${encodeURIComponent(state.id)}/intervene`, body);
    $("#intervene-dialog").close();
    $("#intervention-note").value = "";
    $("#intervention-stage").value = "";
    await refresh();
    toast("Intervention recorded. Resume explicitly to continue.");
  } catch (error) { showError("#intervene-error", error.message); }
  finally { button.disabled = false; }
});
$("#edit-budget").addEventListener("click", () => {
  const budget = state.detail.config.budget;
  $("#budget-usd").value = budget.usd;
  $("#budget-calls").value = budget.max_calls;
  $("#budget-experiments").value = budget.max_experiments;
  $("#budget-wall").value = budget.wall_seconds;
  showError("#budget-error", "");
  $("#budget-dialog").showModal();
  $("#budget-usd").focus();
});
$("#budget-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter; button.disabled = true;
  try {
    await api(`/api/runs/${encodeURIComponent(state.id)}/budget`, { usd: Number($("#budget-usd").value), max_calls: Number($("#budget-calls").value), max_experiments: Number($("#budget-experiments").value), wall_seconds: Number($("#budget-wall").value) });
    $("#budget-dialog").close();
    await refresh();
    toast("Budget saved. Execution has not been restarted.");
  } catch (error) { showError("#budget-error", error.message); }
  finally { button.disabled = false; }
});
function takeRemoteToken() {
  const fragment = new URLSearchParams(location.hash.slice(1));
  const supplied = fragment.has("remote-token");
  let token = fragment.get("remote-token") || "";
  if (supplied) {
    fragment.delete("remote-token");
    history.replaceState(null, "", `${location.pathname}${location.search}${fragment.size ? `#${fragment}` : ""}`);
  } else {
    try { token = sessionStorage.getItem("autoresearch.remoteToken") || ""; } catch { /* Storage can be disabled. */ }
  }
  if (token && (!/^[A-Za-z0-9_-]{16,512}$/.test(token) || !["127.0.0.1", "localhost"].includes(location.hostname))) throw new Error("Invalid remote console link");
  return token;
}
async function boot() {
  try {
    const remoteToken = takeRemoteToken();
    const response = await fetch("/api/bootstrap", { credentials: "same-origin", cache: "no-store", headers: remoteToken ? { Authorization: `Bearer ${remoteToken}` } : {} });
    if (!response.ok) {
      try { sessionStorage.removeItem("autoresearch.remoteToken"); } catch { /* Storage can be disabled. */ }
      throw new Error("Could not establish a console session. For a remote console, reconnect using SSH connections on your local dashboard.");
    }
    const bootstrap = await response.json();
    state.token = bootstrap.token;
    state.managedRemote = !!bootstrap.managed_remote;
    state.remoteLabel = bootstrap.remote_label || (state.managedRemote ? "remote host" : "localhost");
    if (state.managedRemote) state.connectionKey = "remote";
    $("#connection-place").textContent = state.managedRemote ? `SSH · ${state.remoteLabel}` : "LOCAL WORKSPACE";
    try {
      if (state.managedRemote) sessionStorage.setItem("autoresearch.remoteToken", state.token);
      else sessionStorage.removeItem("autoresearch.remoteToken");
    } catch { /* The current page works without reload persistence. */ }
    state.stages = bootstrap.stages;
    applyWorkflow(bootstrap.workflow);
    applyTheme(bootstrap.appearance?.theme || "charcoal");
    for (const stage of state.stages) {
      for (const selector of ["#event-filter", "#intervention-stage"]) {
        if (selector === "#intervention-stage" && stage === "complete") continue;
        const option = element("option", "", stageName(stage)); option.value = stage; $(selector).append(option);
      }
    }
    await refresh();
    setInterval(() => { if (!document.hidden) { refresh(); refreshRemoteStatus(); } }, 2500);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  } catch (error) { showError("#global-error", error.message); }
}
boot();
