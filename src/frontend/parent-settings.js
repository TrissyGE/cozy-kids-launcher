// PIN setup
async function savePin(){ const p1=document.getElementById('cfgPin').value; const p2=document.getElementById('cfgPinConfirm').value; const msg=document.getElementById('pinMsg'); msg.textContent=''; msg.style.color=''; if(!p1||p1!==p2){ msg.textContent=uiText.pinMismatch; msg.style.color='#c00'; return; } if(!/^\d{4,6}$/.test(p1)){ msg.textContent=uiText.pinPlaceholder; msg.style.color='#c00'; return; } const r=await fetch('/api/pin/set',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:p1})}); if(!r.ok){ msg.textContent=uiText.pinWrong||'PIN konnte nicht gespeichert werden'; msg.style.color='#c00'; return; } cfg.pinConfigured=true; msg.textContent=uiText.pinSaved; msg.style.color='green'; document.getElementById('cfgPin').value=''; document.getElementById('cfgPinConfirm').value=''; updatePinButton(); }
async function removePin(){ if(!cfg.pinConfigured) return; const msg=document.getElementById('pinMsg'); msg.textContent=''; msg.style.color=''; const r=await fetch('/api/pin/remove',{method:'POST'}); if(!r.ok){ msg.textContent=uiText.pinWrong||'PIN konnte nicht entfernt werden'; msg.style.color='#c00'; return; } cfg.pinConfigured=false; msg.textContent=uiText.pinRemoved; msg.style.color='green'; updatePinButton(); }
function updatePinButton(){ const setButton=document.getElementById('setPinBtn'); setIconLabel(setButton,'lock',cfg.pinConfigured?uiText.pinChange:uiText.pinSet); const btn=document.getElementById('removePinBtn'); setIconLabel(btn,'delete',uiText.pinRemove); btn.disabled=!cfg.pinConfigured; btn.style.opacity=cfg.pinConfigured?1:.5; }

function parseBrowserAllowedOrigins(value){
  const origins=[];
  for(const raw of String(value||'').split(/\r?\n/)){
    const candidate=raw.trim();
    if(!candidate) continue;
    let url;
    try{ url=new URL(candidate); }catch(e){ return null; }
    if(!['http:','https:'].includes(url.protocol)||url.username||url.password) return null;
    if(!origins.includes(url.origin)) origins.push(url.origin);
    if(origins.length>20) return null;
  }
  return origins;
}

// Update check
let installedVersion='0.0.0';
let savedUpdateTrack='stable';
async function loadUpdateTrack(){
  const select=document.getElementById('updateTrack');
  select.disabled=true;
  try{
    const response=await fetch('/api/update/channel',{cache:'no-store'});
    if(!response.ok) return;
    savedUpdateTrack=(await response.json()).channel;
    select.value=savedUpdateTrack;
    select.disabled=false;
  }catch(e){}
}
async function saveUpdateTrack(){
  const select=document.getElementById('updateTrack');
  const button=document.getElementById('checkUpdateBtn');
  const message=document.getElementById('updateMsg');
  if(button.disabled){
    select.value=savedUpdateTrack;
    return;
  }
  document.getElementById('updateRow').style.display='none';
  clearUiState(message);
  select.disabled=true;
  button.disabled=true;
  try{
    const response=await fetch('/api/update/channel',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({channel:select.value})});
    if(!response.ok) throw new Error('Update channel rejected');
    savedUpdateTrack=(await response.json()).channel;
    updateAvailable=false;
  }catch(e){
    renderUiState(message,'error',uiText.saveError);
  }finally{
    select.value=savedUpdateTrack;
    select.disabled=false;
    button.disabled=false;
  }
}
async function checkUpdate(){
  const btn=document.getElementById('checkUpdateBtn');
  const msg=document.getElementById('updateMsg');
  const updateRow=document.getElementById('updateRow');
  updateRow.style.display='none';
  btn.disabled=true;
  renderUiState(msg,'loading',uiText.updateLoading);
  try{
    const statusR=await fetch('/api/update/status',{cache:'no-store'});
    if(!statusR.ok) throw new Error('fetch failed');
    const status=await statusR.json();
    installedVersion=status.installedVersion||'0.0.0';
    document.getElementById('versionDisplay').textContent=(uiText.versionLabel||'Version')+': '+installedVersion;
    updateAvailable=Boolean(status.updateAvailable);
    if(status.updateAvailable){
      renderUiState(msg,'success',(uiText.updateAvailable||'Update available')+': '+status.latestVersion);
      updateRow.style.display='grid';
    }else{
      renderUiState(msg,'success',uiText.updateUpToDate||'Up to date');
    }
  }catch(e){
    renderUiState(msg,'error',uiText.updateError||'Update check failed',checkUpdate);
  }finally{
    btn.disabled=false;
  }
}
async function startupUpdateCheck(){
  try{
    const statusR=await fetch('/api/update/status',{cache:'no-store'});
    if(!statusR.ok) return;
    const status=await statusR.json();
    installedVersion=status.installedVersion||'0.0.0';
    if(status.updateAvailable){
      updateAvailable=true;
      renderAll();
    }
  }catch(e){}
}
let updateTriggerPending=false;
async function installUpdate(){
  if(updateTriggerPending) return;
  updateTriggerPending=true;
  const button=document.getElementById('updateNowBtn');
  try{
    if(!(await requestConfirmation(uiText.updateConfirm,uiText.updateNow))) return;
    button.disabled=true;
    const response=await fetch('/api/update',{method:'POST'});
    if(!response.ok) throw new Error('Update trigger rejected');
    const result=await response.json();
    if(result.status!=='triggered') throw new Error('Update trigger not acknowledged');
    document.getElementById('updating').classList.remove('hidden');
    // The launcher owns shutdown and execution of the accepted update trigger.
  }catch(e){
    renderUiState(document.getElementById('updateMsg'),'error',uiText.updateStartError,installUpdate);
  }finally{
    updateTriggerPending=false;
    button.disabled=false;
  }
}

