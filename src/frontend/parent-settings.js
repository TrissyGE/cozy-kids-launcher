// PIN setup
async function savePin(){ const p1=document.getElementById('cfgPin').value; const p2=document.getElementById('cfgPinConfirm').value; const msg=document.getElementById('pinMsg'); msg.textContent=''; msg.style.color=''; if(!p1||p1!==p2){ msg.textContent=uiText.pinMismatch; msg.style.color='#c00'; return; } if(!/^\d{4,6}$/.test(p1)){ msg.textContent='4-6 digits'; msg.style.color='#c00'; return; } const r=await fetch('/api/pin/set',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:p1})}); if(!r.ok){ msg.textContent=uiText.pinWrong||'PIN konnte nicht gespeichert werden'; msg.style.color='#c00'; return; } cfg.pinConfigured=true; msg.textContent=uiText.pinSaved; msg.style.color='green'; document.getElementById('cfgPin').value=''; document.getElementById('cfgPinConfirm').value=''; updatePinButton(); }
async function removePin(){ if(!cfg.pinConfigured) return; const msg=document.getElementById('pinMsg'); msg.textContent=''; msg.style.color=''; const r=await fetch('/api/pin/remove',{method:'POST'}); if(!r.ok){ msg.textContent=uiText.pinWrong||'PIN konnte nicht entfernt werden'; msg.style.color='#c00'; return; } cfg.pinConfigured=false; msg.textContent=uiText.pinRemoved; msg.style.color='green'; updatePinButton(); }
function updatePinButton(){ const setButton=document.getElementById('setPinBtn'); setIconLabel(setButton,'lock',cfg.pinConfigured?uiText.pinChange:uiText.pinSet); const btn=document.getElementById('removePinBtn'); setIconLabel(btn,'delete',uiText.pinRemove); btn.disabled=!cfg.pinConfigured; btn.style.opacity=cfg.pinConfigured?1:.5; }

// Update check
let installedVersion='0.0.0';
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
async function installUpdate(){ if(!(await requestConfirmation(uiText.updateConfirm||'Close browser and install update now?',uiText.updateNow))) return; try{ await fetch('/api/update',{method:'POST'}); }catch(e){} document.getElementById('updating').classList.remove('hidden'); setTimeout(()=>{ fetch('/exit-kids',{method:'POST'}).catch(()=>{}); }, 3000); }

