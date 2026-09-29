/** Browser form logic without network access, DOM automation, or third-party dependencies. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../src/autoresearch/static/app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../src/autoresearch/static/index.html', import.meta.url), 'utf8');

function fixture() {
  const nodes = new Map();
  const document = {
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, {
        value: '', checked: false, disabled: false, hidden: false, textContent: '',
        addEventListener() {},
      });
      return nodes.get(selector);
    },
    querySelectorAll() { return []; },
  };
  const context = { document, console, setTimeout() {}, clearTimeout() {} };
  runInNewContext(source.replace(/\nboot\(\);\s*$/, ''), context);
  const config = {
    mode: 'live', schema_version: 1,
    project: {
      source_dir: '/tmp/research-project', baseline_argv: ['python3', 'train.py'],
      evaluator_argv: ['python3', 'evaluate.py'], protected_paths: ['evaluate.py'],
      primary_metric: 'score', metrics: { score: 'max', latency: 'min' },
      sota: { score: 0.8, latency: 10 }, baseline_expected: {},
      specification: 'Use the immutable held-out evaluation split.', seeds: [11, 29],
      dataset_manifest: { fixture: 'preserve-me' },
    },
    provider: { model: 'reasoning-model', base_url: 'https://api.x.ai/v1', api_key_env: 'XAI_API_KEY' },
    execution: { backend: 'docker', docker_image: 'python:3.11-slim', allow_local: false, slurm_account: '', slurm_partition: '', readonly_mounts: [{ source: '/tmp/data', target: '/data' }] },
    budget: { usd: 25, max_calls: 2000, max_experiments: 200, wall_seconds: 604800 },
    pipeline: { critics: 3, agents_per_role: 2, successful_ideas: 4 },
    role_providers: { novelty: { model: 'local-filter-model' } },
    privacy: { traces: 'metadata', cache: false },
  };
  context.fixtureConfig = config;
  runInNewContext('state.serverConfig = fixtureConfig; populateSetup(fixtureConfig);', context);
  const evaluate = (script) => runInNewContext(script, context);
  return { context, nodes, evaluate, config };
}

test('every literal DOM reference is backed by an element in the page', () => {
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]));
  for (const match of source.matchAll(/\$\("#([a-zA-Z0-9_-]+)"\)/g)) assert.ok(ids.has(match[1]), `Missing element ${match[1]}`);
});

test('editing a basic field preserves advanced protocol, routing, privacy and dataset settings', () => {
  const { evaluate, nodes, config } = fixture();
  nodes.get('#setup-budget').value = '40';
  const result = JSON.parse(evaluate('JSON.stringify(readSetup())'));
  assert.equal(result.budget.usd, 40);
  assert.deepEqual(result.pipeline, config.pipeline);
  assert.deepEqual(result.role_providers, config.role_providers);
  assert.deepEqual(result.privacy, config.privacy);
  assert.deepEqual(result.execution.readonly_mounts, config.execution.readonly_mounts);
  assert.deepEqual(result.project.dataset_manifest, config.project.dataset_manifest);
  assert.deepEqual(result.project.seeds, [11, 29]);
  assert.equal(result.project.metrics.latency, 'min');
  assert.equal(result.project.sota.latency, 10);
});

test('a primary metric rename preserves independently configured comparison metrics', () => {
  const { evaluate, nodes } = fixture();
  nodes.get('#setup-metric').value = 'accuracy';
  nodes.get('#setup-sota').value = '0.9';
  const result = JSON.parse(evaluate('JSON.stringify(readSetup())'));
  assert.deepEqual(result.project.metrics, { latency: 'min', accuracy: 'max' });
  assert.deepEqual(result.project.sota, { latency: 10, accuracy: 0.9 });
});

test('unapplied advanced edits cannot be silently discarded during validation', () => {
  const { evaluate } = fixture();
  evaluate('state.jsonDirty = true;');
  assert.throws(() => evaluate('readSetup()'), /unapplied edits/);
});

test('command entries require argument arrays and local execution remains explicit', () => {
  const { evaluate, nodes } = fixture();
  nodes.get('#setup-backend').value = 'local';
  assert.equal(JSON.parse(evaluate('JSON.stringify(readSetup())')).execution.allow_local, false);
  nodes.get('#setup-baseline').value = 'python3 train.py';
  assert.throws(() => evaluate('readSetup()'), /JSON string array/);
  nodes.get('#setup-baseline').value = '["python3", 42]';
  assert.throws(() => evaluate('readSetup()'), /nonempty strings/);
});

test('any setup change invalidates prior readiness approval', () => {
  const { evaluate, nodes } = fixture();
  evaluate('state.validatedKey = "previous-config"; invalidateSetup();');
  assert.equal(evaluate('state.validatedKey'), null);
  assert.equal(nodes.get('#create-live').disabled, true);
});


test('workflow labels and phases come from the runtime graph', () => {
  const { evaluate, context } = fixture();
  context.workflowFixture = { nodes: {
    custom_stage: { label: 'A configured stage', phase: 'Discovery' },
    complete: { label: 'Finished', phase: 'Release' },
  } };
  evaluate('applyWorkflow(workflowFixture)');
  assert.equal(evaluate('stageName("custom_stage")'), 'A configured stage');
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(phases)')), [['Discovery', ['custom_stage']], ['Release', ['complete']]]);
});

test('legacy selection clears another runs graph and adoption invalidates behavior cache', async () => {
  const { evaluate } = fixture();
  evaluate(`
    let behaviorReads = 0;
    let nextRun = {id: 'legacy', behavior: null};
    let nextBehavior = {status: 'legacy_unpinned', workflow: {}, agents: {}};
    api = async path => {
      if (path.endsWith('/behavior')) { behaviorReads++; return nextBehavior; }
      if (path.includes('/events?')) return {events: []};
      return {run: nextRun};
    };
    renderDetail = () => {};
    state.id = 'legacy';
    applyWorkflow({nodes: {full: {label: 'Prior run label', phase: 'Prior'}}});
  `);
  await evaluate('refreshDetail()');
  assert.equal(evaluate('stageName("full")'), 'Full');
  assert.equal(evaluate('phases.length'), 0);
  evaluate(`
    nextRun = {id: 'legacy', behavior: {bundle_sha256: 'new-bundle'}};
    nextBehavior = {status: 'pinned', workflow: {nodes: {full: {label: 'Adopted full benchmark', phase: 'Experiments'}}}, agents: {}};
  `);
  await evaluate('refreshDetail()');
  assert.equal(evaluate('behaviorReads'), 2);
  assert.equal(evaluate('state.behavior.status'), 'pinned');
  assert.equal(evaluate('stageName("full")'), 'Adopted full benchmark');
});

test('unreadable behavior preserves research and journal inspection and retries recovery', async () => {
  const { evaluate } = fixture();
  evaluate(`
    let renders = 0;
    let corrupt = true;
    api = async path => {
      if (path.endsWith('/behavior')) {
        if (corrupt) throw new Error('Artifact integrity check failed');
        return {status: 'pinned', workflow: {nodes: {}}, agents: {}};
      }
      if (path.includes('/events?')) return {events: [{seq: 1, kind: 'run_blocked'}]};
      return {run: {id: 'damaged', behavior: {bundle_sha256: 'bundle'}, error: 'Important failure evidence'}};
    };
    renderDetail = () => { renders++; };
    state.id = 'damaged';
  `);
  await evaluate('refreshDetail()');
  assert.equal(evaluate('renders'), 1);
  assert.equal(evaluate('state.events[0].kind'), 'run_blocked');
  assert.equal(evaluate('state.detail.run.error'), 'Important failure evidence');
  assert.match(evaluate('state.behavior.error'), /integrity/);
  evaluate('corrupt = false');
  await evaluate('refreshDetail()');
  assert.equal(evaluate('state.behavior.status'), 'pinned');
  assert.equal(evaluate('renders'), 2);
});


test('settings fields round trip data, privacy and limits without discarding advanced options', () => {
  const {evaluate, nodes, config} = fixture();
  nodes.get('#setup-specification').value = 'Fixed splits and immutable benchmark';
  nodes.get('#setup-datasets').value = '{"dataset":"public synthetic fixture"}';
  nodes.get('#setup-mounts').value = '{"benchmark":"/tmp/benchmark"}';
  nodes.get('#setup-max-calls').value = '100';
  nodes.get('#setup-traces').value = 'redacted';
  const result = JSON.parse(evaluate('JSON.stringify(readSetup())'));
  assert.equal(result.budget.max_calls, 100);
  assert.equal(result.privacy.traces, 'redacted');
  assert.equal(result.project.specification, 'Fixed splits and immutable benchmark');
  assert.deepEqual(result.execution.readonly_mounts, {benchmark: '/tmp/benchmark'});
  assert.deepEqual(result.role_providers, config.role_providers);
  assert.deepEqual(result.project.dataset_manifest, {dataset: 'public synthetic fixture'});
});

test('saving incomplete settings sends the loaded revision and creates no run', async () => {
  const {evaluate, nodes, context} = fixture();
  const requests = [];
  context.fetch = async (path, options) => {
    requests.push({path, body: JSON.parse(options.body)});
    return {ok: true, json: async () => ({saved: true, revision: 8})};
  };
  nodes.get('#setup-source').value = '';
  nodes.get('#setup-sota').value = '';
  evaluate('state.settingsMode = true; state.settingsRevision = 7');
  await evaluate('saveSettings()');
  assert.equal(requests.length, 1);
  assert.equal(requests[0].path, '/api/settings');
  assert.equal(requests[0].body.revision, 7);
  assert.equal(requests[0].body.config.project.source_dir, '');
  assert.equal(evaluate('state.settingsRevision'), 8);
  assert.match(nodes.get('#validation-state').textContent, /saved/);
});

test('a failed settings save preserves edits and reports the conflict', async () => {
  const {evaluate, nodes, context} = fixture();
  context.fetch = async () => ({ok: false, json: async () => ({error: 'Settings changed in another interface. Reload settings before saving again.'})});
  nodes.get('#setup-model').value = 'unsaved-edit';
  await evaluate('saveSettings()');
  assert.equal(nodes.get('#setup-model').value, 'unsaved-edit');
  assert.match(nodes.get('#setup-error').textContent, /Reload settings/);
  assert.equal(nodes.get('#save-settings').disabled, false);
});


test('advanced JSON replaces settings so an override can be removed', async () => {
  const {evaluate, nodes, context, config} = fixture();
  const replacement = {...config, role_providers: {}, role_panels: {}, role_commands: {}, prompt_overrides: {}};
  const requests = [];
  context.fetch = async (path, options) => {
    const body = JSON.parse(options.body);
    requests.push({path, body});
    return {ok: true, json: async () => ({config: body.config})};
  };
  nodes.get('#setup-json').value = JSON.stringify(replacement);
  evaluate('state.jsonDirty = true');
  await evaluate('applyAdvanced()');
  const result = JSON.parse(evaluate('JSON.stringify(readSetup())'));
  assert.deepEqual(result.role_providers, {});
  assert.deepEqual(result.role_panels, {});
  assert.deepEqual(result.role_commands, {});
  assert.deepEqual(result.prompt_overrides, {});
  assert.equal(requests[0].path, '/api/settings/validate');
  assert.equal(evaluate('state.jsonDirty'), false);
});

test('late JSON validation cannot overwrite newer form edits', async () => {
  const {evaluate, nodes, context, config} = fixture();
  let resolve;
  context.fetch = () => new Promise(done => {resolve = done;});
  nodes.get('#setup-json').value = JSON.stringify(config);
  const pending = evaluate('applyAdvanced()');
  nodes.get('#setup-model').value = 'newer-edit';
  evaluate('invalidateSetup()');
  resolve({ok: true, json: async () => ({config})});
  await pending;
  assert.equal(nodes.get('#setup-model').value, 'newer-edit');
  assert.match(nodes.get('#setup-error').textContent, /changed while applying/);
});