const ADMIN_SECTIONS=[
  ['overview','adminOverview'],
  ['children','adminChildren'],
  ['apps','adminAppsMedia'],
  ['retro','adminRetro'],
  ['screen-time','adminScreenTime'],
  ['appearance','adminAppearance'],
  ['system','adminSystem']
];
const ADMIN_SECTION_ICONS={
  overview:'overview',
  children:'child',
  apps:'apps',
  retro:'apps',
  'screen-time':'timer',
  appearance:'appearance',
  system:'system'
};
function activateAdminSection(section,focusHeading=false){
  if(!ADMIN_SECTIONS.some(([id])=>id===section)) section='overview';
  const changed=adminSection!==section;
  adminSection=section;
  document.querySelectorAll('[data-admin-section]').forEach(button=>{
    const active=button.dataset.adminSection===section;
    button.classList.toggle('active',active);
    button.setAttribute('aria-current',active?'page':'false');
    button.tabIndex=active?0:-1;
  });
  document.querySelectorAll('[data-admin-panel]').forEach(panel=>{
    panel.hidden=panel.dataset.adminPanel!==section;
  });
  const activePanel=document.querySelector('[data-admin-panel="'+section+'"]');
  if(changed) playAdminPanelTransition(activePanel);
  if(changed&&section==='system') void loadUpdateTrack();
  if(changed&&section==='retro') void loadRetroGames();
  if(focusHeading){
    const heading=document.querySelector('[data-admin-panel="'+section+'"] .section-heading');
    if(heading) heading.focus({preventScroll:true});
  }
}
function handleAdminNavKey(event){
  if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
  const buttons=Array.from(document.querySelectorAll('[data-admin-section]'));
  let index=buttons.indexOf(document.activeElement);
  if(index<0) return;
  event.preventDefault();
  if(event.key==='Home') index=0;
  else if(event.key==='End') index=buttons.length-1;
  else{
    const step={ArrowUp:-1,ArrowDown:1,ArrowLeft:-inlineDirection(),ArrowRight:inlineDirection()}[event.key];
    index=(index+step+buttons.length)%buttons.length;
  }
  const button=buttons[index];
  activateAdminSection(button.dataset.adminSection);
  button.focus();
}
function renderAdminSections(){
  document.getElementById('adminNav').setAttribute('aria-label',uiText.adminNavLabel);
  for(const [section,labelKey] of ADMIN_SECTIONS){
    const label=uiText[labelKey];
    const button=document.querySelector('[data-admin-section="'+section+'"]');
    const heading=document.querySelector('[data-admin-panel="'+section+'"] .section-heading');
    setIconLabel(button,ADMIN_SECTION_ICONS[section],label);
    heading.textContent=label;
  }
  document.getElementById('overviewAppsLabel').textContent=uiText.adminAppsMedia;
  document.getElementById('overviewAppsValue').textContent=visibleTiles().length+' / '+cfg.tiles.length;
  document.getElementById('overviewTimerLabel').textContent=uiText.adminScreenTime;
  document.getElementById('overviewTimerValue').textContent=(cfg.timerMinutes||0)>0
    ? String(cfg.timerMinutes)+' '+uiText.timerMinutes
    : uiText.timerOff;
  document.getElementById('overviewAppearanceLabel').textContent=uiText.adminAppearance;
  document.getElementById('overviewAppearanceValue').textContent=themeLabel(cfg.theme||'{{DEFAULT_THEME}}');
  activateAdminSection(adminSection);
}
function renderAppearancePreview(){
  if(!cfg) return;
  const preview=document.getElementById('appearancePreview');
  const previewTitle=document.getElementById('appearancePreviewTitle');
  const previewGrid=document.getElementById('appearancePreviewGrid');
  if(!preview||!previewTitle||!previewGrid) return;
  const themeId=document.getElementById('cfgTheme').value||cfg.theme||'{{DEFAULT_THEME}}';
  const theme=ALL_THEMES.find(item=>item.id===themeId)||ALL_THEMES[0];
  const layout=document.getElementById('cfgLayoutMode').value==='klein'?'klein':'gross';
  const title=document.getElementById('cfgTitle').value||cfg.title||'{{DEFAULT_TITLE}}';
  const world=theme.type==='world';
  const motionInput=document.getElementById('cfgThemeMotionEnabled');
  const timeInput=document.getElementById('cfgThemeTimeOfDayEnabled');
  document.getElementById('worldThemeOptions').classList.toggle('is-disabled',!world);
  motionInput.disabled=!world;
  timeInput.disabled=!world;
  applyThemeRuntime(preview,{
    theme:theme.id,
    themeMotionEnabled:motionInput.checked,
    themeTimeOfDayEnabled:timeInput.checked
  },['launcher-preview']);
  applyAccessibilityRuntime(preview,{
    accessibilityLargeText:document.getElementById('cfgAccessibilityLargeText').checked,
    accessibilityHighContrast:document.getElementById('cfgAccessibilityHighContrast').checked,
    accessibilityReducedMotion:document.getElementById('cfgAccessibilityReducedMotion').checked,
    accessibilityKeyboardFocus:document.getElementById('cfgAccessibilityKeyboardFocus').checked
  });
  for(const token of ['--bg1','--bg2','--text','--btn','--card']){
    preview.style.removeProperty(token);
  }
  if(preview.classList.contains('access-high-contrast')){
    preview.style.background='';
  }else if(theme.id==='custom'){
    const bg1=document.getElementById('cfgCustomBg1').value||'#ffd6e8';
    const bg2=document.getElementById('cfgCustomBg2').value||'#ffeef6';
    preview.style.setProperty('--bg1',bg1);
    preview.style.setProperty('--bg2',bg2);
    preview.style.setProperty('--text',document.getElementById('cfgCustomText').value||'#5f2148');
    preview.style.setProperty('--btn',document.getElementById('cfgCustomBtn').value||'#e85a9c');
    preview.style.setProperty('--card',document.getElementById('cfgCustomCard').value||'#ffffff');
    preview.style.background='linear-gradient(180deg,'+bg1+','+bg2+')';
  }else if(theme.type==='world'){
    preview.style.background='linear-gradient(rgba(255,255,255,.12),rgba(255,255,255,.12)),url('+theme.img+') center/cover no-repeat';
  }else{
    preview.style.background=theme.gradient;
  }
  previewTitle.textContent=title;
  previewGrid.className='preview-launcher-grid '+layout;
  previewGrid.replaceChildren();
  const previewSize=layout==='klein'?9:4;
  const tiles=cfg.tiles.filter(tile=>tile.visible).slice(0,previewSize);
  if(!tiles.length){
    const empty=document.createElement('div');
    empty.className='preview-empty-state';
    empty.textContent=uiText.emptyStateText;
    previewGrid.appendChild(empty);
  }else{
    for(const tile of tiles){
      const card=document.createElement('div');
      card.className='preview-tile';
      const emoji=createTileVisual(tile.emoji,'preview-tile-emoji');
      const label=document.createElement('span');
      label.className='preview-tile-label';
      label.textContent=tile.label||'';
      card.append(emoji,label);
      previewGrid.appendChild(card);
    }
  }
  const selectedLayout=document.getElementById('cfgLayoutMode').selectedOptions[0];
  const layoutLabel=selectedLayout?selectedLayout.textContent:layout;
  preview.setAttribute('aria-label',uiText.previewTitle+': '+title+', '+themeLabel(theme.id)+', '+layoutLabel);
}
function filteredAdminTileIndexes(){
  const query=adminTileQuery.trim().toLocaleLowerCase();
  return cfg.tiles.map((tile,index)=>({tile,index})).filter(({tile})=>{
    if(adminTileVisibility==='visible'&&!tile.visible) return false;
    if(adminTileVisibility==='hidden'&&tile.visible) return false;
    if(!query) return true;
    const command=Array.isArray(tile.cmd)?tile.cmd.join(' '):String(tile.cmd||'');
    return [tile.label||'',tile.emoji||'',command].join(' ').toLocaleLowerCase().includes(query);
  }).map(({index})=>index);
}
function setAdminTileSearch(value){
  adminTileQuery=String(value||'');
  adminSelectedTileIds.clear();
  adminPage=0;
  renderAdmin();
}
function setAdminTileVisibility(value){
  adminTileVisibility=['all','visible','hidden'].includes(value)?value:'all';
  adminSelectedTileIds.clear();
  adminPage=0;
  renderAdmin();
}
function renderAdminBulkActions(filteredTileIndexes){
  const validIds=new Set(cfg.tiles.map(tile=>tile.id));
  for(const id of adminSelectedTileIds){
    if(!validIds.has(id)) adminSelectedTileIds.delete(id);
  }
  const filteredIds=filteredTileIndexes.map(index=>cfg.tiles[index].id);
  const selectedFiltered=filteredIds.filter(id=>adminSelectedTileIds.has(id)).length;
  const selectAll=document.getElementById('bulkSelectFiltered');
  document.getElementById('adminBulkToolbar').setAttribute('aria-label',uiText.appBulkActions);
  selectAll.checked=filteredIds.length>0&&selectedFiltered===filteredIds.length;
  selectAll.indeterminate=selectedFiltered>0&&selectedFiltered<filteredIds.length;
  selectAll.disabled=filteredIds.length===0;
  selectAll.closest('label').classList.toggle('disabled',selectAll.disabled);
  document.getElementById('bulkSelectFilteredLabel').textContent=uiText.appBulkSelectAll;
  document.getElementById('bulkSelectionCount').textContent=uiText.appBulkSelected
    .replace('{count}',String(adminSelectedTileIds.size));
  const disabled=adminSelectedTileIds.size===0;
  const showButton=document.getElementById('bulkShowTilesBtn');
  const hideButton=document.getElementById('bulkHideTilesBtn');
  const deleteButton=document.getElementById('bulkDeleteTilesBtn');
  setIconLabel(showButton,'show',uiText.appBulkShow);
  setIconLabel(hideButton,'hide',uiText.appBulkHide);
  setIconLabel(deleteButton,'delete',uiText.appBulkDelete);
  showButton.disabled=disabled;
  hideButton.disabled=disabled;
  deleteButton.disabled=disabled;
}
function setAdminTileSelected(tileId,selected){
  if(selected) adminSelectedTileIds.add(tileId); else adminSelectedTileIds.delete(tileId);
  renderAdminBulkActions(filteredAdminTileIndexes());
}
function toggleFilteredTileSelection(selected){
  for(const index of filteredAdminTileIndexes()){
    const tileId=cfg.tiles[index].id;
    if(selected) adminSelectedTileIds.add(tileId); else adminSelectedTileIds.delete(tileId);
  }
  renderAdmin();
}
function setSelectedTilesVisible(visible){
  if(!adminSelectedTileIds.size) return;
  for(const tile of cfg.tiles){
    if(adminSelectedTileIds.has(tile.id)) tile.visible=visible;
  }
  adminSelectedTileIds.clear();
  adminPage=0;
  renderAdmin();
}
function createAdminTile(){
  return {id:'tile-'+Date.now(),label:uiText.newTile,emoji:'✨',cmd:[''],visible:true};
}
async function deleteSelectedTiles(){
  const count=adminSelectedTileIds.size;
  if(!count||!(await requestConfirmation(uiText.appBulkDeleteConfirm.replace('{count}',String(count)),uiText.appBulkDelete))) return;
  for(const tileId of adminSelectedTileIds) removeTileSchedule(tileId);
  cfg.tiles=cfg.tiles.filter(tile=>!adminSelectedTileIds.has(tile.id));
  adminSelectedTileIds.clear();
  if(!cfg.tiles.length){
    adminTileQuery='';
    adminTileVisibility='all';
    cfg.tiles.push(createAdminTile());
  }
  adminPage=0;
  renderAll();
}