const ADMIN_SECTIONS=[
  ['overview','adminOverview'],
  ['children','adminChildren'],
  ['apps','adminAppsMedia'],
  ['screen-time','adminScreenTime'],
  ['appearance','adminAppearance'],
  ['system','adminSystem']
];
const ADMIN_SECTION_ICONS={
  overview:'overview',
  children:'child',
  apps:'apps',
  'screen-time':'timer',
  appearance:'appearance',
  system:'system'
};
function activateAdminSection(section,focusHeading=false){
  if(!ADMIN_SECTIONS.some(([id])=>id===section)) section='overview';
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
  else if(event.key==='ArrowUp'||event.key==='ArrowLeft') index=(index-1+buttons.length)%buttons.length;
  else index=(index+1)%buttons.length;
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
  preview.className='launcher-preview theme-'+theme.id;
  for(const token of ['--bg1','--bg2','--text','--btn','--card']){
    preview.style.removeProperty(token);
  }
  if(theme.id==='custom'){
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

function renderAdmin(){
  document.getElementById('adminTitle').textContent=uiText.adminTitle;
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
  document.getElementById('browserHint').textContent=interfaceLanguage()==='de'
    ? 'Änderung wirkt erst nach erneutem Login.'
    : 'Changes take effect after the next login.';
  document.getElementById('cfgParentLabel').value=cfg.parentLabel||'{{DEFAULT_PARENT_LABEL}}';
  document.getElementById('cfgExitLabel').value=cfg.exitLabel||'{{DEFAULT_EXIT_LABEL}}';
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
    browserWrap.appendChild(urlInput);
    browserWrap.appendChild(typeSelect);

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
      }
    };

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
    typeSelect.onchange=updateBrowserCmd;

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
function renderRecommendations(){
  const container=document.getElementById('recommendations');
  container.replaceChildren();
  const panel=document.createElement('div'); panel.className='panel';
  const headerRow=document.createElement('div'); headerRow.style.display='flex'; headerRow.style.justifyContent='space-between'; headerRow.style.alignItems='center'; headerRow.style.marginBottom='12px';
  const h2=document.createElement('h2'); h2.style.margin='0'; h2.textContent=uiText.appBrowserTitle||'App Browser';
  const refreshBtn=document.createElement('button'); refreshBtn.className='smallbtn'; setIconOnly(refreshBtn,'refresh',uiText.retry); refreshBtn.disabled=recommendationState==='loading'; refreshBtn.onclick=loadRecommendations;
  headerRow.appendChild(h2); headerRow.appendChild(refreshBtn);
  panel.appendChild(headerRow);
  container.appendChild(panel);
  if(recommendationState!=='ready'){
    const messages={
      loading:uiText.recommendationsLoading,
      empty:uiText.recommendationsEmpty,
      error:uiText.recommendationsError
    };
    const status=document.createElement('div');
    status.id='recommendationState';
    status.setAttribute('aria-live','polite');
    renderUiState(
      status,
      recommendationState,
      messages[recommendationState],
      recommendationState==='loading'?null:loadRecommendations
    );
    panel.appendChild(status);
    return;
  }
  const existingIds=new Set(cfg.tiles.map(t=>t.id));
  const existingCmds=new Set(cfg.tiles.map(t=>JSON.stringify(t.cmd||[])));
  const grid=document.createElement('div'); grid.className='rec-grid';
  const sorted=[...recommendations].sort((a,b)=>{
    const aAdded=existingIds.has(a.id)||existingCmds.has(JSON.stringify(a.cmd||[]));
    const bAdded=existingIds.has(b.id)||existingCmds.has(JSON.stringify(b.cmd||[]));
    if(aAdded!==bAdded) return aAdded?1:-1;
    if(a.installed!==b.installed) return a.installed?-1:1;
    return 0;
  });
  for(const rec of sorted){
    const card=document.createElement('div'); card.className='rec-card';
    const em=createTileVisual(rec.emoji,'emoji');
    const nm=document.createElement('div'); nm.className='name';
    nm.textContent=(cfg.language==='de'?rec.name_de:rec.name_en)||(cfg.language==='de'?rec.label_de:rec.label_en)||rec.id;
    const desc=document.createElement('div'); desc.className='desc';
    desc.textContent=(cfg.language==='de'?rec.desc_de:rec.desc_en)||'';
    const st=document.createElement('div'); st.className='status '+(rec.installed?'installed':'missing');
    st.textContent=rec.installed?(uiText.installed||'installed'):(uiText.notInstalled||'not installed');
    const actions=document.createElement('div'); actions.className='actions';
    const added=existingIds.has(rec.id)||existingCmds.has(JSON.stringify(rec.cmd||[]));
    if(added){
      const btn=document.createElement('button'); btn.className='smallbtn'; btn.disabled=true; setIconLabel(btn,'save',uiText.added||'Added');
      actions.appendChild(btn);
    } else if(rec.installed){
      const btn=document.createElement('button'); btn.className='smallbtn'; setIconLabel(btn,'add',uiText.addTile||'Add tile');
      btn.onclick=()=>{ cfg.tiles.push({ id:rec.id, label:(cfg.language==='de'?rec.label_de:rec.label_en)||rec.id, emoji:rec.emoji||'✨', cmd:rec.cmd||[], visible:true }); renderAll(); persistConfig(); };
      actions.appendChild(btn);
    } else {
      const btn=document.createElement('button'); btn.className='smallbtn'; setIconLabel(btn,'download',uiText.install||'Install');
      btn.onclick=()=>{ triggerInstall(rec); };
      actions.appendChild(btn);
    }
    card.append(em,nm,desc,st,actions);
    grid.appendChild(card);
  }
  panel.appendChild(grid);
  const disclaimer=document.createElement('div'); disclaimer.className='muted'; disclaimer.style.marginTop='14px'; disclaimer.style.fontSize='.85rem'; disclaimer.textContent=cfg.language==='de'?'Diese Programme stammen aus externen Quellen und stehen in keiner Verbindung zum Cozy Kids Launcher Projekt.':'This software comes from external sources and is not affiliated with the Cozy Kids Launcher project.';
  panel.appendChild(disclaimer);
}
let pendingInstallCommand='';
function triggerInstall(rec){
  pendingInstallCommand='sudo apt install -y '+rec.package;
  document.getElementById('installTitle').textContent=(uiText.install||'Install')+' '+((cfg.language==='de'?rec.name_de:rec.name_en)||(cfg.language==='de'?rec.label_de:rec.label_en)||rec.id);
  fetch('/api/install-package',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({package:rec.package})})
    .then(r=>r.json()).then(data=>{
      const msg=document.getElementById('installMessage');
      if(data.status==='started'){
        msg.textContent=uiText.installStarted||'Installation started. Watch for a password dialog, or run the command below:';
      } else {
        msg.textContent=uiText.installManual||'Please run this command in a terminal:';
      }
      if(data.command) pendingInstallCommand=data.command;
      document.getElementById('installCommand').textContent=pendingInstallCommand;
      const hint=cfg.language==='de'?rec.hint_de:rec.hint_en;
      const hintEl=document.getElementById('installHint');
      hintEl.textContent=hint||'';
      hintEl.style.display=hint?'block':'none';
      document.getElementById('installOverlay').classList.remove('hidden');
    }).catch(()=>{
      document.getElementById('installMessage').textContent=uiText.installManual||'Please run this command in a terminal:';
      document.getElementById('installCommand').textContent=pendingInstallCommand;
      const hint=cfg.language==='de'?rec.hint_de:rec.hint_en;
      const hintEl=document.getElementById('installHint');
      hintEl.textContent=hint||'';
      hintEl.style.display=hint?'block':'none';
      document.getElementById('installOverlay').classList.remove('hidden');
    });
}
function closeInstallOverlay(){ document.getElementById('installOverlay').classList.add('hidden'); }
async function copyInstallCommand(){
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
    if(existingIds.has(rec.id)) continue;
    if(rec.installed && !existingCmds.has(JSON.stringify(rec.cmd||[]))){
      cfg.tiles.push({ id:rec.id, label:(cfg.language==='de'?rec.label_de:rec.label_en)||rec.id, emoji:rec.emoji||'✨', cmd:rec.cmd||[], visible:true });
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
