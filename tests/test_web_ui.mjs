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
