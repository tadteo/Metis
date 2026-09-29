"use strict";

// Research text is always rendered through textContent, never interpreted as HTML.
const $ = (selector) => document.querySelector(selector);
const state = {
  page: "research", theme: "charcoal", setupSection: "project", token: "", stages: [], runs: [], id: null, detail: null, events: [], behavior: null, behaviorKey: "",
  tab: "overview", ideaId: null, experimentId: null, eventId: null,
  eventFilter: "", revision: "", refreshing: false, historyRemaining: false,
  serverConfig: null, setupBase: null, setupRevision: 0, settingsRevision: 0, settingsMode: false,
  validatedKey: null, jsonDirty: false, setupBusy: false, connectionError: false,
  managedRemote: false, remoteLabel: "localhost", remoteProfiles: [], remoteName: "",
  remoteBusy: false, remoteDirty: false, remoteAuth: null, authBusy: false,
};
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
  const [detail, history] = await Promise.all([
    api(`/api/runs/${encodeURIComponent(id)}`),
    api(`/api/runs/${encodeURIComponent(id)}/events?after=${after}`),
  ]);
  if (state.id !== id) return;
  state.detail = detail;
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
    if (!state.id && state.runs.length) await selectRun(state.runs[0].id);
    else if (state.id) await refreshDetail();
    else { $("#empty-workspace").hidden = false; $("#research").hidden = true; }
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
function renderDetail() {
  const { run, config, usage, working, paused, worker_error: workerError } = state.detail;
  const demo = config.mode === "demo";
  $("#empty-workspace").hidden = state.page !== "home";
  $("#research").hidden = state.page === "home";
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
  $("#edit-budget").disabled = working;
  $("#cancel-experiment").hidden = !run.pending_job_id;
  $("#cancel-experiment").disabled = working;
  let message = workerError || run.error || "";
  if (!message && run.pending_job_id) message = `Slurm job ${run.pending_job_id} is pending.${working ? " Monitoring scheduler status." : " Resume to monitor it, or cancel the pending experiment."}`;
  if (!message && run.stage === "complete" && run.outcome) message = human(run.outcome);
  if (!message && demo) message = "Demonstration results are synthetic. Scripted review scores and decisions are not independent scientific validation.";
  $("#run-alert").textContent = message;
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
    else if (event.kind === "agent_completed") active.delete(key);
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
  } else current.append(element("p", "", working ? "The worker is executing this stage. Agent and experiment events appear below as they are recorded." : run.stage === "complete" ? "This run has finished. Inspect its evidence, manuscript, and recorded reviews." : "The run is stopped. Start it or execute one checkpoint using the controls above."));
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
    ["Project & evidence", [["Source directory", config.project.source_dir || "Run source snapshot"], ["Baseline arguments", json(config.project.baseline_argv)], ["Evaluator arguments", json(config.project.evaluator_argv)], ["Protected paths", config.project.protected_paths.join(", ") || "None"], ["Primary metric", `${config.project.primary_metric} (${config.project.metrics[config.project.primary_metric]})`], ["Published SOTA", Object.entries(config.project.sota).map(([key, value]) => `${key}: ${value}`).join("; ") || "Not configured"], ["Seeds", config.project.seeds.join(", ")]]],
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
      const section = check.name.startsWith("provider") ? "model" : ["source", "baseline", "evaluator", "protected-evaluator", "metrics"].includes(check.name) ? "project" : ["datasets", "protocol"].includes(check.name) ? "data" : /docker|execution|dependencies/.test(check.name) ? "execution" : "advanced";
      const fix = element("button", "text-button", `Edit ${section} →`);
      fix.type = "button";
      fix.addEventListener("click", () => setSetupSection(section));
      description.append(fix);
    }
    row.append(element("span", "check-status", check.status), description);
    root.append(row);
  }
}
function showReadiness(readiness) {
  const root = $("#setup-readiness");
  root.hidden = false;
  root.replaceChildren(element("h3", "", readiness.ready ? "Setup checks passed" : "Resolve these setup checks"));
  appendChecks(root, readiness, true);
}
function mergeConfig(base, extra) {
  const output = clone(base);
  for (const [key, value] of Object.entries(extra)) {
    if (["__proto__", "prototype", "constructor"].includes(key)) throw new Error("Invalid configuration key.");
    output[key] = value && typeof value === "object" && !Array.isArray(value) && output[key] && typeof output[key] === "object" && !Array.isArray(output[key]) ? mergeConfig(output[key], value) : clone(value);
  }
  return output;
}
async function openSetup(config, settingsMode = false) {
  state.setupRevision += 1;
  state.settingsMode = settingsMode;
  $("#setup-title").textContent = settingsMode ? "Workspace settings" : "Configure live research";
  $("#setup-description").textContent = settingsMode ? "Private defaults for future runs. Save incomplete setup and return later. Existing runs retain their recorded configuration." : "Check the project and execution environment, then create an idle run. Start it explicitly when ready.";
  $("#run-identity-fields").hidden = settingsMode;
  $("#setup-run-title").required = !settingsMode;
  $("#setup-objective").required = !settingsMode;
  $("#save-settings").hidden = !settingsMode;
  $("#save-settings").disabled = true;
  $("#create-live").hidden = settingsMode;
  setSetupSection("project");
  $("#setup-dialog").showModal();
  $("#setup-loading").hidden = false;
  showError("#setup-error", "");
  $("#setup-readiness").hidden = true;
  $("#create-live").disabled = true;
  $("#validate-setup").disabled = true;
  state.setupBase = null;
  state.validatedKey = null;
  try {
    const defaults = await api("/api/config");
    state.serverConfig = defaults.config;
    state.settingsRevision = defaults.revision;
    populateSetup(config ? mergeConfig(defaults.config, config) : defaults.config);
    $("#setup-run-title").value = "";
    $("#setup-objective").value = "";
    if (defaults.readiness && !config) showReadiness(defaults.readiness);
    if (settingsMode) $("#validation-state").textContent = `Loaded ${defaults.source || "settings"}. Save progress or check prerequisites.`;
    $(settingsMode ? "#setup-source" : "#setup-run-title").focus();
  } catch (error) { showError("#setup-error", error.message); }
  finally { $("#setup-loading").hidden = true; $("#validate-setup").disabled = !state.setupBase; $("#save-settings").disabled = !state.setupBase; }
}
function populateSetup(config) {
  state.setupBase = clone(config);
  state.setupBase.mode = "live";
  const project = state.setupBase.project;
  const provider = state.setupBase.provider;
  const execution = state.setupBase.execution;
  $("#setup-source").value = project.source_dir || "";
  $("#setup-baseline").value = json(project.baseline_argv || []);
  $("#setup-evaluator").value = json(project.evaluator_argv || []);
  $("#setup-protected").value = json(project.protected_paths || []);
  $("#setup-metric").value = project.primary_metric;
  $("#setup-direction").value = project.metrics[project.primary_metric] || "max";
  $("#setup-sota").value = project.sota[project.primary_metric] ?? "";
  $("#setup-budget").value = state.setupBase.budget.usd;
  $("#setup-model").value = provider.model;
  $("#setup-key-env").value = provider.api_key_env;
  $("#setup-base-url").value = provider.base_url;
  $("#setup-backend").value = execution.backend;
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
  const previousMetric = config.project.primary_metric;
  const metric = $("#setup-metric").value.trim();
  if (!metric) throw new Error("A primary metric name is required.");
  if (metric !== previousMetric) {
    delete config.project.metrics[previousMetric];
    delete config.project.sota[previousMetric];
    delete config.project.baseline_expected[previousMetric];
    if (config.project.metric_units) delete config.project.metric_units[previousMetric];
  }
  config.project.source_dir = $("#setup-source").value.trim();
  config.project.baseline_argv = stringArray("#setup-baseline", "Baseline command");
  config.project.evaluator_argv = stringArray("#setup-evaluator", "Evaluator command");
  config.project.protected_paths = stringArray("#setup-protected", "Protected paths");
  config.project.primary_metric = metric;
  config.project.metrics[metric] = $("#setup-direction").value;
  if ($("#setup-sota").value === "") delete config.project.sota[metric];
  else config.project.sota[metric] = Number($("#setup-sota").value);
  config.budget.usd = Number($("#setup-budget").value);
  config.provider.model = $("#setup-model").value.trim();
  config.provider.base_url = $("#setup-base-url").value.trim();
  config.provider.api_key_env = $("#setup-key-env").value.trim();
  if (/^(sk-|xai-|sk_or_|ghp_)/i.test(config.provider.api_key_env)) throw new Error("Enter an environment variable name, not an API key. Remove the credential from this form and set it in the server environment.");
  config.execution.backend = $("#setup-backend").value;
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
  return config;
}
async function saveSettings() {
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
async function openGuide() {
  $("#guide-dialog").showModal();
  $("#welcome-guide-text").textContent = "Loading getting started guide…";
  try { $("#welcome-guide-text").textContent = (await api("/api/config")).guide; }
  catch (error) { $("#welcome-guide-text").textContent = error.message; }
}
async function validateSetup() {
  showError("#setup-error", "");

  let config;
  try { config = readSetup(); }
  catch (error) { showError("#setup-error", error.message); return; }
  const revision = state.setupRevision;
  state.setupBusy = true;
  $("#validate-setup").disabled = true;
  $("#create-live").disabled = true;
  $("#validation-state").textContent = "Checking paths, credentials, evaluator, and execution backend…";
  try {
    const readiness = await api("/api/preflight", { config });
    if (revision !== state.setupRevision) { $("#validation-state").textContent = "Setup changed while validation was running. Validate again."; return; }
    showReadiness(readiness);
    setSetupSection("review");
    state.validatedKey = readiness.ready ? JSON.stringify(config) : null;
    $("#create-live").disabled = !readiness.ready;
    $("#validation-state").textContent = readiness.ready ? "Validated. Creating the run will not start execution." : "Resolve the checks above, then validate again.";
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
  for (const selector of ["#setup-run-title", "#setup-objective"]) {
    if (!$(selector).checkValidity()) {
      setSetupSection("project");
      $(selector).reportValidity();
      return;
    }
  }
  showError("#setup-error", "");
  let config;
  try {
    config = readSetup();
    if (state.validatedKey !== JSON.stringify(config)) throw new Error("Validate the current setup before creating a run.");
  } catch (error) { showError("#setup-error", error.message); return; }
  $("#create-live").disabled = true;
  try {
    const { run } = await api("/api/runs", { title: $("#setup-run-title").value, objective: $("#setup-objective").value, demo: false, config });
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
  finally { state.authBusy = false; renderAuthentication(state.remoteAuth); $("#ssh-auth-answer").focus(); }
}
async function cancelAuthentication() {
  if (state.authBusy) return;
  state.authBusy = true; $("#ssh-auth-answer").value = ""; clearTimeout(authTimer);
  try {
    if (state.remoteAuth?.status === "authenticating") {
      renderAuthentication(await api(`/api/remotes/authentication/${encodeURIComponent(state.remoteAuth.session_id)}/cancel`, {}));
    }
    state.remoteAuth = null;
    $("#ssh-auth-output").textContent = "";
    $("#ssh-auth-dialog").close();
    state.remoteBusy = false; remoteControls();
    await refreshRemoteStatus();
  } catch (error) { showError("#ssh-auth-error", error.message); authTimer = setTimeout(pollAuthentication, 750); }
  finally { state.authBusy = false; if (state.remoteAuth) renderAuthentication(state.remoteAuth); }
}

$("#manage-remotes").addEventListener("click", async () => {
  if (state.managedRemote) return;
  $("#remote-dialog").showModal(); showError("#remote-error", "");
  state.remoteBusy = true; remoteControls();
  try { await loadRemotes(); }
  catch (error) { showError("#remote-error", error.message); }
  finally { state.remoteBusy = false; remoteControls(); }
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
  for (const panel of document.querySelectorAll(".setup-section")) panel.hidden = panel.dataset.section !== section;
  for (const button of document.querySelectorAll(".setup-section-button")) {
    if (button.dataset.section === section) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  }
  $("#setup-back").disabled = section === "project";
  $("#setup-next").hidden = section === "review";
}
function showHome() {
  state.page = "home";
  $("#empty-workspace").hidden = false;
  $("#research").hidden = true;
  $("#main").focus();
}
function applyTheme(theme) {
  state.theme = theme === "cream" ? "cream" : "charcoal";
  document.documentElement.dataset.theme = state.theme;
  $("#theme-toggle").textContent = state.theme === "cream" ? "Charcoal / dark" : "Cream / light";
  $("#theme-toggle").setAttribute("aria-label", `Switch to ${state.theme === "cream" ? "charcoal dark" : "cream light"} theme`);
}
async function toggleTheme() {
  $("#theme-toggle").disabled = true;
  try {
    const result = await api("/api/appearance", {theme: state.theme === "charcoal" ? "cream" : "charcoal"});
    applyTheme(result.theme);
  } catch (error) { showError("#global-error", error.message); }
  finally { $("#theme-toggle").disabled = false; }
}
function commandItems() {
  const items = [
    ["Home", showHome], ["New research", () => openSetup()],
    ["Settings", () => openSetup(undefined, true)], ["Getting started", openGuide],
    ["Switch charcoal / cream", toggleTheme],
    ["Offline demo", () => $("#demo-dialog").showModal()],
  ];
  if (state.id) for (const view of ["overview", "experiments", "activity", "manuscript", "ideas", "system", "config", "fidelity"]) {
    items.push([`Research / ${human(view)}`, () => { state.page = "research"; $("#research").hidden = false; $("#empty-workspace").hidden = true; navigate(view); }]);
  }
  return items;
}
function renderCommands() {
  const query = $("#command-search").value.trim().toLowerCase();
  const root = $("#command-results");
  root.replaceChildren();
  for (const [label, action] of commandItems()) {
    if (!label.toLowerCase().includes(query)) continue;
    const button = element("button", "", label);
    button.type = "button";
    button.addEventListener("click", () => { $("#commands-dialog").close(); action(); });
    root.append(button);
  }
  if (!root.children.length) root.append(empty("No matching view. Try Settings or Experiments."));
}
function openCommands() {
  if (document.querySelector("dialog[open]")) return;
  $("#command-search").value = "";
  renderCommands();
  $("#commands-dialog").showModal();
  $("#command-search").focus();
}
for (const button of document.querySelectorAll(".setup-section-button")) button.addEventListener("click", () => setSetupSection(button.dataset.section));
$("#setup-back").addEventListener("click", () => setSetupSection(setupSections[setupSections.indexOf(state.setupSection) - 1]));
$("#setup-next").addEventListener("click", () => setSetupSection(setupSections[setupSections.indexOf(state.setupSection) + 1]));
$("#open-home").addEventListener("click", showHome);
$("#theme-toggle").addEventListener("click", toggleTheme);
$("#inspect-view").addEventListener("change", () => { if ($("#inspect-view").value) navigate($("#inspect-view").value); });
$("#open-commands").addEventListener("click", openCommands);
$("#command-search").addEventListener("input", renderCommands);
$("#command-search").addEventListener("keydown", event => {
  if (event.key === "ArrowDown") { event.preventDefault(); $("#command-results").querySelector("button")?.focus(); }
  if (event.key === "Enter") { event.preventDefault(); $("#command-results").querySelector("button")?.click(); }
});
document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openCommands(); }
});
$("#welcome-runs").addEventListener("click", () => {
  if (state.runs.length) selectRun(state.runs[0].id);
  else toast("No research yet. Create a run or try the offline demo to begin.");
});

$("#open-guide").addEventListener("click", openGuide);
$("#welcome-guide").addEventListener("click", openGuide);
$("#open-settings").addEventListener("click", () => openSetup(undefined, true));
$("#welcome-settings").addEventListener("click", () => openSetup(undefined, true));
$("#guide-configure").addEventListener("click", () => { $("#guide-dialog").close(); openSetup(undefined, true); });
$("#welcome-demo").addEventListener("click", () => { showError("#demo-error", ""); $("#demo-dialog").showModal(); });
$("#save-settings").addEventListener("click", saveSettings);
$("#new-live").addEventListener("click", () => openSetup());
$("#empty-create").addEventListener("click", () => openSetup());
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
for (const button of document.querySelectorAll(".close-dialog")) button.addEventListener("click", () => button.closest("dialog").close());
$("#setup-form").addEventListener("input", (event) => { if (event.target.id === "setup-json") state.jsonDirty = true; invalidateSetup(); });
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
    $("#console-location").textContent = state.managedRemote ? `REMOTE · ${state.remoteLabel}` : "LOCAL CONSOLE";
    $("#manage-remotes").hidden = state.managedRemote;
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