function renderCatalogStates(){
  const appState=document.getElementById('appCatalogState');
  const browserState=document.getElementById('browserCatalogState');
  const appMessages={
    loading:uiText.appCatalogLoading,
    empty:uiText.appCatalogEmpty,
    error:uiText.appCatalogError
  };
  const browserMessages={
    loading:uiText.browserCatalogLoading,
    empty:uiText.browserCatalogEmpty,
    error:uiText.browserCatalogError
  };
  if(appCatalogState==='ready') clearUiState(appState);
  else renderUiState(
    appState,
    appCatalogState,
    appMessages[appCatalogState],
    appCatalogState==='loading'?null:()=>loadApps(true)
  );
  if(browserCatalogState==='ready') clearUiState(browserState);
  else renderUiState(
    browserState,
    browserCatalogState,
    browserMessages[browserCatalogState],
    browserCatalogState==='loading'?null:()=>loadBrowsers(true)
  );
}

let mediaRootsSession=null;

function clearMediaRoots(){
  if(mediaRootsSession) mediaRootsSession.abort();
  mediaRootsSession=null;
  document.getElementById('mediaRootsInput').value='';
  document.getElementById('mediaRootsInput').disabled=true;
  document.getElementById('mediaRootsInput').readOnly=false;
  document.getElementById('mediaRootsSave').disabled=true;
  document.getElementById('mediaRootsSave').removeAttribute('aria-busy');
  document.getElementById('mediaRootsStatus').textContent='';
}

