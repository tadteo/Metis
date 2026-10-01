/** Production execution view semantics using public synthetic records. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';
const source = readFileSync(new URL('../src/autoresearch/static/process.js', import.meta.url), 'utf8');
const context = {Intl, console};
runInNewContext(source + '\nglobalThis.view = ResearchProcess;', context);
const api = context.view;

test('terminal research retains last recorded phase without marking skipped work complete', () => {
  const workflow = {nodes: {subset: {phase: 'experimentation'}, manuscript: {phase: 'manuscript'}, complete: {phase: 'complete'}}};
  assert.equal(api.currentPhase({current_stage: 'complete', rows: [{kind:'stage_visit',stage:'subset'}, {kind:'stage_visit',stage:'complete'}]}, workflow), 'experimentation');
  assert.equal(api.currentPhase({current_stage: 'subset', rows: []}, workflow), 'experimentation');
  assert.equal(api.currentPhase({current_stage: 'missing', rows: []}, workflow), null);
});
test('parallel call timeline spans wall time rather than sum of calls', () => {
  const data = [{started_at:'2026-01-01T00:00:00Z', duration_seconds:10}, {started_at:'2026-01-01T00:00:02Z',duration_seconds:8}];
  assert.equal(api.timeline(data, null).seconds, 10);
  assert.equal(api.timeline([{duration_seconds:99}],null).start, null);
});
test('unknown time and cost remain unavailable; known zero remains zero', () => {
  assert.equal(api.duration(null),'—'); assert.equal(api.cost(null),'—'); assert.equal(api.cost(0),'$0.00');
  assert.equal(api.aggregate([]).cost_usd,null);
  assert.equal(api.aggregate([{duration_seconds:3,cost_usd:.2},{duration_seconds:null,cost_usd:.1,estimated:true}]).duration_seconds,null);
  assert.equal(api.aggregate([{cost_usd:.2},{cost_usd:.1,estimated:true}]).estimated,true);
});
test('trace expansion keeps retry identities and parent links instead of collapsing equal labels', () => {
  const rows = [{id:'run'}, {id:'visit1',parent_id:'run'}, {id:'call1',parent_id:'visit1',label:'critic'}, {id:'call2',parent_id:'visit1',label:'critic'}, {id:'child',parent_id:'call1'}];
  assert.equal(api.visibleRows(rows,new Set(['run'])).length,2);
  assert.deepEqual(Array.from(api.visibleRows(rows,new Set(['run','visit1'])), x=>x.row.id), ['run','visit1','call1','call2']);
  assert.equal(api.visibleRows(rows,new Set(['run','visit1','call1'])).length,5);
});
test('persisted blocked, waiting and exhausted status are never relabelled ready', () => {
  for (const status of ['blocked','waiting','budget_exhausted','completed','paused','pausing']) {
    assert.equal(api.runStatus({rows:[{kind:'run',status}]},{run:{status}}),status);
  }
  assert.equal(api.runStatus({rows:[{kind:'run',status:'ready'}]},{run:{status:'ready'},worker_error:'failed'}),'error');
});
test('a recovered unchanged snapshot replaces transient API error UI', () => {
  const context = {Intl,console,matchMedia:()=>({addEventListener(){}}),ResizeObserver:class {observe(){}},MutationObserver:class {observe(){}},document:{addEventListener(){},documentElement:{},createElement(){return {}; }},cancelAnimationFrame(){}};
  runInNewContext(source+'\nglobalThis.view=ResearchProcess;',context);
  const root={replaceChildren(){}};
  const view=new context.view.View(root,root,()=>{});
  let renders=0;view.render=()=>renders++;
  const snapshot={current_stage:'subset',rows:[{id:'run',kind:'run'}]},workflow={nodes:{subset:{phase:'experimentation'}}},detail={run:{id:'synthetic'}};
  view.update(snapshot,workflow,detail);view.update({error:'temporary'},workflow,detail);view.update(snapshot,workflow,detail);
  assert.equal(renders,2);
});

test('archived alphabetical object keys do not determine phase or task order', () => {
  const workflow = {initial:'z', nodes:{a:{phase:'experimentation',transitions:[{target:'b'}]},b:{phase:'integrity'},z:{phase:'preparation',transitions:[{target:'a'}]}}};
  assert.deepEqual(Array.from(api.phaseEntries(workflow), x=>x[0]), ['preparation','experimentation','integrity']);
  assert.equal(api.phaseEntries(workflow)[0][1][0][0],'z');
});
