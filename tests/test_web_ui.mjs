/** Browser form logic without network access, DOM automation, or third-party dependencies. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../src/autoresearch/static/app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../src/autoresearch/static/index.html', import.meta.url), 'utf8');

function fixture({missing = []} = {}) {
  const nodes = new Map();
  function node() {
    return {
      value: '', checked: false, disabled: false, required: false, hidden: false, textContent: '', children: [], style: {}, dataset: {}, open: false, beforeCalls: [],
      handlers: {}, addEventListener(type, handler) { this.handlers[type] = handler; }, click() { return this.handlers.click?.(); },
      removeAttribute(name) { delete this[name]; }, setAttribute(name, value) { this[name] = value; },
      append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; },
      before(item) { this.beforeCalls.push(item); },
      showModal() { this.open = true; }, close() { this.open = false; }, focus() {}, checkValidity() { return true; }, reportValidity() {},
      set innerHTML(_) { throw new Error('Untrusted HTML rendering'); },
    };
  }
  const document = {
    documentElement: {dataset: {}},
    addEventListener() {},
    querySelector(selector) {
      if (missing.includes(selector)) return null;
      if (!nodes.has(selector)) nodes.set(selector, node());
      return nodes.get(selector);
    },
    querySelectorAll() { return []; },
    createElement() { return node(); }, addEventListener() {},
  };
  const storage = new Map();
  const context = {
    document, console, URL, URLSearchParams, setTimeout() {}, clearTimeout() {}, setInterval() {},
    location: {hostname: '127.0.0.1', pathname: '/', search: '', hash: ''},
    history: {replaceState(_state, _unused, value) { context.replacedURL = value; }},
    sessionStorage: {getItem(key) { return storage.get(key); }, setItem(key, value) { storage.set(key, value); }, removeItem(key) { storage.delete(key); }},
  };
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
  return { context, nodes, evaluate, config, storage };
}

test('every literal DOM reference is backed by an element in the page', () => {
  const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]));
  for (const match of source.matchAll(/\$\("#([a-zA-Z0-9_-]+)"\)/g)) assert.ok(ids.has(match[1]), `Missing element ${match[1]}`);
});

test('the console initializes when the optional Home guide button is absent', () => {
  assert.doesNotThrow(() => fixture({missing: ['#welcome-guide']}));
});

test('a question must be written before the explicit setup handoff', () => {
  const { evaluate, nodes } = fixture();
  evaluate('let inquiryHandoff = null; openSetup = (...args) => { inquiryHandoff = args; };');
  evaluate('$("#home-question"); $("#home-question-status");');
  nodes.get('#home-question').focus = () => { nodes.get('#home-question').focused = true; };
  evaluate('beginInquiry();');
  assert.equal(evaluate('inquiryHandoff'), null);
  assert.equal(nodes.get('#home-question').focused, true);
  assert.match(nodes.get('#home-question-status').textContent, /Write the question/);
  nodes.get('#home-question').value = 'Can a smaller model preserve calibration?';
  evaluate('beginInquiry();');
  assert.deepEqual(
    JSON.parse(evaluate('JSON.stringify(inquiryHandoff)')),
    [null, false, 'Can a smaller model preserve calibration?'],
  );
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

test('commands accept plain text and legacy arrays while local execution remains explicit', () => {
  const { evaluate, nodes } = fixture();
  nodes.get('#setup-backend').value = 'local';
  assert.equal(JSON.parse(evaluate('JSON.stringify(readSetup())')).execution.allow_local, false);
  nodes.get('#setup-baseline').value = 'python3 train.py';
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(readSetup().project.baseline_argv)')), ['python3', 'train.py']);
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

test('remote bootstrap removes fragment before fetching and retains only the authenticated token', async () => {
  const {context, nodes, evaluate, storage} = fixture();
  const token = 'a'.repeat(43);
  context.location.hash = `#remote-token=${token}`;
  context.fetch = async (path, options) => {
    assert.equal(context.replacedURL, '/');
    assert.equal(path, '/api/bootstrap');
    assert.equal(options.headers.Authorization, `Bearer ${token}`);
    return {ok: true, json: async () => ({token, managed_remote: true, remote_label: '<img src=x onerror=alert(1)>', stages: [], workflow: {}})};
  };
  evaluate('refresh = async () => {};');
  await evaluate('boot()');
  assert.equal(nodes.get('#connection-place').textContent, 'SSH · <img src=x onerror=alert(1)>');
  assert.deepEqual([...storage.entries()], [['autoresearch.remoteToken', token]]);
  context.location.hash = '';
  assert.equal(evaluate('takeRemoteToken()'), token);
});

test('expired remote token is discarded and never falls back to unauthenticated retry', async () => {
  const {context, nodes, evaluate, storage} = fixture();
  storage.set('autoresearch.remoteToken', 'b'.repeat(43));
  let requests = 0;
  context.fetch = async () => {requests++; return {ok: false};};
  await evaluate('boot()');
  assert.equal(requests, 1);
  assert.equal(storage.size, 0);
  assert.match(nodes.get('#global-error').textContent, /reconnect using SSH connections/);
});

test('local bootstrap still works without a token and labels the workspace', async () => {
  const {context, nodes, evaluate, storage} = fixture();
  context.fetch = async (_path, options) => {
    assert.equal(options.headers.Authorization, undefined);
    return {ok: true, json: async () => ({token: 'local-token', managed_remote: false, stages: []})};
  };
  evaluate('refresh = async () => {};');
  await evaluate('boot()');
  assert.equal(nodes.get('#connection-place').textContent, 'LOCAL WORKSPACE');
  assert.equal(storage.size, 0);
});

test('invalid fragment is erased even when token validation rejects it and unavailable storage is optional', () => {
  const {context, evaluate} = fixture();
  context.location.hash = '#remote-token=invalid%20token&view=research';
  assert.throws(() => evaluate('takeRemoteToken()'), /Invalid remote/);
  assert.equal(context.replacedURL, '/#view=research');
  context.location.hash = `#remote-token=${'c'.repeat(43)}`;
  context.sessionStorage.getItem = () => {throw new Error('disabled');};
  assert.equal(evaluate('takeRemoteToken()'), 'c'.repeat(43));
});

test('SSH target suggestions and profile labels render as inert text and manual targets are retained', async () => {
  const {nodes, evaluate} = fixture();
  evaluate(`api = async () => ({hosts: ['<img src=x>'], profiles: [{name: 'fixture', host: '<script>bad()</script>', port: 2202}]});`);
  await evaluate('loadRemotes("fixture")');
  assert.equal(nodes.get('#ssh-hosts').children[0].textContent, '<img src=x>');
  assert.equal(nodes.get('#remote-profile').children[1].textContent, 'fixture · <script>bad()</script>');
  nodes.get('#remote-host').value = 'user@new.example';
  const profile = JSON.parse(evaluate('JSON.stringify(readRemote())'));
  assert.equal(profile.host, 'user@new.example');
  assert.equal(profile.port, 2202);
  assert.equal(profile.identity_file, null);
  assert.match(html, /id="remote-host"[^>]+list="ssh-hosts"/);
});

test('remote research storage is visible before advanced settings and survives profile editing', () => {
  const form = html.split('<dialog id="remote-dialog"')[1].split('</dialog>')[0];
  const primary = form.split('<details class="advanced-setup">')[0];
  assert.match(primary, /id="remote-state-dir"/);
  assert.match(primary, /Research files/);
  assert.match(primary, /database defaults to this path/i);
  const {nodes, evaluate} = fixture();
  evaluate('fillRemote({name:"cluster",host:"host.example",state_dir:"/shared/projects/example/metis"})');
  assert.equal(nodes.get('#remote-state-dir').value, '/shared/projects/example/metis');
  assert.equal(JSON.parse(evaluate('JSON.stringify(readRemote())')).state_dir, '/shared/projects/example/metis');
});

test('compact picker searches inert saved names and discovered aliases', () => {
  const {nodes, evaluate} = fixture();
  evaluate(`state.connectionProfiles = [{name:'fixture',host:'<script>bad()</script>'}]; state.connectionHosts = ['example-alias']; state.connectionKey = 'profile:fixture'; renderConnectionPicker();`);
  assert.equal(nodes.get('#connection-details').textContent, 'Connection settings');
  const options = nodes.get('#connection-options').children;
  assert.equal(options.length, 3);
  assert.equal(options[1].children[1].children[1].textContent, '<script>bad()</script>');
  assert.equal(options[2].children[1].children[0].textContent, 'example-alias');
  assert.equal(options[1]['aria-pressed'], 'true');
  assert.equal(options[2]['aria-pressed'], 'false');
  nodes.get('#connection-search').value = 'fixture';
  evaluate('searchConnections()');
  assert.equal(nodes.get('#connection-options').children.length, 2);
  assert.equal(nodes.get('#connection-primary').textContent, 'Connect to fixture');
  nodes.get('#connection-search').value = 'example-alias';
  evaluate('searchConnections()');
  assert.equal(nodes.get('#connection-primary').textContent, 'Set up host');
  nodes.get('#connection-search').value = 'no matching host';
  evaluate('searchConnections()');
  assert.equal(nodes.get('#connection-primary').textContent, 'Stay on this computer');
  assert.match(html, /id="connection-picker" class="connection-picker"/);
  assert.match(html, /id="connection-switch" type="button"/);
});

test('saved profile connects through SSH authentication without installing or exposing a token in status', async () => {
  const {context, nodes, evaluate} = fixture();
  const token = 'g'.repeat(43);
  const url = `http://127.0.0.1:49152/#remote-token=${token}`;
  const calls = [];
  context.quickRequest = async (path) => {
    calls.push(path);
    return path.endsWith('/authenticate') ? {status:'authenticated'} : {status:'connected',url};
  };
  evaluate(`api = quickRequest; state.connectionProfiles = [{name:'fixture',host:'test.example'}]; state.connectionKey = 'profile:fixture';`);
  await evaluate('connectFromPicker()');
  assert.deepEqual(calls, ['/api/remotes/fixture/authenticate', '/api/remotes/fixture/connect']);
  assert.equal(nodes.get('#connection-dashboard').href, url);
  assert.equal(nodes.get('#connection-dashboard').hidden, false);
  assert.equal(nodes.get('#connection-disconnect').hidden, false);
  assert.equal(nodes.get('#connection-picker-status').textContent.includes(token), false);
});

test('picker restores a connected tunnel from server status after page reload', async () => {
  const {context, nodes, evaluate} = fixture();
  const url = `http://127.0.0.1:49152/#remote-token=${'h'.repeat(43)}`;
  const calls = [];
  context.quickRequest = async (path) => {
    calls.push(path);
    if (path === '/api/remotes') return {profiles:[{name:'fixture',host:'test.example'}],hosts:[]};
    return {status:'connected',url};
  };
  evaluate('api = quickRequest;');
  await evaluate('openConnectionPicker()');
  assert.deepEqual(calls, ['/api/remotes', '/api/remotes/fixture/status']);
  assert.equal(nodes.get('#connection-dashboard').href, url);
  assert.equal(nodes.get('#connection-dashboard').hidden, false);
  assert.equal(nodes.get('#connection-disconnect').hidden, false);
  assert.equal(nodes.get('#connection-primary').hidden, true);
});

test('new SSH host receives a unique saved profile name', () => {
  const {evaluate} = fixture();
  evaluate(`state.remoteProfiles = [{name:'foo-example'}, {name:'foo-example-2'}];`);
  assert.equal(evaluate(`unusedConnectionName('foo.example')`), 'foo-example-3');
  assert.equal(evaluate(`unusedConnectionName('bar.example')`), 'bar-example');
});

test('quick connection waits for an explicit SSH answer before connecting', async () => {
  const {context, nodes, evaluate} = fixture();
  const calls = [];
  context.quickRequest = async (path) => {
    calls.push(path);
    if (path.endsWith('/authenticate')) return {session_id:'session-one',status:'authenticating',output:'Host fingerprint SHA256:fixture. Continue (yes/no)?'};
    return {status:'failed',message:'Runtime needs installation.'};
  };
  evaluate(`api = quickRequest; state.connectionProfiles = [{name:'fixture',host:'test.example'}]; state.connectionKey = 'profile:fixture';`);
  await evaluate('connectFromPicker()');
  assert.deepEqual(calls, ['/api/remotes/fixture/authenticate']);
  assert.equal(nodes.get('#ssh-auth-dialog').open, true);
  assert.match(nodes.get('#ssh-auth-output').textContent, /SHA256:fixture/);
  evaluate(`renderAuthentication({session_id:'session-one',status:'authenticated',message:'Signed in.'});`);
  await new Promise(setImmediate);
  assert.deepEqual(calls, ['/api/remotes/fixture/authenticate', '/api/remotes/fixture/connect']);
  assert.equal(nodes.get('#ssh-auth-dialog').open, false);
  assert.match(nodes.get('#connection-picker-status').textContent, /Runtime needs installation/);
  assert.equal(nodes.get('#connection-details').hidden, false);
  assert.equal(nodes.get('#connection-dashboard').hidden, true);
});

test('compact picker preserves a draft and never manages SSH inside a remote dashboard', async () => {
  const {context, nodes, evaluate} = fixture();
  evaluate(`state.remoteDirty = true; state.managedRemote = true; state.remoteLabel = 'remote fixture'; api = async () => { throw new Error('Nested SSH is disabled'); };`);
  await evaluate('openConnectionPicker()');
  assert.equal(nodes.get('#connection-primary').hidden, true);
  assert.equal(nodes.get('#connection-add').hidden, true);
  assert.match(nodes.get('#connection-guidance').textContent, /local console/);
  evaluate(`state.managedRemote = false;`);
  nodes.get('#remote-host').value = 'existing-draft.example';
  await evaluate('openRemoteSettings("", "another.example")');
  assert.equal(nodes.get('#remote-host').value, 'existing-draft.example');
  assert.equal(nodes.get('#remote-dialog').open, true);
  assert.equal(context.location.hostname, '127.0.0.1');
});

test('dashboard links accept only token-bearing local HTTP forwards', () => {
  const {evaluate, nodes} = fixture();
  const safe = `http://127.0.0.1:49152/#remote-token=${'d'.repeat(43)}`;
  assert.equal(evaluate(`remoteDashboardURL(${JSON.stringify(safe)})`), safe);
  for (const url of ['javascript:alert(1)', 'https://attacker.example/', safe.replace('127.0.0.1', 'attacker.example'), safe.replace('127.0.0.1', 'user@localhost'), safe.replace('/#', '/evil#'), safe.replace('#', '?leak=yes#'), 'http://localhost:49152/']) {
    assert.equal(evaluate(`remoteDashboardURL(${JSON.stringify(url)})`), null);
  }
  evaluate(`renderRemoteStatus({status:'connected', host:'<svg onload=bad()>', message:'<script>bad()</script>', url:${JSON.stringify(safe)}})`);
  assert.equal(nodes.get('#remote-open').href, safe);
  assert.match(nodes.get('#remote-status').textContent, /<svg onload=bad\(\)>/);
  evaluate('renderRemoteStatus({status:"disconnected"})');
  assert.equal(nodes.get('#remote-open').hidden, true);
  assert.equal(nodes.get('#remote-open').href, undefined);
});

test('remote navigation keeps the dashboard hostname so localhost forwarding stays same-site', () => {
  const {context, nodes, evaluate} = fixture();
  const token = 'f'.repeat(43);
  context.location.hostname = 'localhost';
  const target = `http://127.0.0.1:49152/#remote-token=${token}`;
  evaluate(`renderRemoteStatus({status:'connected',url:${JSON.stringify(target)}})`);
  const link = new URL(nodes.get('#remote-open').href);
  assert.equal(link.hostname, 'localhost');
  assert.equal(link.port, '49152');
  assert.equal(link.origin, 'http://localhost:49152');
  assert.equal(link.hash, `#remote-token=${token}`);
  assert.equal(link.search, '', 'The capability must stay in the fragment, outside HTTP requests');
  context.location.hostname = '127.0.0.1';
  assert.equal(evaluate(`remoteDashboardURL(${JSON.stringify(link.href)})`), target);
  context.location.hostname = 'attacker.example';
  assert.equal(evaluate(`remoteDashboardURL(${JSON.stringify(target)})`), null);
});

test('slow remote actions disable duplicate controls and perform only the selected action', async () => {
  const {context, nodes, evaluate} = fixture();
  let finish;
  const requests = [];
  context.actionRequest = async (path) => { requests.push(path); return new Promise(resolve => {finish = resolve;}); };
  evaluate('api = actionRequest; fillRemote({name:"fixture",host:"test.example"});');
  const running = evaluate('remoteAction("probe")');
  assert.equal(nodes.get('#remote-install').disabled, true);
  await evaluate('remoteAction("install")');
  assert.deepEqual(requests, ['/api/remotes/fixture/probe']);
  finish({status: 'ready'});
  await running;
  assert.equal(nodes.get('#remote-install').disabled, false);
  assert.equal(nodes.get('#remote-save').disabled, false);
});

test('MFA responses are cleared before request completes, never stored, and output stays inert', async () => {
  const {context, nodes, evaluate, storage} = fixture();
  const calls = [];
  let finish;
  context.authRequest = async (path, body) => {
    calls.push({path, body});
    if (path.endsWith('/authenticate')) return {session_id:'session-one', status:'authenticating', output:'<img src=x> MFA code:'};
    return new Promise(resolve => {finish = resolve;});
  };
  evaluate('api = authRequest; fillRemote({name:"fixture",host:"test.example"});');
  await evaluate('startAuthentication()');
  assert.equal(nodes.get('#ssh-auth-dialog').open, true);
  assert.equal(nodes.get('#ssh-auth-output').textContent, '<img src=x> MFA code:');
  nodes.get('#ssh-auth-answer').value = '  dummy-MFA-response  ';
  const pending = evaluate('answerAuthentication({preventDefault(){}})');
  assert.equal(nodes.get('#ssh-auth-answer').value, '');
  assert.equal(nodes.get('#ssh-auth-send').disabled, true);
  assert.equal(calls[1].body.answer, '  dummy-MFA-response  ');
  assert.equal(storage.size, 0);
  finish({session_id:'session-one', status:'authenticated', output:'Authenticated'});
  await pending;
  assert.equal(nodes.get('#ssh-auth-answer').disabled, true);
  assert.equal(nodes.get('#ssh-auth-cancel').textContent, 'Close');
  assert.match(html, /id="ssh-auth-answer" type="password" autocomplete="off"/);
  assert.equal(evaluate('JSON.stringify(state)').includes('dummy-MFA-response'), false);
});

test('SSH host-key approval requires explicit response and cancel ends the active prompt', async () => {
  const {context, nodes, evaluate} = fixture();
  const calls = [];
  context.authRequest = async (path, body) => {
    calls.push({path, body});
    return {session_id:'session-one', status:path.endsWith('/cancel') ? 'cancelled' : 'authenticating', output:'Host key fingerprint SHA256:fixture. Continue (yes/no)?'};
  };
  evaluate('api = authRequest; fillRemote({name:"fixture",host:"test.example"});');
  await evaluate('startAuthentication()');
  assert.equal(calls.length, 1, 'No host-key answer is sent automatically');
  nodes.get('#ssh-auth-answer').value = 'yes';
  await evaluate('answerAuthentication({preventDefault(){}})');
  assert.equal(calls[1].body.answer, 'yes');
  await evaluate('cancelAuthentication()');
  assert.equal(calls[2].path, '/api/remotes/authentication/session-one/cancel');
  assert.equal(nodes.get('#ssh-auth-dialog').open, false);
  assert.equal(nodes.get('#ssh-auth-output').textContent, '');
  assert.equal(evaluate('state.remoteAuth'), null);
  assert.equal(nodes.get('#remote-connect').disabled, false);
});

test('connection polling preserves the dashboard link and check failures remain actionable', async () => {
  const {nodes, evaluate} = fixture();
  const url = `http://127.0.0.1:49152/#remote-token=${'e'.repeat(43)}`;
  evaluate(`fillRemote({name:'fixture',host:'test.example'}); renderRemoteStatus({status:'connected',url:${JSON.stringify(url)}});`);
  evaluate(`api = async () => ({ready:false,problems:['Database is on an unsupported network filesystem'],python:{available:false,version:'3.9'},database_filesystem:{type:'nfs'},slurm:{available:true}});`);
  await evaluate('remoteAction("probe")');
  assert.equal(nodes.get('#remote-open').href, url);
  const report = nodes.get('#remote-report');
  assert.equal(report.hidden, false);
  assert.ok(report.children.some(child => child.textContent.includes('network filesystem')));
  assert.match(report.children.at(-1).children[1].textContent, /"type": "nfs"/);
  evaluate('renderRemoteStatus({status:"connected"})');
  assert.equal(nodes.get('#remote-open').href, url);
  assert.equal(report.hidden, false);
  assert.ok(report.children.some(child => child.textContent.includes('network filesystem')));
  evaluate('fillRemote({name:"another",host:"another.example"})');
  assert.equal(nodes.get('#remote-open').href, undefined);
  assert.equal(report.hidden, true);
});

test('remote check identifies distinct research and database locations', async () => {
  const {nodes, evaluate} = fixture();
  evaluate('fillRemote({name:"cluster",host:"host.example"}); api = async () => ({ready:false,problems:["Database directory uses nfs4"],research_dir:"/shared/projects/example/metis",database_dir:"/srv/example/metis-db"});');
  await evaluate('remoteAction("probe")');
  const visible = nodes.get('#remote-report').children.map(child => child.textContent).join(' ');
  assert.match(visible, /Research files.*\/shared\/projects\/example\/metis/);
  assert.match(visible, /Database.*\/srv\/example\/metis-db/);
});

test('failed installation retains diagnostic error after later tunnel status updates', async () => {
  const {nodes, evaluate} = fixture();
  evaluate('fillRemote({name:"fixture",host:"test.example"}); api = async () => ({status:"error",error:"Python interpreter is unavailable"});');
  await evaluate('remoteAction("install")');
  evaluate('renderRemoteStatus({status:"disconnected"})');
  assert.ok(nodes.get('#remote-report').children.some(child => child.textContent.includes('Python interpreter is unavailable')));
});

test('overlapping prompt submit leaves the unsent response intact', async () => {
  const {nodes, evaluate} = fixture();
  evaluate('renderAuthentication({session_id:"fixture",status:"authenticating"}); state.authBusy = true;');
  nodes.get('#ssh-auth-answer').value = 'unsent-response';
  await evaluate('answerAuthentication({preventDefault(){}})');
  assert.equal(nodes.get('#ssh-auth-answer').value, 'unsent-response');
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

test('an explicit empty response supports SSH prompts that request Enter', async () => {
  const {context, evaluate} = fixture();
  const responses = [];
  context.send = async (_path, body) => { responses.push(body.answer); return {session_id:'fixture',status:'authenticating'}; };
  evaluate('api = send; renderAuthentication({session_id:"fixture",status:"authenticating"});');
  await evaluate('answerAuthentication({preventDefault(){}})');
  assert.deepEqual(responses, ['']);
});

test('theme change persists only appearance and recovers from failure', async () => {
  const {evaluate, nodes, context} = fixture();
  const requests = [];
  context.fetch = async (path, options) => {
    requests.push({path, body: JSON.parse(options.body)});
    return {ok: true, json: async () => ({theme: 'cream'})};
  };
  await evaluate('toggleTheme()');
  assert.deepEqual(requests, [{path: '/api/appearance', body: {theme: 'cream'}}]);
  assert.equal(context.document.documentElement.dataset.theme, 'cream');
  context.fetch = async () => { throw new Error('Unavailable'); };
  await evaluate('toggleTheme()');
  assert.equal(context.document.documentElement.dataset.theme, 'cream');
  assert.equal(nodes.get('#theme-toggle').disabled, false);
});

test('moving between settings sections preserves unsaved values', () => {
  const {evaluate, nodes} = fixture();
  nodes.get('#setup-model').value = 'my-unsaved-model';
  evaluate('setSetupSection("model"); setSetupSection("review"); setSetupSection("project")');
  assert.equal(nodes.get('#setup-model').value, 'my-unsaved-model');
  assert.equal(nodes.get('#setup-back').disabled, true);
});

test('plain command quoting round-trips literal arguments and rejects shell syntax', () => {
  const {evaluate, context} = fixture();
  context.args = ['python3', 'train.py', '--label', "researcher's test", '$literal', 'back\\slash', 'a"b'];
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(parseCommand(formatCommand(args)))')), context.args);
  assert.throws(() => evaluate("parseCommand('python3 train.py | tee out')"), /Shell operators/);
  assert.throws(() => evaluate('parseCommand("python3 \\\"unfinished")'), /quotes/);
});

test('preparing AI requires preview and never generates or creates a run implicitly', async () => {
  const {evaluate, nodes} = fixture();
  nodes.get('#setup-objective') ?? evaluate('$("#setup-objective").value = "Question"');
  evaluate(`$("#setup-objective").value = "Question"; $("#onboarding-budget").value = "1";
    let requests = [];
    api = async (path, body) => { requests.push({path, body}); return {id:'setup-fixture', model:'fixture', maximum_usd:1, objective:'Question', inspection:{source_dir:'/tmp/project',files:[],documents:[],candidates:{},warnings:[]}}; };`);
  await evaluate('prepareProposal()');
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(requests.map(r=>r.path))')), ['/api/onboarding/prepare']);
  assert.equal(nodes.get('#generate-proposal').hidden, false);
  evaluate('invalidateSetup()');
  await evaluate('generateProposal()');
  assert.equal(evaluate('requests.length'), 1);
  assert.match(nodes.get('#setup-error').textContent, /changed/);
});

test('late AI previews cannot overwrite current setup or authorize sending', async () => {
  const {evaluate,nodes} = fixture();
  evaluate(`$("#setup-objective").value = "Question"; $("#onboarding-budget").value = "1";
    api = async () => { invalidateSetup(); return {id:'stale'}; };`);
  await evaluate('prepareProposal()');
  assert.equal(evaluate('state.proposalPrepared'), null);
  assert.equal(nodes.get('#generate-proposal').hidden, true);
});

test('AI results are inert, preserve blockers and never auto-select suggestions', () => {
  const {evaluate,nodes} = fixture();
  evaluate(`renderProposal({id:'setup-fixture',status:'complete',model:'fixture',usage:{cost_usd:0.02},proposal:{summary:'<script>unsafe</script>',suggestions:[{field:'project.baseline_argv',value:['python3','train.py'],reason:'Documented',evidence:['README.md']}],questions:['Which metric?'],blockers:['GPU adapter required'],drafts:[{path:'adapter.py',purpose:'Review',content:'untrusted text'}]}})`);
  const children = nodes.get('#onboarding-result').children;
  assert.ok(children.some(node => node.textContent === '<script>unsafe</script>'));
  assert.ok(children.some(node => node.textContent === 'GPU adapter required'));
  const choice = children.find(node => node.className === 'proposal-choice');
  assert.equal(choice.children[0].checked, false);
  assert.equal(evaluate('state.validatedKey'), null);
});

test('readiness leads with a short action plan and retains full diagnostics', () => {
  const {evaluate,nodes} = fixture();
  evaluate(`showReadiness({ready:false,guidance:[{owner:'metis',title:'Inspect the project',message:'Metis can inspect',section:'project',checks:['baseline']}],checks:[{name:'baseline',status:'error',message:'Choose training command'},{name:'paper-orchestra',status:'warning',message:'Writer needs setup'},{name:'provider-access',status:'warning',message:'Access untested'},{name:'source',status:'ok',message:'Source found'}]}, {candidates:{baseline:['train.py'],evaluator:['evaluate.py']}})`);
  const children = nodes.get('#setup-readiness').children;
  const step = children.find(node => node.className === 'setup-guidance-step');
  assert.ok(step);
  assert.match(step.children[2].textContent, /train.py/);
  const details = children.find(node => node.children?.[0]?.textContent === 'All setup diagnostics');
  assert.ok(details.children.some(node => node.className === 'readiness-check error'));
  assert.equal(details.open, false);
  const later = children.find(node => node.children?.[0]?.textContent === 'Before manuscript writing · prerequisites still needed');
  assert.ok(later);
  assert.equal(later.open, false);
});

test('checking setup inspects source automatically without a model request or applying commands', async () => {
  const {evaluate,nodes} = fixture();
  evaluate(`let setupRequests = [];
    api = async (path) => { setupRequests.push(path); return path === '/api/preflight'
      ? {ready:false,guidance:[{owner:'metis',title:'Inspect the project',message:'Review suggestions',section:'project',checks:['baseline','evaluator']}],checks:[]}
      : {source_dir:'/tmp/research-project',files:['train.py','evaluate.py'],documents:[],candidates:{baseline:['train.py'],evaluator:['evaluate.py']},warnings:[]}; };`);
  const before = nodes.get('#setup-baseline').value;
  await evaluate('validateSetup()');
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(setupRequests)')), ['/api/preflight', '/api/onboarding/inspect']);
  assert.equal(nodes.get('#setup-baseline').value, before);
  assert.equal(nodes.get('#onboarding-report').hidden, false);
  assert.equal(nodes.get('#create-live').disabled, true);
});

test('project inspection leaves automatic run naming tied to the question', async () => {
  const {evaluate, nodes} = fixture();
  evaluate(`$("#setup-objective").value = 'Can this result be reproduced?';
    api = async () => ({source_dir:'/tmp/research-project',files:[],documents:[],candidates:{},warnings:[]});`);
  await evaluate('inspectProject()');
  assert.equal(evaluate('$("#setup-run-title").value'), '');
  assert.equal(evaluate('runTitle()'), 'Can this result be reproduced?');
});

test('setup applies mechanical recovery before enabling run creation', async () => {
  const {evaluate, nodes} = fixture();
  evaluate(`state.setupBase.project.include = ['missing/*.py'];
    api = async (path, body) => {
      if (path === '/api/preflight') return {ready:false,guidance:[{owner:'metis',title:'Select project files',message:'Metis can select project files',section:'project',checks:['source']}],checks:[]};
      if (path === '/api/onboarding/recover') {
        const config = JSON.parse(JSON.stringify(body.config));
        config.project.include = ['train.py','evaluate.py'];
        return {config, readiness:{ready:true,guidance:[],checks:[],source_files:['evaluate.py','train.py'],source_file_count:2},actions:['Selected 2 project files.']};
      }
      throw new Error('Unexpected request');
    };`);
  await evaluate('validateSetup()');
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(state.setupBase.project.include)')), ['train.py','evaluate.py']);
  assert.equal(nodes.get('#create-live').disabled, false);
  assert.ok(nodes.get('#setup-readiness').children.some(item => /Selected 2 project files/.test(item.textContent)));
  const files = nodes.get('#setup-review-summary').children.find(item => item.className === 'raw-details');
  assert.equal(files.children[1].textContent, '2 project files selected\nevaluate.py\ntrain.py');
  assert.ok(!files.children[1].textContent.includes('missing/*.py'));
});

test('setup repairs a partial file selection that hides command scripts', async () => {
  const {evaluate, nodes} = fixture();
  evaluate(`let paths = [];
    state.setupBase.project.include = ['README.md'];
    api = async (path, body) => {
      paths.push(path);
      if (path === '/api/preflight') return {ready:false,guidance:[{owner:'metis',title:'Inspect the project',message:'Inspect commands',section:'project',checks:['baseline','evaluator']}],checks:[{name:'source',status:'ok',message:'1 project file selected.'},{name:'baseline',status:'error',message:'Script train.py is missing from the selected project files.'}]};
      if (path === '/api/onboarding/recover') {
        const config = JSON.parse(JSON.stringify(body.config));
        config.project.include = ['README.md','evaluate.py','train.py'];
        return {config, readiness:{ready:true,guidance:[],checks:[],source_files:['README.md','evaluate.py','train.py'],source_file_count:3},actions:['Selected 3 project files.']};
      }
      throw new Error('Unexpected request');
    };`);
  await evaluate('validateSetup()');
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(paths)')), ['/api/preflight','/api/onboarding/recover']);
  assert.equal(nodes.get('#create-live').disabled, false);
  assert.deepEqual(JSON.parse(evaluate('JSON.stringify(state.setupBase.project.include)')), ['README.md','evaluate.py','train.py']);
});

test('review labels a bounded project file preview with its remaining count', () => {
  const {evaluate, nodes} = fixture();
  evaluate(`renderSetupReview(fixtureConfig, {source_files:['evaluate.py','train.py'],source_file_count:5})`);
  const files = nodes.get('#setup-review-summary').children.find(item => item.className === 'raw-details');
  assert.equal(files.children[1].textContent, '5 project files selected\nevaluate.py\ntrain.py\n… and 3 more');
});

test('a stale recovery response cannot replace newer setup edits', async () => {
  const {evaluate, nodes} = fixture();
  evaluate(`api = async (path, body) => {
    if (path === '/api/preflight') return {ready:false,guidance:[{owner:'metis',title:'Prepare a Docker image',message:'Fetch image',section:'execution',checks:['docker-image']}],checks:[]};
    if (path === '/api/onboarding/recover') {
      invalidateSetup();
      return {config:body.config, readiness:{ready:true,guidance:[],checks:[]},actions:['Fetched image.']};
    }
  };`);
  await evaluate('validateSetup()');
  assert.equal(nodes.get('#create-live').disabled, true);
  assert.match(nodes.get('#validation-state').textContent, /Setup changed/);
});

test('a built image remains selected when the form is read for creation', async () => {
  const {evaluate, nodes} = fixture();
  evaluate(`api = async (path, body) => {
    if (path === '/api/preflight') return {ready:false,guidance:[{owner:'metis',title:'Prepare a Docker image',message:'Build image',section:'execution',checks:['docker-image']}],checks:[]};
    if (path === '/api/onboarding/recover') {
      const config = JSON.parse(JSON.stringify(body.config));
      config.execution.docker_image = 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
      return {config, readiness:{ready:true,guidance:[],checks:[]},actions:['Built image.']};
    }
  };`);
  await evaluate('validateSetup()');
  const image = 'sha256:' + 'a'.repeat(64);
  assert.equal(nodes.get('#setup-docker-image').value, image);
  assert.equal(evaluate('readSetup().execution.docker_image'), image);
  assert.equal(evaluate('state.validatedKey === JSON.stringify(readSetup())'), true);
});

test('failed automatic inspection tells the user why and offers a manual retry', async () => {
  const {evaluate,nodes} = fixture();
  evaluate(`let inspectionAttempts = 0; api = async (path) => { if (path === '/api/preflight') return {ready:false,guidance:[{owner:'metis',title:'Inspect the project',message:'Review suggestions',section:'project',checks:['baseline']}],checks:[]}; if (++inspectionAttempts === 1) throw new Error('Inspection limit reached'); return {source_dir:'/tmp/research-project',files:['train.py'],documents:[],candidates:{baseline:['train.py'],evaluator:[]},warnings:[]}; };`);
  await evaluate('validateSetup()');
  const step = nodes.get('#setup-readiness').children.find(node => node.className === 'setup-guidance-step');
  assert.ok(step.children.some(node => /Inspection limit reached/.test(node.textContent)));
  const retry = step.children.find(node => node.textContent === 'Retry project inspection →');
  assert.ok(retry);
  await retry.click();
  assert.equal(evaluate('inspectionAttempts'), 2);
  assert.equal(nodes.get('#onboarding-report').hidden, false);
  assert.equal(evaluate('state.setupSection'), 'project');
  const updated = nodes.get('#setup-readiness').children.find(node => node.className === 'setup-guidance-step');
  assert.ok(updated.children.some(node => /train.py/.test(node.textContent)));
  assert.ok(!updated.children.some(node => node.textContent === 'Retry project inspection →'));
  assert.equal(nodes.get('#create-live').disabled, true);
});

test('a folder Metis cannot use leads back to Project', () => {
  const {evaluate,nodes} = fixture();
  evaluate(`showReadiness({ready:false,guidance:[{owner:'you',title:'Choose a project folder',message:'No usable project files were found',section:'project',checks:['source']}],checks:[]})`);
  const step = nodes.get('#setup-readiness').children.find(node => node.className === 'setup-guidance-step');
  step.children.find(node => node.textContent === 'Open project →').click();
  assert.equal(evaluate('state.setupSection'), 'project');
});

test('credential field rejects a pasted value before sending setup to the server', () => {
  const {evaluate,nodes} = fixture();
  nodes.get('#setup-key-env').value = 'API_KEY-invalid-paste';
  assert.throws(() => evaluate('readSetup()'), /key variable name/);
  assert.equal(nodes.get('#setup-key-env').value, '');
  assert.equal(evaluate('state.setupSection'), 'model');
});

test('settings opens a dedicated page without research or a setup modal', async () => {
  const {evaluate, nodes, context, config} = fixture();
  evaluate(`api = async (path) => path === "/api/settings/models" ? {scope:"global", project:"", config:fixtureConfig, overrides:{}, inherited:{}, revision:"fixture"} : {config: fixtureConfig, revision: 1, source:"missing", vault_available:false, readiness: {checks: []}};`);
  await evaluate('openSetup(undefined, true)');
  assert.equal(evaluate('state.setupSection'), 'model');
  assert.equal(evaluate('state.page'), 'settings');
  assert.equal(nodes.get('#setup-dialog').open, false);
  assert.equal(nodes.get('#settings-page').hidden, false);
  assert.equal(nodes.get('#setup-nav').hidden, true);
  assert.doesNotMatch(nodes.get('#setup-model-status').textContent, /secret/i);
  assert.equal(nodes.get('#setup-key-name').textContent, 'XAI_API_KEY');
  assert.equal(context.document.querySelector('.setup-section-button[data-section="project"]').beforeCalls[0], context.document.querySelector('.setup-section-button[data-section="model"]'));
  assert.equal(nodes.get('#setup-back').disabled, true);
  nodes.get('#setup-next').click();
  assert.equal(evaluate('state.setupSection'), 'project');
  assert.equal(nodes.get('#setup-source').value, config.project.source_dir);
});

test('model access status never implies a provider call and changes invalidate the old check', () => {
  const {evaluate, nodes} = fixture();
  evaluate(`renderModelStatus({checks: [{name: 'provider:default', status: 'error', message: 'Set XAI_API_KEY in the server environment.'}]})`);
  assert.match(nodes.get('#setup-model-status').textContent, /Set XAI_API_KEY/);
  evaluate(`renderModelStatus({checks: [{name: 'provider:default', status: 'ok'}]})`);
  assert.match(nodes.get('#setup-model-status').textContent, /No model request was made/);
  nodes.get('#setup-key-env').value = 'OTHER_KEY';
  nodes.get('#setup-form').handlers.input({target: {id: 'setup-key-env'}});
  assert.equal(nodes.get('#setup-key-name').textContent, 'OTHER_KEY');
  assert.match(nodes.get('#setup-model-status').textContent, /has not been checked/);
});

test('invalid credential paste clears on input without echoing it into help', () => {
  const {evaluate, nodes} = fixture();
  evaluate(`$("#setup-key-env").value = 'API_KEY-invalid-paste'`);
  nodes.get('#setup-key-env').handlers.input({target: nodes.get('#setup-key-env')});
  nodes.get('#setup-form').handlers.input({target: nodes.get('#setup-key-env')});
  assert.equal(nodes.get('#setup-key-env').value, '');
  assert.doesNotMatch(nodes.get('#setup-key-name').textContent, /invalid-paste/);
  assert.doesNotMatch(nodes.get('#setup-model-status').textContent, /invalid-paste/);
  assert.match(nodes.get('#setup-error').textContent, /variable name/);
});

test('welcome question moves into setup without creating a run', async () => {
  const {evaluate, nodes, context, config} = fixture();
  const paths = [];
  context.fetch = async (path) => {
    paths.push(path);
    return {ok: true, json: async () => ({config, revision: 1})};
  };
  await evaluate('openSetup(undefined, false, "What evidence would change this conclusion?")');
  assert.equal(nodes.get('#setup-objective').value, 'What evidence would change this conclusion?');
  assert.equal(evaluate('runTitle()'), 'What evidence would change this conclusion?');
  assert.equal(nodes.get('#setup-run-title').required, false);
  assert.deepEqual(paths, ['/api/config', '/api/credentials']);
  assert.equal(nodes.get('#setup-dialog').open, true);
});

test('saving a key clears the field immediately and sends it only to the credential endpoint', async () => {
  const {evaluate, nodes, storage, context} = fixture();
  const calls = [];
  evaluate(`api = async (path, body) => { fixtureCalls.push({path, body}); return {source:'vault', vault_available:true}; };`);
  // Provide the capture through the VM rather than storing a key in browser storage.
  evaluate('fixtureCalls = []');
  nodes.get('#setup-api-key').value = 'synthetic-private-key-123456';
  context.document.querySelector('#setup-key-persistence').value = 'vault';
  const pending = evaluate('saveApiKey()');
  assert.equal(nodes.get('#setup-api-key').value, '');
  await pending;
  calls.push(...evaluate('fixtureCalls'));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/api/credentials');
  assert.equal(calls[0].body.persistence, 'vault');
  assert.equal(calls[0].body.name, 'XAI_API_KEY');
  assert.equal(nodes.get('#setup-api-key').value, '');
  assert.equal(JSON.stringify(evaluate('readSetup()')).includes('synthetic-private-key'), false);
  assert.equal([...storage.values()].some(value => String(value).includes('synthetic-private-key')), false);
});

test('Escape and dialog close clear an unsaved API key', () => {
  const {nodes} = fixture();
  nodes.get('#setup-api-key').value = 'synthetic-unsaved-key-123456';
  nodes.get('#setup-dialog').handlers.cancel();
  assert.equal(nodes.get('#setup-api-key').value, '');
  nodes.get('#setup-api-key').value = 'synthetic-unsaved-key-123456';
  nodes.get('#setup-dialog').handlers.close();
  assert.equal(nodes.get('#setup-api-key').value, '');
});

test('failed key removal invalidates earlier setup approval', async () => {
  const {evaluate, nodes} = fixture();
  evaluate(`state.validatedKey = JSON.stringify(readSetup()); api = async () => { throw new Error('Host credential vault could not remove this key.'); };`);
  nodes.get('#setup-api-key').value = 'synthetic-unsaved-key-123456';
  await evaluate('clearApiKey()');
  assert.equal(nodes.get('#setup-api-key').value, '');
  assert.equal(evaluate('state.validatedKey'), null);
  assert.match(nodes.get('#setup-credential-status').textContent, /could not be fully verified/);
});

test('creating research derives a name from the question and does not start execution', async () => {
  const {evaluate, nodes} = fixture();
  evaluate(`$("#setup-objective").value = 'Can a smaller model reproduce the measured result?'`);
  evaluate(`let requests = []; api = async (path, body) => { requests.push({path, body}); return {run: {id: 'idle-run'}}; };
    selectRun = async () => {}; refresh = async () => {}; state.validatedKey = JSON.stringify(readSetup());`);
  await evaluate('createLive({preventDefault(){}})');
  assert.equal(evaluate('requests.length'), 1);
  assert.equal(evaluate('requests[0].path'), '/api/runs');
  assert.equal(evaluate('requests[0].body.title'), 'Can a smaller model reproduce the measured result?');
  assert.equal(nodes.get('#setup-dialog').open, false);
});


test('malformed AI command suggestions remain inspectable and do not hide blockers', () => {
  const {evaluate,nodes} = fixture();
  evaluate(`renderProposal({id:'malformed',status:'complete',model:'fixture',usage:{cost_usd:0.01},proposal:{summary:'Review required',suggestions:[{field:'project.baseline_argv',value:['python3',{bad:'argument'}],reason:'Unverified',evidence:['README.md']}],questions:[],blockers:['The launcher needs integration'],drafts:[]}})`);
  assert.ok(nodes.get('#onboarding-result').children.some(node => node.textContent === 'The launcher needs integration'));
  assert.match(evaluate("suggestionValue({field:'project.baseline_argv',value:['python3',{bad:'argument'}]})"), /bad/);
});

const templeSource = readFileSync(new URL('../src/autoresearch/static/temple.js', import.meta.url), 'utf8');
const templeScene = JSON.parse(readFileSync(new URL('../src/autoresearch/static/temple.json', import.meta.url), 'utf8'));

test('temple stones fall monotonically and all settle before the animation stops', () => {
  const context = {scene: templeScene};
  runInNewContext(templeSource, context);
  assert.equal(runInNewContext('scene.blocks.every(b => Temple.placement(b, scene.duration, scene).lift === 0)', context), true);
  assert.equal(runInNewContext('Temple.polygons(scene, 0, scene.yaw, scene.pitch).length', context), 0);
  assert.ok(runInNewContext('Temple.polygons(scene, scene.duration, scene.yaw, scene.pitch).length', context) > 500);
  assert.equal(runInNewContext(`scene.blocks.every(b => {
    const start = Temple.placement(b, b[6], scene);
    const mid = Temple.placement(b, b[6] + scene.fall_seconds / 2, scene);
    return start.visible && start.lift > mid.lift && mid.lift > 0;
  })`, context), true);
});

test('temple pauses offscreen, supports pointer and keyboard rotation, and respects reduced motion', () => {
  function node() {
    return {handlers: {}, textContent: '', disabled: false, clientWidth: 0, clientHeight: 0,
      addEventListener(name, fn) { this.handlers[name] = fn; }, setAttribute() {},
      getContext() { return {}; }, setPointerCapture() {}, focus() {}, classList: {add() {}}};
  }
  const canvas = node(), replay = node();
  const root = {...node(), querySelector(selector) { return {canvas, '[data-temple-replay]': replay}[selector]; }};
  const media = {matches: false, addEventListener(_, fn) { this.change = fn; }};
  const document = {hidden: false, handlers: {}, querySelector() { return null; }, documentElement: {}, addEventListener(name, fn) { this.handlers[name] = fn; }};
  let observer, scheduled = new Map(), id = 0;
  const context = {scene: templeScene, root, document, matchMedia: () => media,
    requestAnimationFrame(fn) { scheduled.set(++id, fn); return id; }, cancelAnimationFrame(id) { scheduled.delete(id); },
    IntersectionObserver: class { constructor(fn) { observer = fn; } observe() {} },
    ResizeObserver: class { observe() {} }, MutationObserver: class { observe() {} },
  };
  runInNewContext(templeSource + '\nvar view = new Temple.View(root, scene);', context);
  const run = script => runInNewContext(script, context);
  assert.equal(scheduled.size, 0);
  observer([{isIntersecting: true}]); assert.equal(scheduled.size, 1);
  canvas.handlers.keydown({key: ' ', preventDefault() {}}); assert.equal(scheduled.size, 0);
  canvas.handlers.keydown({key: ' ', preventDefault() {}}); assert.equal(scheduled.size, 1);
  observer([{isIntersecting: false}]); assert.equal(scheduled.size, 0);
  canvas.handlers.keydown({key: 'ArrowRight', preventDefault() {}});
  assert.notEqual(run('view.yaw'), templeScene.yaw);
  canvas.handlers.pointerdown({button: 0, isPrimary: true, clientX: 0, clientY: 0, pointerId: 1});
  const yaw = run('view.yaw');
  canvas.handlers.pointermove({clientX: 50, clientY: 20, pointerId: 1});
  assert.ok(run('view.yaw') > yaw);
  canvas.handlers.pointercancel();
  const released = run('view.yaw');
  canvas.handlers.pointermove({clientX: 80, clientY: 20, pointerId: 1});
  assert.equal(run('view.yaw'), released);
  canvas.handlers.keydown({key: 'Home', preventDefault() {}}); assert.equal(run('view.yaw'), templeScene.yaw);
  media.matches = true; media.change();
  assert.equal(run('view.elapsed'), templeScene.duration);
  assert.equal(scheduled.size, 0);
  assert.ok(replay.disabled);
  replay.handlers.click(); assert.equal(run('view.elapsed'), templeScene.duration);
  media.matches = false; media.change(); replay.handlers.click();
  assert.equal(run('view.elapsed'), 0);
  observer([{isIntersecting: true}]); document.hidden = true; document.handlers.visibilitychange();
  assert.equal(scheduled.size, 0);
});


test('Google routing applies only to the form and preserves the question and edited project', async () => {
  const {evaluate, nodes, context} = fixture();
  nodes.get('#setup-source').value = '/tmp/edited-project';
  evaluate('$("#setup-objective")');
  nodes.get('#setup-objective').value = 'Preserve my question';
  context.profileCalls = [];
  evaluate(`api = async (path, body) => {
    profileCalls.push({path, body});
    return path === '/api/settings/model-profile' ? {config: {...body.config, cheap_provider: {name:'google', model:'gemini-fixture'}}} : {source:'missing', vault_available:false};
  }`);
  await evaluate('applyGoogleProfile()');
  assert.deepEqual(Array.from(context.profileCalls, c => c.path), ['/api/settings/model-profile', '/api/credentials']);
  assert.equal(nodes.get('#setup-source').value, '/tmp/edited-project');
  assert.equal(nodes.get('#setup-objective').value, 'Preserve my question');
  assert.equal(nodes.get('#setup-credential-target').value, 'google');
  assert.equal(context.profileCalls[1].body.name, 'GEMINI_API_KEY');
  assert.equal(evaluate('state.validatedKey'), null);
});

test('late Google routing cannot overwrite newer edits or unapplied JSON', async () => {
  const {evaluate, nodes} = fixture();
  evaluate('api = () => new Promise(resolve => { globalThis.finishProfile = resolve; });');
  const pending = evaluate('applyGoogleProfile()');
  nodes.get('#setup-source').value = '/tmp/newer-project';
  evaluate('invalidateSetup(); finishProfile({config: fixtureConfig});');
  await pending;
  assert.equal(nodes.get('#setup-source').value, '/tmp/newer-project');
  assert.match(nodes.get('#setup-error').textContent, /Settings changed/);
  evaluate('state.jsonDirty = true;');
  await evaluate('applyGoogleProfile()');
  assert.match(nodes.get('#setup-error').textContent, /unapplied edits/);
});

test('Laya settings round-trip and credential destinations stay out of configuration', async () => {
  const {evaluate, nodes, context} = fixture();
  nodes.get('#setup-laya-enabled').checked = true;
  nodes.get('#setup-laya-url').value = 'http://127.0.0.1:9001';
  nodes.get('#setup-laya-cost').value = '0.003';
  nodes.get('#setup-laya-key-env').value = 'CUSTOM_LAYA_KEY';
  context.keyCalls = [];
  evaluate(`api = async (path, body) => { keyCalls.push({path, body}); return {source:'session', vault_available:false}; };`);
  nodes.get('#setup-api-key').value = 'synthetic-unsaved-primary';
  nodes.get('#setup-credential-target').value = 'laya';
  nodes.get('#setup-credential-target').handlers.change();
  assert.equal(nodes.get('#setup-api-key').value, '');
  nodes.get('#setup-api-key').value = 'synthetic-laya-key';
  await evaluate('saveApiKey()');
  assert.equal(context.keyCalls.at(-1).body.name, 'CUSTOM_LAYA_KEY');
  const config = JSON.parse(evaluate('JSON.stringify(readSetup())'));
  assert.equal(config.laya.enabled, true);
  assert.equal(config.laya.base_url, 'http://127.0.0.1:9001');
  assert.equal(config.laya.cost_per_call_usd, 0.003);
  assert.equal(config.provider.api_key_env, 'XAI_API_KEY');
  assert.equal(JSON.stringify(config).includes('synthetic-laya-key'), false);
  context.savedFixture = config;
  evaluate('populateSetup(savedFixture)');
  assert.equal(nodes.get('#setup-laya-enabled').checked, true);
  assert.equal(nodes.get('#setup-laya-details').open, true);
});

for (const operation of ['saveApiKey', 'clearApiKey']) {
  test(`${operation} ignores a result for an old credential destination`, async () => {
    const {evaluate, nodes} = fixture();
    nodes.get('#setup-credential-target').value = 'primary';
    nodes.get('#setup-api-key').value = 'synthetic-old-key';
    evaluate('api = () => new Promise(resolve => { globalThis.finishKey = resolve; });');
    const pending = evaluate(`${operation}()`);
    assert.equal(nodes.get('#setup-credential-target').disabled, true);
    nodes.get('#setup-credential-target').value = 'google';
    nodes.get('#setup-api-key').value = 'synthetic-new-key';
    evaluate('$("#setup-credential-status")');
    nodes.get('#setup-credential-status').textContent = 'Google status';
    evaluate('finishKey({source:"session", vault_available:true});');
    await pending;
    assert.equal(nodes.get('#setup-credential-status').textContent, 'Google status');
    assert.equal(nodes.get('#setup-api-key').value, 'synthetic-new-key');
    assert.equal(nodes.get('#setup-credential-target').disabled, false);
  });
}

test('scope edits survive navigation and saves send only selected model overrides', async () => {
  const {evaluate, nodes, context} = fixture();
  evaluate('$("#model-settings-scope").value = "workspace";');
  context.savedScopes = [];
  evaluate(`api = async (path, body) => {
    if (path === '/api/credentials') return {source:'missing', vault_available:false};
    if (body.overrides) savedScopes.push(body);
    return {scope:body.scope, project:body.project, config:fixtureConfig, overrides:body.overrides || {}, inherited:{...fixtureConfig,laya:{enabled:false}}, revision:'revision-one'};
  };`);
  await evaluate('loadModelScope(false)');
  assert.equal(nodes.get('#setup-model').disabled, true);
  nodes.get('#model-settings-routing').checked = true;
  evaluate('updateModelScopeControls()');
  nodes.get('#setup-model').value = 'workspace-custom';
  nodes.get('#model-settings-scope').value = 'global';
  await evaluate('loadModelScope()');
  nodes.get('#model-settings-scope').value = 'workspace';
  await evaluate('loadModelScope()');
  assert.equal(nodes.get('#setup-model').value, 'workspace-custom');
  await evaluate('saveModelScope()');
  assert.equal(context.savedScopes[0].overrides.provider.model, 'workspace-custom');
  assert.equal(Object.hasOwn(context.savedScopes[0].overrides, 'project'), false);
  assert.equal(Object.hasOwn(context.savedScopes[0].overrides, 'laya'), false);
});

test('late scope loads cannot replace the selected scope and unapplied JSON cannot save', async () => {
  const {evaluate, nodes} = fixture();
  evaluate('$("#model-settings-scope").value = "workspace"; api = () => new Promise(resolve => { globalThis.finishScope = resolve; });');
  const pending = evaluate('loadModelScope(false)');
  evaluate('state.modelScopeRequest += 1; finishScope({scope:"workspace",project:"",config:fixtureConfig,overrides:{},inherited:{},revision:"old"});');
  await pending;
  assert.equal(evaluate('state.modelScope'), null);
  evaluate('state.modelJsonDirty = true');
  await evaluate('saveModelScope()');
  assert.match(nodes.get('#setup-error').textContent, /Apply model JSON/);
});

test('scope load cannot overwrite edits made while it is pending', async () => {
  const {evaluate, nodes} = fixture();
  evaluate('$("#model-settings-scope").value = "global"; api = () => new Promise(resolve => { globalThis.finishScope = resolve; });');
  const pending = evaluate('loadModelScope(false)');
  nodes.get('#setup-model').value = 'newer-edit';
  evaluate('invalidateSetup(); finishScope({scope:"global",project:"",config:fixtureConfig,overrides:{},inherited:{},revision:"old"});');
  await pending;
  assert.equal(nodes.get('#setup-model').value, 'newer-edit');
  assert.equal(evaluate('state.modelScope'), null);
});

test('pending Settings initialization cannot overwrite a newly opened inquiry', async () => {
  const {evaluate, nodes} = fixture();
  evaluate(`let loads = 0; api = async path => {
    if (path === '/api/config' && ++loads === 1) return await new Promise(resolve => {globalThis.finishOldSetup = resolve;});
    if (path === '/api/config') return {config:fixtureConfig,revision:0};
    if (path === '/api/credentials') return {source:'missing',vault_available:false};
    throw new Error('Old settings must not start a scope request');
  };`);
  const settings = evaluate('openSetup(undefined, true)');
  await evaluate('openSetup(undefined, false, "A new inquiry")');
  evaluate('finishOldSetup({config:fixtureConfig,revision:0});');
  await settings;
  assert.equal(evaluate('state.settingsMode'), false);
  assert.equal(evaluate('state.modelScope'), null);
  assert.equal(nodes.get('#setup-objective').value, 'A new inquiry');
  assert.equal(nodes.get('#setup-dialog').open, true);
});

test('new inquiry restores editable run controls without discarding model JSON draft', async () => {
  const {evaluate, nodes} = fixture();
  evaluate(`state.modelScope = {scope:'workspace',project:'',config:fixtureConfig,overrides:{},inherited:fixtureConfig,revision:'r'};
    state.settingsMode = true; state.modelJsonDirty = true;
    $('#model-settings-json').value = '{unfinished';
    updateModelScopeControls();
    api = async path => path === '/api/config' ? {config:fixtureConfig,revision:0} : {source:'missing',vault_available:false};`);
  assert.equal(nodes.get('#setup-model').disabled, true);
  await evaluate('openSetup(undefined, false, "Fresh inquiry")');
  assert.equal(nodes.get('#setup-model').disabled, false);
  assert.equal(evaluate('state.modelJsonDirty'), false);
  assert.equal(evaluate('state.modelDrafts.get("workspace:").modelJSON'), '{unfinished');
});

test('project inheritance keeps newer non-model edits and setup waits for resolution', async () => {
  const {evaluate,nodes,context} = fixture();
  context.calls = [];
  evaluate(`state.runModelOverrides = false; api = async (path,body) => {
    calls.push(path);
    if (path === '/api/settings/models') return await new Promise(resolve => {globalThis.finishProjectModels = resolve;});
    if (path === '/api/setup/recover') return {config:body.config,readiness:{ready:true,checks:[]},actions:[]};
    return {ready:true,checks:[]};
  };`);
  const pending = nodes.get('#setup-source').handlers.change();
  nodes.get('#setup-budget').value = '42';
  evaluate('invalidateSetup()');
  const validation = evaluate('validateSetup()');
  assert.deepEqual(Array.from(context.calls), ['/api/settings/models']);
  evaluate('finishProjectModels({config:{...fixtureConfig,provider:{...fixtureConfig.provider,model:"project-model"}}});');
  await pending; await validation;
  assert.equal(evaluate('readSetup().budget.usd'), 42);
  assert.equal(nodes.get('#setup-model').value, 'project-model');
});

test('validation awaiting old project defaults cannot act on a new inquiry', async () => {
  const {evaluate,context} = fixture();
  context.validationCalls = [];
  evaluate('state.projectModelPending = new Promise(resolve => {globalThis.finishOldProject = resolve;}); api = async path => {validationCalls.push(path); return {};};');
  const pending = evaluate('validateSetup()');
  evaluate('state.setupOpening += 1; state.projectModelPending = null; finishOldProject();');
  await pending;
  assert.deepEqual(Array.from(context.validationCalls), []);
});


test('folder selection fills the path, invalidates readiness and refreshes project inheritance', async () => {
  const { evaluate, nodes, context } = fixture();
  context.calls = [];
  evaluate('api = async (path, body) => { calls.push({path, body}); return {config: fixtureConfig}; }; state.validatedKey = "old";');
  await evaluate('useProjectFolder("/tmp/selected-project")');
  assert.equal(nodes.get('#setup-source').value, '/tmp/selected-project');
  assert.equal(evaluate('state.validatedKey'), null);
  assert.equal(nodes.get('#project-folder-picker').hidden, true);
  assert.equal(context.calls[0].body.project, '/tmp/selected-project');
});

test('cancelled and superseded folder browsing cannot replace the current location', async () => {
  const { evaluate, nodes, context } = fixture();
  context.pending = [];
  evaluate('api = () => new Promise(resolve => pending.push(resolve));');
  const first = evaluate('browseProjectFolders("/tmp/old")');
  const second = evaluate('browseProjectFolders("/tmp/new")');
  context.pending[1]({path: '/tmp/new', parent: '/tmp', folders: [], truncated: false});
  await second;
  context.pending[0]({path: '/tmp/old', parent: '/tmp', folders: [], truncated: false});
  await first;
  assert.equal(nodes.get('#project-folder-location').value, '/tmp/new');
  const third = evaluate('browseProjectFolders("/tmp/cancelled")');
  evaluate('closeFolderPicker()');
  context.pending[2]({path: '/tmp/cancelled', parent: '/tmp', folders: [], truncated: false});
  await third;
  assert.equal(nodes.get('#project-folder-picker').hidden, true);
  assert.equal(evaluate('state.folderSelection'), null);
});

test('folder creation keeps newer path edits and discloses the created location', async () => {
  const { evaluate, nodes, context } = fixture();
  evaluate('api = () => new Promise(resolve => { globalThis.finishFolder = resolve; });');
  const pending = evaluate('createProjectFolder()');
  nodes.get('#setup-source').value = '/tmp/new-choice';
  context.finishFolder({path: '/tmp/created'});
  assert.equal(await pending, false);
  assert.equal(nodes.get('#setup-source').value, '/tmp/new-choice');
  assert.match(nodes.get('#project-folder-status').textContent, /Created \/tmp\/created/);
});

test('blank folder is automatically created before setup checks without starting research', async () => {
  const { evaluate, nodes, context } = fixture();
  nodes.get('#setup-source').value = '';
  context.calls = [];
  evaluate(`api = async (path, body) => {
    calls.push({path, body});
    if (path === '/api/folders/create') return {path: '/tmp/automatic-project'};
    if (path === '/api/settings/models') return {config: fixtureConfig};
    return {ready: false, checks: [], guidance: []};
  };`);
  await evaluate('validateSetup()');
  assert.equal(nodes.get('#setup-source').value, '/tmp/automatic-project');
  assert.deepEqual(context.calls.map(item => item.path), ['/api/folders/create', '/api/settings/models', '/api/preflight']);
  assert.equal(context.calls[2].body.config.project.source_dir, '/tmp/automatic-project');
  assert.equal(nodes.get('#create-live').disabled, true);
});

test('experiment internals live under advanced protocol with no setup mode choice', () => {
  assert.ok(!html.includes('id="onboarding-kind"'));
  assert.ok(html.indexOf('id="onboarding-manual"') > html.indexOf('data-section="data" hidden'));
});


test('folder creation errors are visible when checking setup outside Project', async () => {
  const { evaluate, nodes } = fixture();
  nodes.get('#setup-source').value = '';
  evaluate('setSetupSection("review"); api = async () => { throw new Error("Folder permission denied"); };');
  await evaluate('validateSetup()');
  assert.equal(nodes.get('#setup-error').hidden, false);
  assert.match(nodes.get('#setup-error').textContent, /Folder permission denied/);
  assert.equal(nodes.get('#project-folder-create').disabled, false);
});

test('inspection retry reveals its containing disclosure', async () => {
  const { evaluate, nodes } = fixture();
  evaluate('api = async () => ({source_dir: "/tmp/project", files: [], documents: [], warnings: [], candidates: {}});');
  await evaluate('inspectProject()');
  assert.equal(nodes.get('#onboarding-existing').open, true);
});