async function loadMediaRoots(){
  clearMediaRoots();
  mediaRootsSession=new AbortController();
  const {signal}=mediaRootsSession;
  try{
    const response=await fetch('/api/media/roots',{cache:'no-store',signal});
    if(!response.ok) throw new Error('Media folders unavailable');
    const {roots}=await response.json();
    if(!Array.isArray(roots)||roots.some(root=>typeof root!=='string')) throw new Error('Invalid media folders');
    if(signal.aborted) return;
    const input=document.getElementById('mediaRootsInput');
    input.value=roots.join('\n');
    input.disabled=false;
    document.getElementById('mediaRootsSave').disabled=false;
  }catch(e){
    if(!signal.aborted) document.getElementById('mediaRootsStatus').textContent=uiText.mediaRootsLoadError;
  }
}

async function saveMediaRoots(){
  const input=document.getElementById('mediaRootsInput');
  const button=document.getElementById('mediaRootsSave');
  const status=document.getElementById('mediaRootsStatus');
  if(!mediaRootsSession||button.disabled||button.hasAttribute('aria-busy')) return;
  const {signal}=mediaRootsSession;
  const roots=input.value.split('\n').filter(path=>path.trim());
  button.setAttribute('aria-busy','true');
  input.readOnly=true;
  status.textContent='';
  try{
    const response=await fetch('/api/media/roots',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({roots}),signal
    });
    if(response.status===400){
      if(!signal.aborted) status.textContent=uiText.mediaRootsInvalid;
      return;
    }
    if(!response.ok) throw new Error('Media folders could not be saved');
    const result=await response.json();
    if(signal.aborted) return;
    input.value=result.roots.join('\n');
    status.textContent=uiText.mediaRootsSaved;
  }catch(e){
    if(!signal.aborted) status.textContent=uiText.saveError;
  }finally{
    if(!signal.aborted){
      input.readOnly=false;
      button.removeAttribute('aria-busy');
    }
  }
}

let retroSession=null;

function clearRetroGames(){
  retroSession?.abort();
  retroSession=null;
  document.getElementById('retroRoots').value='';
  document.getElementById('retroGame').replaceChildren();
  document.getElementById('retroStatus').textContent='';
  for(const id of ['retroRoots','retroSave','retroGame','retroApprove','retroEnabled','retroCovers','retroSettingsSave']) document.getElementById(id).disabled=true;
}

async function loadRetroGames(){
  clearRetroGames();
  retroSession=new AbortController();
  const {signal}=retroSession;
  const status=document.getElementById('retroStatus');
  try{
    const response=await fetch('/api/retro/games',{cache:'no-store',signal});
    if(!response.ok) throw new Error('Retro library unavailable');
    const data=await response.json();
    if(signal.aborted) return;
    const roots=document.getElementById('retroRoots');
    roots.value=data.roots.join('\n');
    roots.disabled=false;
    document.getElementById('retroSave').disabled=false;
    for(const [id,value] of [['retroEnabled',data.enabled],['retroCovers',data.covers]]){
      const field=document.getElementById(id);
      field.checked=value;
      field.disabled=false;
    }
    document.getElementById('retroSettingsSave').disabled=false;
    const select=document.getElementById('retroGame');
    for(const game of data.games){
      if(data.approvedIds.includes(game.id)) continue;
      const option=new Option(game.title,game.id);
      option.title=game.path;
      select.appendChild(option);
    }
    select.disabled=!select.options.length;
    document.getElementById('retroApprove').disabled=select.disabled;
    status.textContent=[
      data.unavailable>0?uiText.mediaLibrarySourcesMissing:'',
      data.truncated?uiText.retroLimit:'',
      select.disabled?uiText.retroEmpty:''
    ].filter(Boolean).join(' ');
  }catch(e){
    if(!signal.aborted) status.textContent=uiText.retroUnavailable;
  }
}

async function updateRetroGames(endpoint,body,button){
  if(!retroSession||button.disabled) return;
  const {signal}=retroSession;
  button.disabled=true;
  const status=document.getElementById('retroStatus');
  try{
    const response=await fetch('/api/retro/'+endpoint,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal
    });
    if(!response.ok) throw new Error('Retro settings could not be saved');
    const data=await response.json();
    if(signal.aborted) return;
    if(data.tile){
      if(data.hub&&!cfg.tiles.some(tile=>tile.id===data.hub.id)) cfg.tiles.push(data.hub);
      const existing=cfg.tiles.find(tile=>tile.id===data.tile.id);
      if(existing) Object.assign(existing,data.tile);
      else cfg.tiles.push(data.tile);
      renderAll();
    }
    await loadRetroGames();
  }catch(e){
    if(!signal.aborted){
      button.disabled=false;
      status.textContent=uiText.saveError;
    }
  }
}

function saveRetroRoots(){
  const roots=document.getElementById('retroRoots').value.split('\n').filter(path=>path.trim());
  return updateRetroGames('games',{roots},document.getElementById('retroSave'));
}

