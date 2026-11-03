// Terminal-free catalog package actions. Consent is never restored or auto-submitted.
let packageJob={status:'idle'};
let packageView=0;
let packagePoll=null;
let packageReturnFocus=null;

function packageIsOpen(){ return !document.getElementById('packageOverlay').classList.contains('hidden'); }
function showPackageOverlay(){
  if(!packageIsOpen()) packageReturnFocus=document.activeElement;
  document.getElementById('packageOverlay').classList.remove('hidden');
  document.getElementById('packageClose').textContent=uiText.close;
  document.getElementById('packageClose').focus();
}
function closePackageOverlay(){
  ++packageView;
  clearTimeout(packagePoll);
  document.getElementById('packageOverlay').classList.add('hidden');
  const focusTarget=packageReturnFocus?.isConnected?packageReturnFocus:document.getElementById('catalogSearch');
  if(focusTarget?.getClientRects().length) focusTarget.focus();
}
async function packageRequest(path,body){
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch(path,body===undefined?
      {cache:'no-store',signal:controller.signal}:
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
    const data=await response.json();
    if(!response.ok){ const error=new Error('Package request rejected'); error.code=response.status===403?'authorization':data.error; throw error; }
    if(!data||typeof data.status!=='string') throw new Error('Invalid package status');
    return data;
  }finally{ clearTimeout(timeout); }
}
function packageErrorText(code,operation='install'){
  const maintenance=uiText.packageMaintenance;
  if(operation!=='install'){
    const text={authorization:maintenance.denied,changes_required:maintenance.changes,
      plan_changed:maintenance.changed,failed:maintenance.failed,not_installed:maintenance.notInstalled,
      no_update:maintenance.noUpdate,interrupted:maintenance.interrupted,unsupported:maintenance.unsupported,
      unavailable:maintenance.unsupported}[code];
    if(text) return text;
  }
  return ({network:uiText.packageNetwork,authorization:uiText.packageAuthorization,
    busy:uiText.packageBusy,not_found:uiText.packageNotFound,unsupported:uiText.packageUnsupported,
    unavailable:uiText.packageUnsupported,changes_required:uiText.packageChanges,
    plan_changed:uiText.packageChanged,interrupted:uiText.packageInterrupted,storage:uiText.packageStorage})[code]||uiText.packageFailed;
}
function packageAction(label,callback){
  const button=document.getElementById('packageAction');
  button.textContent=label; button.onclick=callback; button.disabled=false; button.hidden=false;
}
function renderPackageJob(){
  const job=packageJob;
  const rec=recommendations.find(item=>item.id===job.appId);
  const operation=job.operation||'install';
  const maintenance=uiText.packageMaintenance;
  const isRemoval=operation==='remove';
  const isUpdate=operation==='update';
  document.getElementById('packageTitle').textContent=rec?catalogName(rec):uiText.packageStatus;
  const message=document.getElementById('packageMessage');
  const progress=document.getElementById('packageProgress');
  const summary=document.getElementById('packageSummary');
  const details=document.getElementById('packageDetails');
  const hint=document.getElementById('packageHint');
  document.getElementById('packageAction').hidden=true;
  progress.hidden=true; summary.hidden=true; details.hidden=true; hint.textContent='';
  if(job.status==='checking'||job.status==='installing'){
    const checking=job.recovered?maintenance.reconnecting:operation==='install'?uiText.packageCheck:maintenance.checking;
    const running=isRemoval?maintenance.removing:isUpdate?maintenance.updating:uiText.packageInstalling;
    const authorization=operation==='install'?uiText.packageAuth:maintenance.auth;
    const text=job.status==='checking'?checking:
      ({authorization,waiting:uiText.packageWaiting,downloading:uiText.packageDownloading,checking})[job.phase]||running;
    renderUiState(message,'loading',text);
    progress.hidden=false; progress.setAttribute('aria-label',text);
    if(Number.isFinite(job.percent)) progress.value=job.percent; else progress.removeAttribute('value');
    hint.textContent=operation==='install'?uiText.packageKeepOpen:maintenance.keepOpen;
  }else if(job.status==='ready'){
    renderUiState(message,'success',isRemoval?maintenance.removeReview:isUpdate?maintenance.updateReview:uiText.packageReview);
    const packages=Array.isArray(job.packages)?job.packages:[];
    const size=Number.isFinite(job.downloadBytes)?
      new Intl.NumberFormat(cfg.language,{maximumFractionDigits:1}).format(job.downloadBytes/1048576)+' MB':uiText.packageUnknownSize;
    const facts=[localizedCount('packageCount',packages.length)];
    if(!isRemoval) facts.unshift(uiText.packageDownload.replace('{size}',size));
    if(job.currentVersion) facts.push(job.targetVersion?
      maintenance.versions.replace('{current}',()=>job.currentVersion).replace('{target}',()=>job.targetVersion):
      maintenance.version.replace('{current}',()=>job.currentVersion));
    summary.textContent=facts.join(' · ');
    summary.hidden=false; details.hidden=false;
    document.getElementById('packageDetailsLabel').textContent=uiText.packageList;
    const list=document.getElementById('packageList'); list.replaceChildren();
    for(const name of packages.slice(0,200)){ const item=document.createElement('li'); item.textContent=name; list.appendChild(item); }
    hint.textContent=isRemoval?maintenance.removeConsent:isUpdate?maintenance.consent:uiText.packageConsent;
    packageAction(isRemoval?maintenance.removeNow:isUpdate?maintenance.updateNow:uiText.packageConfirm,confirmPackageOperation);
  }else if(job.status==='complete'){
    renderUiState(message,'success',isRemoval?maintenance.removed:isUpdate?maintenance.updated:uiText.packageComplete);
    if(operation==='install'&&rec&&!catalogAdded(rec)){
      packageAction(uiText.packageAdd,()=>addInstalledPackageTile(rec));
    }
  }else if(job.status==='idle'){
    renderUiState(message,'empty',uiText.packageStatus);
  }else{
    const code=job.error||'interrupted';
    renderUiState(message,code==='no_update'?'empty':'error',packageErrorText(code,operation),
      code==='no_update'?null:()=>rec?preparePackageOperation(rec,operation):refreshPackageStatus());
  }
}
function renderPackageConnectionError(error){
  const message=document.getElementById('packageMessage');
  document.getElementById('packageAction').hidden=true;
  document.getElementById('packageProgress').hidden=true;
  for(const id of ['packageSummary','packageDetails']) document.getElementById(id).hidden=true;
  document.getElementById('packageHint').textContent='';
  renderUiState(message,'error',packageErrorText(error.code||'interrupted',packageJob.operation),()=>refreshPackageStatus());
}
async function pollPackageStatus(view){
  try{
    const job=await packageRequest('/api/packages/status');
    if(view!==packageView||!packageIsOpen()) return;
    packageJob=job; renderPackageJob();
    if(job.status==='checking'||job.status==='installing'){
      packagePoll=setTimeout(()=>pollPackageStatus(view),750);
    }else if(job.status==='complete'){
      await Promise.all([loadRecommendations(),loadApps()]);
      if(view===packageView&&packageIsOpen()) renderPackageJob();
    }
  }catch(error){ if(view===packageView&&packageIsOpen()) renderPackageConnectionError(error); }
}
function refreshPackageStatus(){ clearTimeout(packagePoll); return pollPackageStatus(++packageView); }
function openPackageStatus(){ showPackageOverlay(); return refreshPackageStatus(); }
function triggerInstall(rec){ return preparePackageOperation(rec,'install'); }
async function preparePackageOperation(rec,operation){
  clearTimeout(packagePoll);
  const view=++packageView;
  showPackageOverlay(); packageJob={status:'checking',appId:rec.id,operation}; renderPackageJob();
  try{
    const body=operation==='install'?{appId:rec.id}:{appId:rec.id,operation};
    const job=await packageRequest('/api/packages/prepare',body);
    if(view!==packageView||!packageIsOpen()) return;
    packageJob=job; renderPackageJob();
    await pollPackageStatus(view);
  }catch(error){ if(view===packageView&&packageIsOpen()) renderPackageConnectionError(error); }
}
async function confirmPackageOperation(){
  if(packageJob.status!=='ready') return;
  const body={jobId:packageJob.jobId,confirmationToken:packageJob.confirmationToken};
  const path=packageJob.operation&&packageJob.operation!=='install'?'/api/packages/confirm':'/api/packages/install';
  const view=++packageView;
  // Disable synchronously; double clicks and lost replies must never resubmit consent.
  packageJob={...packageJob,status:'installing',phase:'authorization',percent:null}; renderPackageJob();
  try{
    const job=await packageRequest(path,body);
    if(view!==packageView||!packageIsOpen()) return;
    packageJob=job; renderPackageJob(); await pollPackageStatus(view);
  }catch(error){
    if(view!==packageView||!packageIsOpen()) return;
    // Reconcile the server-owned job, never automatically repeat the install POST.
    if(error.code==='plan_changed'||error.code==='authorization') renderPackageConnectionError(error);
    else await pollPackageStatus(view);
  }
}
async function addInstalledPackageTile(rec){
  if(cfg.tiles.some(tile=>tile.id===rec.id)) return;
  const button=document.getElementById('packageAction'); button.disabled=true;
  const tile={id:rec.id,label:catalogText(rec,'label')||rec.id,
    emoji:rec.emoji||'✨',cmd:rec.cmd||[],visible:true};
  cfg.tiles.push(tile);
  try{
    await persistConfig(); renderAll(); renderPackageJob();
  }catch(error){
    cfg.tiles=cfg.tiles.filter(item=>item!==tile);
    renderUiState(document.getElementById('packageMessage'),'error',uiText.packageAddError);
    button.disabled=false;
  }
}
document.addEventListener('keydown',event=>{
  if(!packageIsOpen()) return;
  if(event.key==='Escape'){ event.preventDefault(); event.stopImmediatePropagation(); closePackageOverlay(); return; }
  if(event.key!=='Tab') return;
  const elements=Array.from(document.querySelectorAll('#packageOverlay button:not([hidden]):not([disabled]),#packageDetails:not([hidden]) summary'))
    .filter(element=>element.getClientRects().length);
  if(!elements.length) return;
  const index=elements.indexOf(document.activeElement);
  if(index<0||(!event.shiftKey&&index===elements.length-1)||(event.shiftKey&&index===0)){
    event.preventDefault(); event.stopImmediatePropagation(); elements[event.shiftKey?elements.length-1:0].focus();
  }
},true);
