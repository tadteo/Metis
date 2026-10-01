/* Compact inventory settings. Secrets use only the host credential API. */
let inventoryView = null;
let inventoryRequest = 0;
let inventoryBusy = false;
const inventoryRoot = () => document.querySelector('#model-inventory');
function modelButton(label, action, primary = false) {
  const button = element('button', `button ${primary ? 'primary' : 'secondary'}`, label);
  button.type = 'button'; button.addEventListener('click', action); return button;
}
function inventoryStatus(status) {
  return ({configured:'Configured', key_needed:'Key needed', disabled:'Disabled', invalid_key:'Invalid key', unavailable:'Unavailable'})[status] || 'Unchecked';
}
async function openInventory(scope = 'global', project = '') {
  const request = ++inventoryRequest;
  state.setupOpening += 1; // Ignore late inquiry/setup responses.
  state.page = 'settings';
  $('#settings-page').hidden = false; $('#empty-workspace').hidden = true; $('#research').hidden = true;
  for (const node of document.querySelectorAll('#settings-page > .settings-scope-panel, #model-settings-editor, #settings-page > .advanced-setup')) node.hidden = true;
  inventoryRoot().hidden = false;
  inventoryRoot().replaceChildren(element('p', 'muted', 'Loading models…'));
  try {
    const result = await api('/api/settings/inventory', {scope, project});
    if (request !== inventoryRequest || state.page !== "settings") return;
    inventoryView = result; renderInventory(); $('#model-settings-title').focus();
  } catch (error) { if (request === inventoryRequest) inventoryRoot().replaceChildren(element('p','notice error',error.message)); }
}
function renderInventory() {
  const view = inventoryView;
  const root = inventoryRoot(); root.replaceChildren();
  const locked = view.managed && view.scope === 'global';
  const heading = element('div', 'inventory-heading');
  heading.append(element('h2', '', view.scope === 'project' ? 'Project models' : 'Available to Metis'));
  if (view.scope !== 'project') {
    const actions = element('div','button-row');
    const scope = element('select'); scope.setAttribute('aria-label', 'Model settings scope');
    for (const [value,label] of [['global','Global defaults'],['workspace','This workspace']]) { const option=element('option','',label);option.value=value;scope.append(option); }
    scope.value=view.scope;scope.addEventListener('change',()=>openInventory(scope.value));actions.append(scope);
    const add=modelButton('＋ Add model',()=>editInventoryModel(null),true);add.disabled=locked;actions.append(add);heading.append(actions);
  }
  root.append(heading);
  if (locked) root.append(element('p','muted','Global defaults are managed from your local console. Keys are local to this host.'));
  if (view.scope === 'project') { renderProjectInventory(root); return; }
  const list=element('div','inventory-list');
  for(const model of view.inventory.models) {
    const row=element('article','inventory-row');const name=element('div','inventory-name');
    name.append(element('strong','',model.label),element('span','muted',model.provider.name));
    const status=view.access.find(item=>item.id===model.id);
    const label=element('span',`inventory-status ${status?.usable?'configured':''}`,inventoryStatus(status?.status));
    label.title='Local endpoint/key configuration only; provider access is unverified.';
    const configure=modelButton('Configure',()=>editInventoryModel(model));configure.disabled=locked;
    row.append(name,label,configure);list.append(row);
  }
  if (!view.inventory.models.length) list.append(element('p','muted','No models configured.'));
  root.append(list);
  const system=element('section','inventory-system');system.append(element('h2','','System 1'));
  const row=element('div','inventory-row');const name=element('div','inventory-name');
  name.append(element('strong','','Laya'),element('span','muted','Optional decision advice'));
  const configure=modelButton('Configure',editInventoryLaya);configure.disabled=locked;
  row.append(name,element('span','inventory-status',view.config.laya.enabled?'Enabled · unverified':'Disabled'),configure);system.append(row);root.append(system);
  const footer=element('div','inventory-footer');footer.append(element('span','muted','Configured keys are local to this host. No provider request was made.'));
  footer.append(modelButton('Refresh',()=>openInventory(view.scope,view.project)));
  const advanced=element('details','advanced-setup');advanced.append(element('summary','','Advanced model settings'));
  advanced.append(modelButton('Open routing and scope settings',async()=>{inventoryRequest++;inventoryRoot().hidden=true;for(const node of document.querySelectorAll('#settings-page > .settings-scope-panel, #model-settings-editor, #settings-page > .advanced-setup'))node.hidden=false;await openSetup(undefined,true);}));
  root.append(footer,advanced);
  if(!view.automatic)root.append(element('p','muted','Existing routing is preserved. Saving a model enables automatic selection for future runs.'));
  if(view.sync && Object.values(view.sync).some(value=>typeof value==='string'?value!=='synced':value?.status==='error'||value?.error))root.append(element('p','notice','Saved locally. Some remote workspaces still need settings synchronization.'));
}
async function saveInventory(changes, view) {
  const result=await api('/api/settings/inventory',{scope:view.scope,project:view.project,revision:view.revision,changes});
  // Never paint a response over another settings scope.
  if(inventoryView===view){inventoryView=result;renderInventory();}
  return result;
}
function inventoryDialog(title) {
  const dialog=$('#inventory-dialog');dialog.replaceChildren();dialog.setAttribute('aria-label',title);
  const form=element('form'); const heading=element('div','inventory-heading');heading.append(element('h2','',title));
  heading.append(modelButton('Cancel',()=>{if(!inventoryBusy)dialog.close();}));form.append(heading);
  const error=element('p','notice error');error.hidden=true;error.setAttribute('role','alert');
  form.append(error);dialog.append(form);return {dialog,form,error};
}
function inventoryField(form,labelText,value,type='text') {
  const label=element('label','',labelText);const input=element('input');input.type=type;
  input.value=value??'';input.autocomplete='off';if(type==='password'){input.maxLength=8192;input.spellcheck=false;}
  label.append(input);form.append(label);return input;
}
function inventorySelect(form,labelText,options,value) {
  const label=element('label','',labelText);const input=element('select');for(const [key,text]of options){const option=element('option','',text);option.value=key;input.append(option);}input.value=value;label.append(input);form.append(label);return input;
}
function setInventoryBusy(form,busy){inventoryBusy=busy;for(const node of form.querySelectorAll('button,input,select'))node.disabled=busy;}
function editInventoryModel(model) {
  let view=inventoryView;
  const draftId=model?.id||crypto.randomUUID();
  const {dialog,form,error}=inventoryDialog(model?'Configure model':'Add model');
  const provider=clone(model?.provider||view.config.provider);
  const label=inventoryField(form,'Display name',model?.label||'');label.required=true;label.maxLength=120;
  const kind=inventorySelect(form,'Provider',[['xai','xAI'],['google','Google'],['openai','OpenAI'],['compatible','Other / local compatible API']],['xai','google','openai'].includes(provider.name)?provider.name:'compatible');
  const modelId=inventoryField(form,'Model ID',model?provider.model:'');modelId.required=true;
  const url=inventoryField(form,'API address',provider.base_url,'url');url.required=true;
  const keyName=inventoryField(form,'Key variable',provider.api_key_env);keyName.required=true;keyName.maxLength=128;
  const secret=inventoryField(form,'API key (leave blank to keep saved key)','','password');
  const persistence=inventorySelect(form,'Keep key',[['vault',"This host's credential vault"],['session','This server session']], 'vault');
  form.append(element('p','muted','The key is saved only on this execution host. Access is not verified by a provider request.'));
  const enabledLabel=element('label','checkbox-label');const enabled=element('input');enabled.type='checkbox';enabled.checked=model?.enabled!==false;enabledLabel.append(enabled,element('span','','Available for automatic selection'));form.append(enabledLabel);
  const prices=element('details','advanced-setup');prices.append(element('summary','','Price estimates and limits'));form.append(prices);
  const priceInputs={};for(const [key,title]of [['input_per_million','Input USD / million tokens'],['output_per_million','Output USD / million tokens'],['long_input_per_million','Long input USD / million tokens'],['long_output_per_million','Long output USD / million tokens']]){const input=inventoryField(prices,title,provider[key],'number');input.min='0';input.step='any';input.required=true;priceInputs[key]=input;}
  prices.append(element('p','muted','Selection and budgets use these estimates. Verify them with your provider.'));
  kind.addEventListener('change',()=>{const defaults={xai:['https://api.x.ai/v1','XAI_API_KEY'],google:['https://generativelanguage.googleapis.com/v1beta/openai','GEMINI_API_KEY'],openai:['https://api.openai.com/v1','OPENAI_API_KEY'],compatible:['http://127.0.0.1:8000/v1','LOCAL_MODEL_API_KEY']}[kind.value];url.value=defaults[0];keyName.value=defaults[1];secret.value='';modelId.value='';});
  keyName.addEventListener('input',()=>{secret.value='';});
  const save=element('button','button primary','Save model');save.type='submit';form.append(save);
  form.addEventListener('submit',async event=>{event.preventDefault();if(inventoryBusy)return;const key=secret.value;secret.value='';const name=keyName.value.trim();setInventoryBusy(form,true);error.hidden=true;
    try {
      const updated={id:draftId,label:label.value.trim(),enabled:enabled.checked,provider:{...provider,name:kind.value,model:modelId.value.trim(),base_url:url.value.trim(),api_key_env:name,...Object.fromEntries(Object.entries(priceInputs).map(([k,input])=>[k,Number(input.value)]))}};
      const models=view.inventory.models.filter(item=>item.id!==updated.id);models.push(updated);
      // Save validated references first; a key failure leaves a visible, unconnected model.
      const result=await saveInventory({model_inventory:{models}},view);
      view=result;
      if(key)await api('/api/credentials',{action:'save',name,secret:key,persistence:persistence.value});
      dialog.close();if(inventoryView===result)await openInventory(result.scope,result.project);
    }catch(exc){error.textContent=exc.message;error.hidden=false;}finally{setInventoryBusy(form,false);}
  });
  dialog.showModal();label.focus();
}
function editInventoryLaya() {
  let view=inventoryView;const current=view.config.laya;const {dialog,form,error}=inventoryDialog('System 1 · Laya');
  const enableLabel=element('label','checkbox-label'),enabled=element('input');enabled.type='checkbox';enabled.checked=current.enabled;enableLabel.append(enabled,element('span','','Enable optional decision advice'));form.append(enableLabel);
  const endpoint=inventoryField(form,'Service address',current.base_url,'url');endpoint.required=true;
  const model=inventoryField(form,'Model',current.model);model.required=true;
  const name=inventoryField(form,'Key variable',current.api_key_env);name.required=true;
  const secret=inventoryField(form,'Optional API key','','password');
  const persistence=inventorySelect(form,'Keep key',[['vault',"This host's credential vault"],['session','This server session']], 'vault');
  name.addEventListener('input',()=>{secret.value='';});
  const cost=inventoryField(form,'Estimated USD per request',current.cost_per_call_usd,'number');cost.min='0';cost.step='any';cost.required=true;
  form.append(element('p','muted','Separate typed advice. Research models still run. Service availability is unverified.'));
  const save=element('button','button primary','Save System 1');save.type='submit';form.append(save);
  form.addEventListener('submit',async event=>{event.preventDefault();if(inventoryBusy)return;const key=secret.value;secret.value='';const keyRef=name.value.trim();setInventoryBusy(form,true);
    try{view=await saveInventory({laya:{...current,enabled:enabled.checked,base_url:endpoint.value.trim(),model:model.value.trim(),api_key_env:keyRef,cost_per_call_usd:Number(cost.value)}},view);if(key)await api('/api/credentials',{action:'save',name:keyRef,secret:key,persistence:persistence.value});dialog.close();}
    catch(exc){error.textContent=exc.message;error.hidden=false;}finally{setInventoryBusy(form,false);}
  });dialog.showModal();enabled.focus();
}
function renderProjectInventory(root){
  const view=inventoryView;root.append(element('p','muted',view.project));
  root.append(modelButton('Return to inquiry', async()=>{showHome();$('#setup-dialog').showModal();await refreshProjectModels();$('#setup-source').focus();}));
  let allowed=view.config.allowed_models;
  const mode=inventorySelect(root,'Models',[['all','All available models'],['selected','Only selected models']],allowed===null?'all':'selected');
  const list=element('div','inventory-list');const checks=[];
  for(const model of view.inventory.models){const label=element('label','inventory-project-model');const check=element('input');check.type='checkbox';check.checked=allowed===null||allowed.includes(model.id);check.disabled=mode.value==='all';checks.push([model.id,check]);label.append(check,element('span','',model.label));list.append(label);}root.append(list);
  mode.addEventListener('change',()=>{for(const [,check]of checks)check.disabled=mode.value==='all';});
  const error=element('p','notice error');error.hidden=true;root.append(error);
  root.append(element('p','muted','Applies to future runs. Metis selects only within this list. Native manuscript models must also be permitted.'));
  const save=modelButton('Save project models',async()=>{save.disabled=true;try{allowed=mode.value==='all'?null:checks.filter(([,check])=>check.checked).map(([id])=>id);if(allowed?.length===0)throw new Error('Select at least one model.');await saveInventory({allowed_models:allowed},view);toast('Project model preferences saved.');}catch(exc){error.textContent=exc.message;error.hidden=false;}finally{save.disabled=false;}},true);root.append(save);
}
if(typeof document!=='undefined'){
  document.querySelector('#inventory-dialog').addEventListener('close',()=>{for(const input of $('#inventory-dialog').querySelectorAll('input[type="password"]'))input.value='';});
  document.querySelector('#inventory-dialog').addEventListener('cancel',event=>{if(inventoryBusy)event.preventDefault();});
  document.querySelector('#project-model-settings').addEventListener('click',()=>{const project=$('#setup-source').value.trim();if(!project){showError('#setup-error','Choose a project folder first.');return;}$('#setup-dialog').close();openInventory('project',project);});
}