function approveRetroGame(){
  const gameId=document.getElementById('retroGame').value;
  return updateRetroGames('approve',{gameId,profileId:cfg.activeProfileId},document.getElementById('retroApprove'));
}

function saveRetroSettings(){
  return updateRetroGames('settings',{
    profileId:cfg.activeProfileId,
    enabled:document.getElementById('retroEnabled').checked,
    covers:document.getElementById('retroCovers').checked
  },document.getElementById('retroSettingsSave'));
}

function renderRetroEmulators(){
  const container=document.getElementById('retroEmulators');
  container.replaceChildren();
  if(recommendationState!=='ready'){
    const message={
      error:uiText.recommendationsError,empty:uiText.recommendationsEmpty,loading:uiText.recommendationsLoading
    }[recommendationState];
    renderUiState(container,recommendationState,message,recommendationState==='error'?loadRecommendations:null);
    return;
  }
  for(const emulator of recommendations.filter(item=>item.retroEmulator)){
    const card=document.createElement('article');
    card.className='rec-card';
    card.dataset.retroEmulator=emulator.id;
    const name=document.createElement('h4');
    name.textContent=catalogName(emulator);
    const button=document.createElement('button');
    button.className='smallbtn';
    button.type='button';
    button.disabled=emulator.installed;
    button.textContent=emulator.installed?uiText.installed:uiText.install;
    button.onclick=()=>triggerInstall(emulator);
    card.append(name,button,catalogDetails(emulator));
    container.appendChild(card);
  }
}

