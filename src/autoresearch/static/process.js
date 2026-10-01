"use strict";

// Read-only views of durable execution evidence. Research text is never HTML.
const ResearchProcess = (() => {
  const human = value => String(value ?? "").replaceAll("_", " ");
  const time = value => value ? Date.parse(value) : NaN;
  const duration = seconds => {
    if (seconds == null || !Number.isFinite(seconds)) return "—";
    if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
    if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
    return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  };
  const cost = value => value == null ? "—" : new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", maximumFractionDigits: value > 0 && value < .01 ? 4 : 2}).format(value);
  const el = (tag, name = "", text) => {
    const node = document.createElement(tag);
    node.className = name;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  function button(text, action, name = "text-button", key) {
    const node = el("button", name, text);
    node.type = "button";
    if (key) node.dataset.processKey = key;
    node.addEventListener("click", action);
    return node;
  }
  function runStatus(data, detail) {
    if (detail.worker_error) return "error";
    return data.rows.find(r => r.kind === "run")?.status || detail.run.status || "unknown";
  }
  function aggregate(rows) {
    return {
      duration_seconds: rows.length && rows.every(r => r.duration_seconds != null) ? rows.reduce((n, r) => n + r.duration_seconds, 0) : null,
      cost_usd: rows.some(r => r.cost_usd != null) ? rows.reduce((n, r) => n + (r.cost_usd || 0), 0) : null,
      estimated: rows.some(r => r.estimated),
    };
  }
  function phaseEntries(workflow) {
    // Archived JSON object keys are sorted; use declared edges, never key order.
    const nodes = workflow.nodes || {}, ordered = [], seen = new Set();
    function visit(id) {
      if (seen.has(id) || !nodes[id]) return;
      seen.add(id); ordered.push([id, nodes[id]]);
      for (const edge of nodes[id].transitions || []) visit(edge.target);
    }
    visit(workflow.initial);
    for (const id of Object.keys(nodes)) visit(id);
    const keys = ["preparation", "ideation", "experimentation", "ablation", "manuscript", "integrity"];
    for (const [,node] of ordered) if (node.phase !== "complete" && !keys.includes(node.phase)) keys.push(node.phase);
    return keys.map(phase => [phase, ordered.filter(([,node]) => node.phase === phase)]).filter(([,stages]) => stages.length);
  }
  function phaseFor(workflow, stage) { return workflow?.nodes?.[stage]?.phase || null; }
  function currentPhase(data, workflow) {
    const phase = phaseFor(workflow, data.current_stage);
    if (phase !== "complete") return phase;
    // A terminal checkpoint says nothing about which scientific phases succeeded.
    const visits = data.rows.filter(r => r.kind === "stage_visit" && phaseFor(workflow, r.stage) !== "complete");
    return phaseFor(workflow, visits.at(-1)?.stage);
  }
  function timeline(rows, captured) {
    const starts = rows.map(r => time(r.started_at)).filter(Number.isFinite);
    const ends = rows.flatMap(r => [time(r.ended_at), Number.isFinite(time(r.started_at)) && r.duration_seconds != null ? time(r.started_at) + r.duration_seconds * 1000 : NaN]).filter(Number.isFinite);
    const start = starts.length ? Math.min(...starts) : null;
    const end = ends.length ? Math.max(...ends) : time(captured);
    return {start, seconds: start === null || !Number.isFinite(end) ? 0 : Math.max(.001, (end - start) / 1000)};
  }
  function visibleRows(rows, expanded) {
    const children = new Map();
    for (const row of rows) {
      const parent = row.parent_id || null;
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent).push(row);
    }
    const result = [], seen = new Set();
    function walk(parent, depth) {
      for (const row of children.get(parent) || []) {
        if (seen.has(row.id)) continue;
        seen.add(row.id);
        result.push({row, depth, hasChildren: children.has(row.id)});
        if (expanded.has(row.id)) walk(row.id, depth + 1);
      }
    }
    walk(null, 0);
    return result;
  }
  let scenePromise;
  function scene() {
    if (!scenePromise) scenePromise = fetch("/temple.json", {credentials: "same-origin"}).then(r => { if (!r.ok) throw new Error("Temple unavailable"); return r.json(); });
    return scenePromise;
  }
  class View {
    constructor(graph, traces, navigate) {
      this.graph = graph; this.traces = traces; this.navigate = navigate;
      this.phase = null; this.stage = null; this.selected = null; this.runId = null;
      this.expanded = new Set(); this.follow = true; this.mode = "tasks";
      this.frame = null; this.templeKey = null;
      this.reduced = matchMedia("(prefers-reduced-motion: reduce)");
      this.reduced.addEventListener("change", () => this.drawTemple());
      this.resize = new ResizeObserver(() => this.drawTemple()); this.resize.observe(graph);
      this.theme = new MutationObserver(() => this.drawTemple());
      this.theme.observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
      document.addEventListener("visibilitychange", () => this.drawTemple());
    }
    update(data, workflow, detail) {
      this.detail = detail;
      if (detail.run.id !== this.runId) {
        this.runId = detail.run.id; this.phase = null; this.stage = null;
        this.selected = null; this.expanded = new Set(); this.follow = true; this.signature = null;
      }
      this.data = data; this.workflow = workflow || {nodes: {}};
      if (!data || data.error) {
        this.signature = null;
        if (this.frame !== null) cancelAnimationFrame(this.frame);
        this.frame = null;
        this.graph.replaceChildren(el("p", "panel-note", `Research process unavailable. ${data?.error || "Waiting for execution records."}`));
        this.traces.replaceChildren(el("p", "panel-note", "Execution records could not be loaded. Activity & traces remains available."));
        return;
      }
      if (this.follow) this.phase = currentPhase(data, this.workflow);
      if (!this.expanded.size) {
        for (const r of data.rows) if (r.kind === "run" || (r.kind === "stage_visit" && r.stage === data.current_stage)) this.expanded.add(r.id);
      }
      // Preserve selected records, focus, expanded details and scroll while polling.
      const signature = JSON.stringify([data.rows, data.notes, workflow, detail.working, detail.paused, detail.worker_error, this.phase]);
      if (signature === this.signature) return;
      this.signature = signature;
      this.render();
    }
    render() {
      const focus = document.activeElement?.dataset.processKey;
      const scroll = [...this.graph.querySelectorAll(".rg-scroll,.rg-phases"), ...this.traces.querySelectorAll(".at-scroll")].map(n => [n.className, n.scrollLeft, n.scrollTop]);
      const opened = [...this.graph.querySelectorAll("details[open]"), ...this.traces.querySelectorAll("details[open]")].map(n => n.dataset.processKey);
      this.renderGraph(); this.renderTraces();
      for (const [name, left, top] of scroll) for (const n of [...this.graph.querySelectorAll(`.${name}`), ...this.traces.querySelectorAll(`.${name}`)]) { n.scrollLeft = left; n.scrollTop = top; }
      for (const n of [...this.graph.querySelectorAll("details"), ...this.traces.querySelectorAll("details")]) if (opened.includes(n.dataset.processKey)) n.open = true;
      if (focus) this.focus(focus, true);
      this.drawTemple();
    }
    focus(key, preventScroll = false) {
      [...this.graph.querySelectorAll("[data-process-key]"), ...this.traces.querySelectorAll("[data-process-key]")].find(n => n.dataset.processKey === key)?.focus({preventScroll});
    }
    phaseEntries() { return phaseEntries(this.workflow); }
    selectPhase(phase) { this.phase = phase; this.follow = false; this.stage = null; this.render(); this.focus(`phase:${phase}`); }
    renderGraph() {
      const root = this.graph, data = this.data, phases = this.phaseEntries(), live = currentPhase(data, this.workflow);
      root.replaceChildren();
      const heading = el("header", "rg-heading"), title = el("div");
      title.append(el("h2", "", "Research process"), el("p", "", "Tasks, agents and their handoffs"));
      const actions = el("div", "rg-heading-actions");
      actions.append(button("Follow current work ↗", () => {this.follow = true; this.phase = live; this.stage = null; this.render(); this.focus("follow");}, "text-button", "follow"));
      heading.append(title, actions); root.append(heading);
      if (!phases.length) { root.append(el("p", "panel-note", "The archived workflow is unavailable. Inspect recorded work in Agent traces.")); return; }
      const layout = el("div", "rg-layout"), main = el("div", "rg-main"), nav = el("nav", "rg-phases"); nav.setAttribute("aria-label", "Research phases");
      for (const [phase, stages] of phases) {
        const visited = data.rows.some(r => r.kind === "stage_visit" && stages.some(([s]) => s === r.stage));
        const b = button("", () => this.selectPhase(phase), `rg-phase${phase === this.phase ? " active" : ""}${phase === live ? " live" : ""}`, `phase:${phase}`);
        b.setAttribute("aria-pressed", String(phase === this.phase));
        b.append(el("span", "dot", phase === live ? "●" : visited ? "◌" : "○"), document.createTextNode(human(phase)), el("small", "", phase === live ? data.current_stage === "complete" ? "LAST PHASE" : "CURRENT" : visited ? "VISITED" : "NOT VISITED"));
        nav.append(b);
      }
      main.append(nav);
      const context = el("div", "rg-context");
      const picker = el("select"); picker.setAttribute("aria-label", "Research graph view"); picker.dataset.processKey = "mode";
      for (const [value, label] of [["tasks", "Grouped tasks"], ["attempts", "Recorded attempts"]]) { const o = el("option", "", label); o.value = value; picker.append(o); }
      picker.value = this.mode; picker.addEventListener("change", () => {this.mode = picker.value; this.render(); this.focus("mode");});
      context.append(el("span", "", `${human(this.phase || "Unknown phase")}${this.follow ? "" : " · inspecting"}`), picker); main.append(context);
      const stages = phases.find(([phase]) => phase === this.phase)?.[1] || [];
      const scroll = el("div", "rg-scroll"); scroll.tabIndex = 0; scroll.setAttribute("aria-label", "Scrollable task graph"); scroll.dataset.processKey = "graph-scroll";
      if (this.mode === "attempts") {
        const attempts = data.rows.filter(r => r.kind === "stage_visit" && stages.some(([s]) => s === r.stage));
        const list = el("div", "rg-attempts");
        for (const r of attempts) {
          const b = button("", () => this.openTrace(r.id), "rg-attempt", `attempt:${r.id}`);
          b.append(el("strong", "", this.labelFor(r)), el("small", "", human(r.status)), el("span", "rg-measure", `${duration(r.duration_seconds)} · ${cost(r.cost_usd)}${r.estimated ? " estimated" : ""}`)); list.append(b);
        }
        if (!attempts.length) list.append(el("p", "panel-note", "No attempts recorded in this phase."));
        scroll.append(list);
      } else {
        const canvas = el("div", "rg-graph"); canvas.style.height = `${Math.ceil(stages.length / 3) * 156 + 30}px`;
        const positions = new Map(stages.map(([id], i) => [id, {x: 20 + (i % 3) * 254, y: 20 + Math.floor(i / 3) * 156}]));
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg"); svg.setAttribute("aria-hidden", "true");
        const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs"), marker = document.createElementNS("http://www.w3.org/2000/svg", "marker"), arrow = document.createElementNS("http://www.w3.org/2000/svg", "path");
        for (const [key, value] of Object.entries({id:"process-arrow",markerWidth:"7",markerHeight:"7",refX:"6",refY:"3",orient:"auto"})) marker.setAttribute(key,value);
        arrow.setAttribute("d","M0 0 L6 3 L0 6"); arrow.setAttribute("fill","var(--muted)"); marker.append(arrow); defs.append(marker); svg.append(defs);
        for (const [id, spec] of stages) {
          const a = positions.get(id);
          for (const edge of spec.transitions || []) {
            const b = positions.get(edge.target); if (!b) continue;
            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
            const returning = b.y < a.y || (b.y === a.y && b.x <= a.x);
            const d = id === edge.target ? `M${a.x+50} ${a.y} v-12 h90 v12` : a.y === b.y && !returning ? `M${a.x+200} ${a.y+60} H${b.x}` : `M${a.x+160} ${a.y+122} V${a.y+140} H${b.x+30} V${b.y}`;
            path.setAttribute("d", d); path.setAttribute("marker-end", "url(#process-arrow)"); path.setAttribute("class", `rg-edge${returning ? " return" : ""}`);
            svg.append(path);
          }
        }
        canvas.append(svg);
        for (const [stage, spec] of stages) {
          const visits = data.rows.filter(r => r.kind === "stage_visit" && r.stage === stage), metric = aggregate(visits);
          const current = stage === data.current_stage;
          const status = current ? runStatus(data, this.detail) : visits.length ? "visited" : "waiting";
          const b = button("", () => {this.stage = stage; this.render(); this.focus(`task:${stage}`);}, `rg-node ${status}`, `task:${stage}`);
          const p = positions.get(stage); b.style.left = `${p.x}px`; b.style.top = `${p.y}px`; b.setAttribute("aria-pressed", String(this.stage === stage));
          b.append(el("strong", "", spec.label || human(stage)), el("small", "", (spec.agents || []).map(human).join(" · ") || "Workflow checkpoint"), el("span", "rg-node-status", status === "waiting" ? "Not visited" : current ? human(status) : `${visits.length} recorded visit${visits.length === 1 ? "" : "s"}`), el("span", "rg-measure", `${duration(metric.duration_seconds)} · ${cost(metric.cost_usd)}${metric.estimated ? " est." : ""}`));
          canvas.append(b);
        }
        scroll.append(canvas);
      }
      main.append(scroll); layout.append(main);
      const temple = el("aside", "rg-temple"); temple.setAttribute("aria-label", "Overall research summary");
      const picture = el("canvas"); picture.setAttribute("aria-hidden", "true");
      temple.append(picture, el("strong", "", human(live || "Unknown phase")), el("small", "", data.current_stage === "complete" ? "Last recorded phase" : "Overall phase"), el("p", "", human(runStatus(data, this.detail))));
      layout.append(temple); root.append(layout);
      root.append(el("footer", "rg-footer", "Recorded stage time · attributed model cost. Visits are not acceptance. Select a task to inspect attempts and conditional paths."));
      if (this.stage) this.renderTask();
    }
    labelFor(row) {
      if (row.kind !== "stage_visit") return row.label;
      const visits = this.data.rows.filter(r => r.kind === "stage_visit" && r.stage === row.stage);
      return `${this.workflow.nodes?.[row.stage]?.label || row.label} · visit ${visits.findIndex(r => r.id === row.id) + 1}`;
    }
    renderTask() {
      const spec = this.workflow.nodes?.[this.stage]; if (!spec) return;
      const inspector = el("section", "rg-inspector"), top = el("div", "rg-inspector-top");
      top.append(el("h3", "", spec.label), button("Close details ×", () => {const stage = this.stage; this.stage = null; this.render(); this.focus(`task:${stage}`);}, "text-button", "task-close")); inspector.append(top);
      inspector.append(el("p", "", `Agents: ${(spec.agents || []).map(human).join(" · ") || "Workflow checkpoint"}`));
      const visits = this.data.rows.filter(r => r.kind === "stage_visit" && r.stage === this.stage);
      if (!visits.length) inspector.append(el("p", "", "No recorded execution. This checkpoint may be conditional."));
      for (const row of visits) inspector.append(button(`${this.labelFor(row)} · ${human(row.status)} · ${duration(row.duration_seconds)} · ${cost(row.cost_usd)} →`, () => this.openTrace(row.id), "activity-row", `visit:${row.id}`));
      inspector.append(el("h3", "", "Possible next steps"));
      for (const edge of spec.transitions || []) inspector.append(el("p", "", `${this.workflow.nodes?.[edge.target]?.label || human(edge.target)} — ${edge.condition || "Recorded workflow transition"}`));
      this.graph.append(inspector);
    }
    openTrace(id) {
      this.selected = id;
      let row = this.data.rows.find(r => r.id === id); const seen = new Set();
      while (row && !seen.has(row.id)) {seen.add(row.id); this.expanded.add(row.id); row = this.data.rows.find(r => r.id === row.parent_id);}
      this.renderTraces(); this.navigate("agent-traces"); this.focus(`trace:${id}`);
    }
    renderTraces() {
      const root = this.traces, rows = this.data.rows, run = rows.find(r => r.kind === "run"); root.replaceChildren();
      const heading = el("header", "rg-heading"), title = el("div"); title.append(el("h2", "", "Agent traces"), el("p", "", "Recorded attempts on a shared timeline"));
      const parents = new Set(rows.map(r => r.parent_id).filter(Boolean)); const allOpen = [...parents].every(id => this.expanded.has(id));
      heading.append(title, button(allOpen ? "Collapse all" : "Expand all", () => {this.expanded = new Set(allOpen ? run ? [run.id] : [] : parents); this.renderTraces(); this.focus("expand-all");}, "text-button", "expand-all")); root.append(heading);
      const summary = el("div", "at-summary");
      summary.append(el("span", "", `Elapsed ${duration(run?.duration_seconds)}`), el("span", "", `Model cost ${cost(run?.cost_usd)}${run?.estimated ? " (estimated)" : ""}`), el("span", "", `Reserved ${cost(run?.reserved_usd)}`)); root.append(summary);
      const layout = el("div", "at-layout"), scroll = el("div", "at-scroll"); scroll.tabIndex = 0; scroll.dataset.processKey = "trace-scroll"; scroll.setAttribute("aria-label", "Scrollable execution timeline");
      const table = el("div", "at-table"); const scale = timeline(rows, this.data.captured_at);
      const axis = el("div", "at-axis"); axis.append(el("span", "", "Recorded work / status"), el("span", "", "Elapsed"), el("span", "", "Cost"), el("span", "", `Timeline · 0 — ${duration(scale.seconds)}`)); table.append(axis);
      for (const {row, depth, hasChildren} of visibleRows(rows, this.expanded)) {
        const line = el("div", `at-row${row.id === this.selected ? " selected" : ""}`), name = el("div", "at-name"); name.style.setProperty("--depth", depth);
        if (hasChildren) {
          const expand = button(this.expanded.has(row.id) ? "−" : "+", () => {this.expanded.has(row.id) ? this.expanded.delete(row.id) : this.expanded.add(row.id); this.renderTraces(); this.focus(`expand:${row.id}`);}, "at-expand", `expand:${row.id}`);
          expand.setAttribute("aria-label", `${this.expanded.has(row.id) ? "Collapse" : "Expand"} ${this.labelFor(row)}`); expand.setAttribute("aria-expanded", String(this.expanded.has(row.id))); name.append(expand);
        } else name.append(el("span", "at-spacer"));
        const select = button("", () => {this.selected = row.id; this.renderTraces(); this.focus(`trace:${row.id}`);}, "", `trace:${row.id}`); select.setAttribute("aria-pressed", String(this.selected === row.id));
        select.append(el("strong", "", this.labelFor(row)), el("small", "", human(row.status))); name.append(select);
        const track = el("div", `at-track ${row.status}`); track.setAttribute("aria-hidden", "true");
        const start = time(row.started_at);
        if (Number.isFinite(start) && row.duration_seconds != null && scale.start !== null) {
          const bar = el("span"); bar.style.left = `${Math.max(0, Math.min(100, (start - scale.start) / 1000 / scale.seconds * 100))}%`; bar.style.width = `${Math.max(.2, Math.min(100, row.duration_seconds / scale.seconds * 100))}%`; track.append(bar);
        } else track.append(el("small", "", "Timing not recorded"));
        line.append(name, el("span", "at-number", duration(row.duration_seconds)), el("span", "at-number", `${cost(row.cost_usd)}${row.estimated ? " est." : ""}`), track); table.append(line);
      }
      if (!rows.length) table.append(el("p", "panel-note", "No execution records yet."));
      scroll.append(table); layout.append(scroll);
      const details = el("aside", "at-detail"), selected = rows.find(r => r.id === this.selected);
      if (selected) {
        details.append(el("h3", "", this.labelFor(selected)), el("p", "", human(selected.status)));
        const dl = el("dl");
        for (const [label, value] of [["Elapsed", duration(selected.duration_seconds)], ["Model cost", cost(selected.cost_usd)], ["Reserved", cost(selected.reserved_usd)], ["Started", selected.started_at ? new Date(selected.started_at).toLocaleString() : "Not recorded"]]) {const div = el("div"); div.append(el("dt", "", label), el("dd", "", value)); dl.append(div);} details.append(dl);
        details.append(el("p", "", selected.estimated ? "Cost is conservatively estimated." : "Costs use configured model rates; compute and storage are separate."));
        details.append(el("p", "", `Timing: ${human(selected.timing_basis || "not recorded")}. Parent totals include children; do not add both.`));
        if (selected.stage && this.workflow.nodes?.[selected.stage] && phaseFor(this.workflow, selected.stage) !== "complete") details.append(button("Show task in graph →", () => {this.stage = selected.stage; this.phase = phaseFor(this.workflow, selected.stage); this.follow = false; this.mode = "tasks"; this.render(); this.navigate("overview"); this.focus(`task:${selected.stage}`);}, "text-button", "show-graph"));
        const raw = el("details", "raw-details"); raw.dataset.processKey = `record:${selected.id}`;
        const summary = el("summary", "", "Recorded evidence"); summary.dataset.processKey = `record-summary:${selected.id}`;
        raw.append(summary, el("pre", "", JSON.stringify(selected, null, 2))); details.append(raw);
      } else details.append(el("p", "", "Select an attempt to inspect its timing, usage and recorded evidence."));
      layout.append(details); root.append(layout);
      root.append(el("footer", "rg-footer", "Elapsed stage time may include pauses. Parallel calls overlap. Unknown timing or cost is shown as —. Execution completion does not establish scientific acceptance."));
      for (const note of this.data.notes || []) root.append(el("p", "panel-note", note));
    }
    drawTemple() {
      if (this.frame !== null) cancelAnimationFrame(this.frame);
      this.frame = null;
      const canvas = this.graph.querySelector("canvas");
      if (!canvas || !this.data || this.data.error || !canvas.clientWidth || document.hidden) return;
      if (!this.scene) { scene().then(value => {this.scene = value; this.drawTemple();}).catch(() => {}); return; }
      const phase = currentPhase(this.data, this.workflow), phases = this.phaseEntries().map(([p]) => p), index = phases.indexOf(phase);
      if (index < 0) return;
      const key = `${this.runId}:${phase}`;
      if (this.templeKey !== key) {this.templeKey = key; this.motionStart = performance.now();}
      const cutoffs = {preparation: 1.2, ideation: 3, experimentation: 5.7, ablation: 6.8, manuscript: 8.3, integrity: 9};
      const cut = cutoffs[phase] ?? 1.2;
      const tick = () => {
        this.frame = null;
        if (!canvas.isConnected || document.hidden) return;
        const progress = this.reduced.matches ? 1 : Math.min(1, (performance.now() - this.motionStart) / 800);
        const w = canvas.clientWidth, h = canvas.clientHeight, ctx = canvas.getContext("2d"); if (!ctx || !w || !h) return;
        const ratio = Math.min(window.devicePixelRatio || 1, 2); canvas.width = w * ratio; canvas.height = h * ratio; ctx.scale(ratio, ratio);
        const blocks = this.scene.blocks.filter(b => b[1] <= cut).map(b => {const block = [...b]; block[6] = 0; block[1] += (1-progress)*.7; return block;});
        const css = getComputedStyle(document.documentElement);
        for (const face of Temple.polygons({...this.scene, blocks}, this.scene.duration, this.scene.yaw, this.scene.pitch)) {
          const points = face.points.map(p => [w/2+p[0]*w/23,h*.83+p[1]*w/23]); ctx.beginPath(); ctx.moveTo(...points[0]); for (const p of points.slice(1)) ctx.lineTo(...p); ctx.closePath();
          ctx.fillStyle = css.getPropertyValue(`--${face.top ? "muted" : face.side ? "raised" : "border"}`).trim(); ctx.fill(); ctx.strokeStyle = css.getPropertyValue("--bg").trim(); ctx.lineWidth = .3; ctx.stroke();
        }
        if (progress < 1) this.frame = requestAnimationFrame(tick);
      };
      tick();
    }
  }
  return {View, aggregate, currentPhase, timeline, visibleRows, duration, cost, runStatus, phaseEntries};
})();