function renderAdmin(){
  document.getElementById('retroEnabledLabel').textContent=uiText.retroEnabled;
  document.getElementById('retroCoversLabel').textContent=uiText.retroCovers;
  document.getElementById('retroSettingsSave').textContent=uiText.save;
  document.getElementById('retroGuide').textContent=uiText.retroGuide;
  document.getElementById('retroRootsLabel').textContent=uiText.retroRoots;
  document.getElementById('retroSave').textContent=uiText.save;
  document.getElementById('retroRefresh').textContent=uiText.retroRefresh;
  document.getElementById('retroGameLabel').textContent=uiText.retroGame;
  document.getElementById('retroApprove').textContent=uiText.retroApprove;
  document.getElementById('controllerNavigationLabel').textContent=uiText.controllerNavigationLabel;
  document.getElementById('controllerNavigationHint').textContent=uiText.controllerNavigationHint;
  document.getElementById('cfgControllerNavigation').checked=cfg.controllerNavigationEnabled===true;
  document.getElementById('mediaRootsLabel').textContent=uiText.mediaRootsLabel;
  document.getElementById('mediaRootsHint').textContent=uiText.mediaRootsHint;
  document.getElementById('mediaRootsSave').textContent=uiText.mediaRootsSave;
  document.getElementById('adminTitle').textContent=uiText.adminTitle;
  document.getElementById('cfgLanguageLabel').textContent=uiText.languageLabel;
  const languages=document.getElementById('cfgLanguage');
  languages.replaceChildren();
  for(const {code,name} of INTERFACE_LANGUAGE_REGISTRY.languages){
    const option=document.createElement('option');
    option.value=code;
    option.lang=code;
    option.textContent=name;
    languages.appendChild(option);
  }
  languages.value=normalizedInterfaceLanguage(cfg.language);
  document.getElementById('cfgTitle').placeholder=uiText.placeholderTitle;
  document.getElementById('cfgParentLabel').placeholder=uiText.placeholderParentLabel;
  document.getElementById('cfgExitLabel').placeholder=uiText.placeholderExitLabel;
  setIconLabel(document.getElementById('addTileBtn'),'add',uiText.addTile);
  setIconLabel(document.getElementById('backBtn'),'back',uiText.back);
  setIconLabel(document.getElementById('saveBtn'),'save',uiText.save);
  document.getElementById('tileSearchLabel').textContent=uiText.appSearchLabel;
  const tileSearch=document.getElementById('tileSearch');
  tileSearch.placeholder=uiText.appSearchLabel;
  tileSearch.value=adminTileQuery;
  document.getElementById('tileFilterLabel').textContent=uiText.appFilterLabel;
  document.getElementById('tileFilterAll').textContent=uiText.appFilterAll;
  document.getElementById('tileFilterVisible').textContent=uiText.appFilterVisible;
  document.getElementById('tileFilterHidden').textContent=uiText.appFilterHidden;
  document.getElementById('tileVisibilityFilter').value=adminTileVisibility;
  document.getElementById('cfgTitle').value=cfg.title||'';
  renderProfileAdmin();
  document.getElementById('cfgTheme').value=cfg.theme||'{{DEFAULT_THEME}}';
  updateThemeDisplay();
  // Custom theme controls
  const ctp=document.getElementById('customThemePanel');
  const isCustom=(cfg.theme||'')==='custom';
  ctp.style.display=isCustom?'grid':'none';
  const c=cfg.customColors||{};
  document.getElementById('cfgCustomBg1').value=c.bg1||'#ffd6e8';
  document.getElementById('cfgCustomBg2').value=c.bg2||'#ffeef6';
  document.getElementById('cfgCustomText').value=c.text||'#5f2148';
  document.getElementById('cfgCustomBtn').value=c.btn||'#e85a9c';
  document.getElementById('cfgCustomCard').value=c.card||'#ffffff';
  document.getElementById('cfgCustomBg').value=cfg.customBackground||'';
  document.getElementById('cfgLayoutMode').value=cfg.layoutMode||'{{DEFAULT_LAYOUT}}';
  document.getElementById('cfgThemeMotionEnabled').checked=cfg.themeMotionEnabled===true;
  document.getElementById('cfgThemeTimeOfDayEnabled').checked=cfg.themeTimeOfDayEnabled===true;
  document.getElementById('cfgSoundFeedbackEnabled').checked=cfg.soundFeedbackEnabled===true;
  document.getElementById('cfgSpeechFeedbackEnabled').checked=cfg.speechFeedbackEnabled===true;
  document.getElementById('cfgCelebrationEnabled').checked=cfg.celebrationEnabled===true;
  document.getElementById('cfgAccessibilityLargeText').checked=cfg.accessibilityLargeText===true;
  document.getElementById('cfgAccessibilityHighContrast').checked=cfg.accessibilityHighContrast===true;
  document.getElementById('cfgAccessibilityReducedMotion').checked=cfg.accessibilityReducedMotion===true;
  document.getElementById('cfgAccessibilityKeyboardFocus').checked=cfg.accessibilityKeyboardFocus===true;
  document.getElementById('speechFeedbackStatus').textContent=features.speechFeedbackAvailable
    ?(uiText.speechAvailable||'Local Linux speech is available on this device.')
    :(uiText.speechUnavailable||'Install Speech Dispatcher or eSpeak to use speech feedback.');
  // Browser dropdown
  const browserSel=document.getElementById('cfgBrowser');
  browserSel.innerHTML='';
  const installedBrowsers=browserOptions.filter(b=>b.installed);
  const currentBrowser=cfg.browser||'{{BROWSER_CMD}}';
  if(installedBrowsers.length===0){
    const opt=document.createElement('option');
    opt.value=currentBrowser;
    opt.textContent=currentBrowser||uiText.browserCatalogEmpty;
    browserSel.appendChild(opt);
  }else{
    for(const b of installedBrowsers){
      const opt=document.createElement('option');
      opt.value=b.name; opt.textContent=b.name;
      browserSel.appendChild(opt);
    }
  }
  browserSel.disabled=browserCatalogState!=='ready';
  if(Array.from(browserSel.options).some(option=>option.value===currentBrowser)){
    browserSel.value=currentBrowser;
  }else if(installedBrowsers.length>0){
    browserSel.value=installedBrowsers[0].name;
  }
  document.getElementById('browserHint').textContent=uiText.browserHint;
  document.getElementById('cfgParentLabel').value=cfg.parentLabel||'{{DEFAULT_PARENT_LABEL}}';
  document.getElementById('cfgExitLabel').value=cfg.exitLabel||'{{DEFAULT_EXIT_LABEL}}';
  document.getElementById('updateTrackLabel').textContent=uiText.updateTrack.label;
  document.getElementById('updateTrackStable').textContent=uiText.updateTrack.stable;
  document.getElementById('updateTrackPreview').textContent=uiText.updateTrack.preview;
  document.getElementById('updateTrackHint').textContent=uiText.updateTrack.hint;
  setIconLabel(document.getElementById('checkUpdateBtn'),'refresh',uiText.updateCheck||'Check for updates');
  document.getElementById('versionDisplay').textContent=(uiText.versionLabel||'Version')+': '+installedVersion;
  clearUiState(document.getElementById('updateMsg'));
  clearUiState(document.getElementById('saveMsg'));
  renderCatalogStates();
  updatePinButton();
  // Timer admin
  document.getElementById('timerLabel').textContent=uiText.timerLabel||'Bildschirmzeit';
  const timerSel=document.getElementById('cfgTimerMinutes');
  const timerCustom=document.getElementById('cfgTimerCustom');
  const minutes=cfg.timerMinutes||0;
  if([15,30,60].includes(minutes)){
    timerSel.value=String(minutes);
    timerCustom.style.display='none';
  }else if(minutes>0){
    timerSel.value='custom';
    timerCustom.value=String(minutes);
    timerCustom.style.display='';
  }else{
    timerSel.value='0';
    timerCustom.style.display='none';
  }
  timerSel.onchange=function(){
    timerCustom.style.display=timerSel.value==='custom'?'':'none';
  };
  const timerBtn=document.getElementById('timerToggleBtn');
  if(lastTimerStatus.active&&!lastTimerStatus.expired){
    setIconLabel(timerBtn,'timer',uiText.timerStop||'Stop');
    document.getElementById('timerStatus').textContent=(uiText.timerRemaining||'Noch {time}').replace('{time}',formatTime(lastTimerStatus.remainingSeconds));
  }else{
    setIconLabel(timerBtn,'timer',uiText.timerStart||'Start');
    document.getElementById('timerStatus').textContent='';
  }
  const filteredTileIndexes=filteredAdminTileIndexes();
  const filteredPages=Math.max(1,Math.ceil(filteredTileIndexes.length/pageSize()));
  adminPage=Math.min(Math.max(0,adminPage),filteredPages-1);
  const pageStart=adminPage*pageSize();
  const pageTileIndexes=new Set(filteredTileIndexes.slice(pageStart,pageStart+pageSize()));
  const resultCount=document.getElementById('adminTileResultCount');
  resultCount.textContent=uiText.appFilterCount
    .replace('{shown}',String(filteredTileIndexes.length))
    .replace('{total}',String(cfg.tiles.length));
  const emptyState=document.getElementById('adminTileEmptyState');
  emptyState.textContent=uiText.appFilterEmpty;
  emptyState.hidden=filteredTileIndexes.length!==0;
  const forms=document.getElementById('forms');
  forms.innerHTML='';
  cfg.tiles.forEach((tile, idx)=>{
    const row=document.createElement('div');
    row.className='tileform';
    row.style.display=pageTileIndexes.has(idx)?'grid':'none';
    const emoji=document.createElement('input');
    emoji.value=tile.emoji||'';
    emoji.onchange=e=>{ tile.emoji=e.target.value; renderAppearancePreview(); };
    const label=document.createElement('input');
    label.value=tile.label||'';
    label.onchange=e=>{ tile.label=e.target.value; renderAppearancePreview(); };
    const visibleWrap=document.createElement('label');
    visibleWrap.className='chk';
    const visible=document.createElement('input');
    visible.type='checkbox';
    visible.checked=!!tile.visible;
    visible.onchange=e=>{
      tile.visible=e.target.checked;
      renderAppearancePreview();
      if(adminTileVisibility==='all') renderAdminSections(); else renderAdmin();
    };
    visibleWrap.append(visible,' '+uiText.visible);
    const select=document.createElement('select');
    select.className='appSelect';
    const special=document.createElement('option');
    special.value='special:filme-musik';
    special.textContent=uiText.specialMedia;
    select.appendChild(special);
    const browserOpt=document.createElement('option');
    browserOpt.value='__BROWSER__';
    browserOpt.textContent='🌐 '+uiText.browserPage;
    select.appendChild(browserOpt);
    const empty=document.createElement('option');
    empty.value='';
    empty.textContent=uiText.noApp;
    select.appendChild(empty);
    for(const app of appOptions){
      const opt=document.createElement('option');
      opt.value=app.exec;
      opt.textContent=app.name;
      select.appendChild(opt);
    }

    const browserWrap=document.createElement('div');
    browserWrap.className='browserWrap';
    const urlInput=document.createElement('input');
    urlInput.dir='ltr';
    urlInput.placeholder='https://...';
    const typeSelect=document.createElement('select');
    const optEmb=document.createElement('option');
    optEmb.value='embedded';
    optEmb.textContent=uiText.webModeEmbedded;
    const optExt=document.createElement('option');
    optExt.value='external';
    optExt.textContent=uiText.webModeExternal;
    typeSelect.appendChild(optEmb);
    typeSelect.appendChild(optExt);
    const browserPrimary=document.createElement('div');
    browserPrimary.className='browser-primary';
    browserPrimary.append(urlInput,typeSelect);
    const allowlistLabel=document.createElement('label');
    allowlistLabel.className='browser-allowlist';
    const allowlistTitle=document.createElement('span');
    allowlistTitle.textContent=uiText.browserAllowlistLabel;
    const allowlistInput=document.createElement('textarea');
    allowlistInput.dir='ltr';
    allowlistInput.rows=2;
    allowlistInput.placeholder='https://media.example';
    allowlistInput.value=Array.isArray(tile.browserAllowedOrigins)
      ?tile.browserAllowedOrigins.join('\n')
      :'';
    allowlistLabel.append(allowlistTitle,allowlistInput);
    const boundaryHint=document.createElement('p');
    boundaryHint.className='muted browser-boundary-hint';
    browserWrap.append(browserPrimary,allowlistLabel,boundaryHint);

    let currentExec=Array.isArray(tile.cmd)?tile.cmd.join(' '):'';
    let isBrowser=false, browserUrl='', browserType='embedded';
    if(currentExec.startsWith('special:browser:')){
      isBrowser=true;
      browserUrl=currentExec.substring('special:browser:'.length);
      currentExec='__BROWSER__';
    }else if(currentExec.startsWith('special:external-browser:')){
      isBrowser=true;
      browserUrl=currentExec.substring('special:external-browser:'.length);
      currentExec='__BROWSER__';
      browserType='external';
    }
    select.value=currentExec;
    if(isBrowser){
      row.classList.add('has-browser');
      urlInput.value=browserUrl;
      typeSelect.value=browserType;
    }
    if(select.value!==currentExec){
      const opt=document.createElement('option');
      opt.value=currentExec;
      opt.textContent=currentExec||uiText.customCmd;
      opt.selected=true;
      select.appendChild(opt);
    }

    select.onchange=e=>{
      if(e.target.value==='__BROWSER__'){
        row.classList.add('has-browser');
        urlInput.value='';
        typeSelect.value='embedded';
      }else{
        row.classList.remove('has-browser');
        tile.cmd=[e.target.value];
        delete tile.browserAllowedOrigins;
      }
    };

    function renderBrowserBoundary(){
      const embedded=typeSelect.value==='embedded';
      allowlistLabel.hidden=!embedded;
      boundaryHint.textContent=embedded
        ?uiText.browserBoundaryEmbedded
        :uiText.browserBoundaryExternal;
    }

    function updateBrowserCmd(){
      const u=urlInput.value.trim();
      if(!u) return;
      if(typeSelect.value==='external'){
        tile.cmd=['special:external-browser:'+u];
      }else{
        tile.cmd=['special:browser:'+u];
      }
    }
    urlInput.onchange=updateBrowserCmd;
    typeSelect.onchange=()=>{ updateBrowserCmd(); renderBrowserBoundary(); };
    allowlistInput.oninput=()=>{
      const origins=parseBrowserAllowedOrigins(allowlistInput.value);
      allowlistInput.setCustomValidity(origins===null?uiText.browserAllowlistInvalid:'');
      if(origins!==null) tile.browserAllowedOrigins=origins;
    };
    renderBrowserBoundary();

    const dragHandle=document.createElement('div');
    dragHandle.className='dragHandle';
    dragHandle.textContent='⋮⋮';
    const leading=document.createElement('div');
    leading.className='tile-row-leading';
    const selected=document.createElement('input');
    selected.type='checkbox';
    selected.checked=adminSelectedTileIds.has(tile.id);
    selected.setAttribute('aria-label',uiText.appSelectTile.replace('{tile}',tile.label||uiText.newTile));
    selected.onchange=e=>setAdminTileSelected(tile.id,e.target.checked);
    const selectLabel=document.createElement('label');
    selectLabel.className='tile-select-toggle';
    selectLabel.appendChild(selected);
    leading.append(selectLabel,dragHandle);
    const del=document.createElement('button');
    del.className='smallbtn';
    setIconLabel(del,'delete',uiText.delete);
    del.onclick=()=>deleteTile(idx);

    row.draggable=true;
    row.dataset.index=String(idx);
    row.addEventListener('dragstart',e=>{
      e.dataTransfer.setData('text/plain',String(idx));
      e.dataTransfer.effectAllowed='move';
      row.classList.add('dragging');
    });
    row.addEventListener('dragend',()=>{
      row.classList.remove('dragging');
      document.querySelectorAll('.tileform').forEach(r=>r.classList.remove('drag-over'));
    });
    row.addEventListener('dragover',e=>{
      e.preventDefault();
      e.dataTransfer.dropEffect='move';
      const target=e.currentTarget;
      if(!target.classList.contains('drag-over')){
        document.querySelectorAll('.tileform').forEach(r=>r.classList.remove('drag-over'));
        target.classList.add('drag-over');
      }
    });
    row.addEventListener('dragleave',e=>{
      if(e.currentTarget===e.target) e.currentTarget.classList.remove('drag-over');
    });
    row.addEventListener('drop',e=>{
      e.preventDefault();
      const from=parseInt(e.dataTransfer.getData('text/plain'),10);
      const to=parseInt(e.currentTarget.dataset.index,10);
      document.querySelectorAll('.tileform').forEach(r=>r.classList.remove('drag-over'));
      reorderTile(from,to);
    });

    row.append(leading,emoji,label,visibleWrap,select,browserWrap,del);
    forms.appendChild(row);
  });
  renderAdminBulkActions(filteredTileIndexes);
  renderBackupOptions();
  renderAdminPageNav(filteredTileIndexes.length);
  renderRecommendations();
  renderScheduleControls();
  renderActivityDashboard();
  renderAdminSections();
  renderAppearancePreview();
}
function reorderTile(from,to){
  if(from===to||from<0||to<0||from>=cfg.tiles.length||to>=cfg.tiles.length) return;
  const[tile]=cfg.tiles.splice(from,1);
  cfg.tiles.splice(to,0,tile);
  const filteredPosition=filteredAdminTileIndexes().indexOf(to);
  adminPage=filteredPosition<0?0:Math.floor(filteredPosition/pageSize());
  renderAdmin();
}
function deleteTile(idx){ const tile=cfg.tiles[idx]; if(tile) removeTileSchedule(tile.id); cfg.tiles.splice(idx,1); if(cfg.tiles.length===0) addTile(); renderAll(); }
function addTile(){ adminTileQuery=''; adminTileVisibility='all'; adminSelectedTileIds.clear(); cfg.tiles.push(createAdminTile()); adminPage=Math.max(0,Math.ceil(cfg.tiles.length/pageSize())-1); renderAll(); }
function renderAdminPageNav(tileCount){ const nav=document.getElementById('adminPageNav'); nav.innerHTML=''; const pages=Math.max(1,Math.ceil(tileCount/pageSize())); if(pages<=1) return; const prev=document.createElement('button'); prev.className='smallbtn'; setIconLabel(prev,'nav-left',uiText.adminPagePrev); prev.onclick=()=>{ adminPage=Math.max(0,adminPage-1); renderAdmin(); }; prev.disabled=adminPage<=0; nav.appendChild(prev); const info=document.createElement('span'); info.className='muted'; info.textContent=(adminPage+1)+' / '+pages; nav.appendChild(info); const next=document.createElement('button'); next.className='smallbtn'; setIconLabel(next,'nav-right',uiText.adminPageNext); next.onclick=()=>{ adminPage=Math.min(pages-1,adminPage+1); renderAdmin(); }; next.disabled=adminPage>=pages-1; nav.appendChild(next); }
let pendingInstallCommand='';
let installRequestId=0;
async function showManualInstall(rec){
  const requestId=++installRequestId;
  pendingInstallCommand='';
  const overlay=document.getElementById('installOverlay');
  const commandBox=overlay.querySelector('.command-box');
  const message=document.getElementById('installMessage');
  commandBox.classList.add('hidden');
  document.getElementById('installCommand').textContent='';
  document.getElementById('installCopyBtn').disabled=true;
  renderUiState(message,'loading',uiText.installLoading);
  document.getElementById('installTitle').textContent=uiText.install+' '+catalogName(rec);
  const hint=catalogText(rec,'hint');
  const hintEl=document.getElementById('installHint');
  hintEl.textContent=hint||'';
  hintEl.style.display=hint?'block':'none';
  overlay.classList.remove('hidden');
  document.getElementById('installCloseBtn').focus();
  try{
    const response=await fetch('/api/install-package',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({package:rec.package})});
    if(!response.ok) throw new Error('Package instructions rejected');
    const data=await response.json();
    if(requestId!==installRequestId) return;
    if(data.status==='unsupported'){
      renderUiState(message,'empty',uiText.installUnsupported);
      return;
    }
    if(data.status!=='manual'||typeof data.command!=='string'||!data.command.trim()){
      throw new Error('Invalid package instructions');
    }
    pendingInstallCommand=data.command;
    clearUiState(message);
    message.textContent=uiText.installManual;
    message.hidden=false;
    document.getElementById('installCommand').textContent=pendingInstallCommand;
    commandBox.classList.remove('hidden');
    document.getElementById('installCopyBtn').disabled=false;
  }catch(e){
    if(requestId!==installRequestId) return;
    renderUiState(message,'error',uiText.installError,()=>showManualInstall(rec));
  }
}
function closeInstallOverlay(){ ++installRequestId; pendingInstallCommand=''; document.getElementById('installOverlay').classList.add('hidden'); }
async function copyInstallCommand(){
  if(!pendingInstallCommand) return;
  try{
    await navigator.clipboard.writeText(pendingInstallCommand);
    const btn=document.querySelector('#installOverlay .command-box .smallbtn');
    setIconLabel(btn,'save',uiText.commandCopied||'Copied!');
    setTimeout(()=>setIconLabel(btn,'copy',uiText.copyCommand||'Copy'),2000);
  }catch(e){}
}
async function autoScanRecommendations(){
  if(cfg.autoScanDone) return;
  if(cfg.pinConfigured) return;
  if(recommendationState==='error') return;
  const existingIds=new Set(cfg.tiles.map(t=>t.id));
  const existingCmds=new Set(cfg.tiles.map(t=>JSON.stringify(t.cmd||[])));
  let added=false;
  for(const rec of recommendations){
    if(rec.installOnly) continue;
    if(existingIds.has(rec.id)) continue;
    if(rec.installed && !existingCmds.has(JSON.stringify(rec.cmd||[]))){
      cfg.tiles.push({ id:rec.id, label:catalogText(rec,'label')||rec.id, emoji:rec.emoji||'✨', cmd:rec.cmd||[], visible:true });
      added=true;
    }
  }
  cfg.autoScanDone=true;
  await persistConfig();
  if(added){ renderAll(); }
}
async function persistConfig(){
  const r=await fetch('/api/save-config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
  if(!r.ok) throw new Error('Config could not be saved');
  const result=await r.json();
  if(result.config) cfg=result.config;
}
