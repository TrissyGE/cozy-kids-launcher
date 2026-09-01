// Timer logic
let timerWarningShown=false;
function formatTime(sec){
  const m=Math.max(0,Math.floor(sec/60));
  return m+' {{TIMER_MINUTES}}';
}
async function pollTimer(){
  try{
    const r=await fetch('/api/timer/status');
    const data=await r.json();
    lastTimerStatus=data;
    const badge=document.getElementById('timerBadge');
    if(data.active){
      badge.style.display='block';
      setIconLabel(badge,'timer',formatTime(data.remainingSeconds));
      if(data.expired){
        badge.className='expired';
        setIconLabel(badge,'timer',uiText.timerExpired);
        showTimerBlock();
      }else if(data.warning && !timerWarningShown){
        badge.className='warning';
        timerWarningShown=true;
        showTimerWarning(data.remainingSeconds);
      }else if(!data.warning){
        badge.className='';
        hideTimerWarning();
      }
    }else{
      timerWarningShown=false;
      badge.style.display='none';
      hideTimerWarning();
      hideTimerBlock();
    }
  }catch(e){}
}
function showTimerWarning(remaining){
  const el=document.getElementById('timerWarning');
  if(!el.classList.contains('hidden')) return;
  document.getElementById('timerWarningTitle').textContent=uiText.timerWarningTitle||'Noch 5 Minuten!';
  document.getElementById('timerWarningText').textContent=(uiText.timerWarningText||'').replace('{time}',formatTime(remaining));
  el.classList.remove('hidden');
  setTimeout(hideTimerWarning,6000);
}
function hideTimerWarning(){
  document.getElementById('timerWarning').classList.add('hidden');
}
function showTimerBlock(){
  document.getElementById('timerBlock').classList.remove('hidden');
}
function hideTimerBlock(){
  document.getElementById('timerBlock').classList.add('hidden');
  document.getElementById('timerBlockPin').value='';
  document.getElementById('timerBlockErr').textContent='';
}
async function toggleTimer(){
  const btn=document.getElementById('timerToggleBtn');
  if(lastTimerStatus.active && !lastTimerStatus.expired){
    // Stop timer
    const r=await fetch('/api/timer/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const data=await r.json();
    if(data.valid){
      timerWarningShown=false;
      setIconLabel(btn,'timer',uiText.timerStart);
      document.getElementById('timerStatus').textContent='';
      pollTimer();
    }
  }else{
    // Start timer
    let minutes=parseInt(document.getElementById('cfgTimerMinutes').value,10);
    if(isNaN(minutes)||minutes<=0){
      minutes=parseInt(document.getElementById('cfgTimerCustom').value,10);
    }
    if(isNaN(minutes)||minutes<=0) return;
    cfg.timerMinutes=minutes;
    await persistConfig();
    timerWarningShown=false;
    const r=await fetch('/api/timer/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({minutes:minutes})});
    const data=await r.json();
    if(data.valid){
      setIconLabel(btn,'timer',uiText.timerStop);
      document.getElementById('timerStatus').textContent=uiText.timerActive;
      pollTimer();
    }
  }
}
async function extendFromBlock(minutes){
  const pin=document.getElementById('timerBlockPin').value;
  const r=await fetch('/api/timer/extend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:pin,minutes:minutes})});
  const data=await r.json();
  if(data.valid){
    timerWarningShown=false;
    hideTimerBlock();
    pollTimer();
  }else{
    document.getElementById('timerBlockErr').textContent=uiText.timerWrongPin||'Falscher PIN';
    document.getElementById('timerBlockPin').value='';
    document.getElementById('timerBlockPin').focus();
  }
}

// Touch swipe
let touchStartX=null, touchStartY=null;
function homeGestureAllowed(){
  return !document.getElementById('kids').classList.contains('hidden') &&
    document.getElementById('pin').classList.contains('hidden') &&
    document.getElementById('themeOverlay').classList.contains('hidden') &&
    document.getElementById('installOverlay').classList.contains('hidden') &&
    document.getElementById('profileOverlay').classList.contains('hidden') &&
    document.getElementById('firstRunOverlay').classList.contains('hidden') &&
    document.getElementById('availabilityBlock').classList.contains('hidden') &&
    document.getElementById('timerBlock').classList.contains('hidden') &&
    document.getElementById('timerWarning').classList.contains('hidden') &&
    document.getElementById('startOverlay').classList.contains('hidden');
}
document.addEventListener('touchstart',function(e){
  if(e.touches.length!==1||!homeGestureAllowed()){
    touchStartX=null; touchStartY=null; return;
  }
  touchStartX=e.touches[0].clientX;
  touchStartY=e.touches[0].clientY;
},false);
document.addEventListener('touchend',function(e){
  if(touchStartX===null||touchStartY===null) return;
  const startX=touchStartX, startY=touchStartY;
  touchStartX=null; touchStartY=null;
  if(!homeGestureAllowed()||e.changedTouches.length===0) return;
  const dx=e.changedTouches[0].clientX-startX;
  const dy=e.changedTouches[0].clientY-startY;
  if(Math.abs(dx)<50 || Math.abs(dy)>Math.abs(dx)) return;
  if(dx>0) changePage(-1); else changePage(1);
},false);

// Clock
function clockIconName(h){
  if(h>=5 && h<11) return 'sunrise';
  if(h>=11 && h<17) return 'sun';
  if(h>=17 && h<21) return 'sunset';
  return 'moon';
}
function updateClock(){
  const now=new Date();
  const h=now.getHours();
  const m=String(now.getMinutes()).padStart(2,'0');
  const badge=document.getElementById('clockBadge');
  setIconLabel(badge,clockIconName(h),h+':'+m);
}
setInterval(updateClock,30000);
updateClock();

// Battery
async function updateBattery(){
  const badge=document.getElementById('batteryBadge');
  if(!navigator.getBattery) return;
  try{
    const bat=await navigator.getBattery();
    const pct=Math.round(bat.level*100);
    let icon='battery';
    if(bat.charging) icon='charging';
    else if(pct<=20) icon='battery-low';
    badge.style.display='flex';
    setIconLabel(badge,icon,pct+'%');
    bat.addEventListener('levelchange',updateBattery);
    bat.addEventListener('chargingchange',updateBattery);
  }catch(e){}
}
updateBattery();

async function saveConfig(){
  const button=document.getElementById('saveBtn');
  const message=document.getElementById('saveMsg');
  button.disabled=true;
  renderUiState(message,'loading',uiText.saveLoading);
  cfg.title=document.getElementById('cfgTitle').value;
  cfg.name=document.getElementById('cfgProfileName').value.trim();
  cfg.avatar=document.getElementById('cfgProfileAvatar').value.trim();
  cfg.theme=document.getElementById('cfgTheme').value;
  cfg.layoutMode=document.getElementById('cfgLayoutMode').value;
  cfg.parentLabel=document.getElementById('cfgParentLabel').value;
  cfg.exitLabel=document.getElementById('cfgExitLabel').value;
  let minutes=parseInt(document.getElementById('cfgTimerMinutes').value,10);
  if(isNaN(minutes)||minutes<=0){
    minutes=parseInt(document.getElementById('cfgTimerCustom').value,10)||0;
  }
  cfg.timerMinutes=minutes;
  cfg.timerWarningMinutes=cfg.timerWarningMinutes||5;
  if(cfg.theme==='custom'){
    cfg.customColors={
      bg1:document.getElementById('cfgCustomBg1').value,
      bg2:document.getElementById('cfgCustomBg2').value,
      text:document.getElementById('cfgCustomText').value,
      btn:document.getElementById('cfgCustomBtn').value,
      card:document.getElementById('cfgCustomCard').value,
    };
    cfg.customBackground=document.getElementById('cfgCustomBg').value;
  }
  cfg.browser=document.getElementById('cfgBrowser').value;
  cfg.currentPage=0;
  try{
    await persistConfig();
    await pollAvailability();
    clearUiState(message);
    renderAll();
    closeAdmin();
  }catch(e){
    renderUiState(message,'error',uiText.saveError);
  }finally{
    button.disabled=false;
  }
}
async function exportConfig(){
  const r=await fetch('/api/export-config');
  const blob=await r.blob();
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;
  a.download='cozy-kids-config.json';
  a.click();
  URL.revokeObjectURL(url);
}
async function exportDiagnostics(){
  const r=await fetch('/api/diagnostics');
  if(!r.ok) return;
  const blob=await r.blob();
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;
  a.download='cozy-kids-diagnostics.json';
  a.click();
  URL.revokeObjectURL(url);
}
async function importConfig(input){
  const msg=document.getElementById('importMsg');
  msg.textContent='';
  msg.style.color='';
  if(!input.files||!input.files[0]) return;
  if(!(await requestConfirmation(uiText.importConfirm||'This will overwrite all settings. Continue?',uiText.importConfig))){ input.value=''; return; }
  try{
    const text=await input.files[0].text();
    const data=JSON.parse(text);
    const r=await fetch('/api/import-config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result=await r.json();
    if(result.status==='ok'){
      msg.textContent=uiText.importSuccess||'Config imported';
      msg.style.color='green';
      await loadConfig();
      renderAll();
    }else{
      msg.textContent=result.message||(uiText.importError||'Import failed');
      msg.style.color='#c00';
    }
  }catch(e){
    msg.textContent=uiText.invalidConfig||'Invalid config file';
    msg.style.color='#c00';
  }
  input.value='';
}
function backupLabel(backup){
  const date=new Date(backup.createdAt);
  const locale=interfaceLanguage()==='de'?'de-DE':'en-US';
  const created=Number.isNaN(date.getTime())?backup.createdAt:date.toLocaleString(locale);
  const source=backup.source==='pre-restore'?uiText.backupPreRestore:uiText.backupInstaller;
  return source+' · '+created;
}
function renderBackupOptions(){
  const select=document.getElementById('backupSelect');
  const button=document.getElementById('restoreBackupBtn');
  if(!select||!button) return;
  select.replaceChildren();
  setIconLabel(button,'restore',uiText.backupRestore);
  if(backupState!=='ready'){
    const empty=document.createElement('option');
    empty.value='';
    const labels={
      loading:uiText.backupLoading,
      empty:uiText.backupEmpty,
      error:uiText.backupLoadError
    };
    empty.textContent=labels[backupState]||uiText.backupEmpty;
    select.appendChild(empty);
    select.disabled=true;
    button.disabled=true;
    return;
  }
  for(const backup of backups){
    const option=document.createElement('option');
    option.value=backup.id;
    option.textContent=backupLabel(backup);
    select.appendChild(option);
  }
  select.disabled=false;
  button.disabled=false;
}
async function loadBackups(){
  const msg=document.getElementById('backupMsg');
  backupState='loading';
  renderBackupOptions();
  renderUiState(msg,'loading',uiText.backupLoading);
  try{
    const response=await fetch('/api/backups',{cache:'no-store'});
    if(!response.ok) throw new Error('backup list failed');
    const result=await response.json();
    backups=Array.isArray(result.backups)?result.backups:[];
    backupState=backups.length?'ready':'empty';
    renderBackupOptions();
    if(backupState==='empty') renderUiState(msg,'empty',uiText.backupEmpty,loadBackups);
    else clearUiState(msg);
  }catch(e){
    backups=[];
    backupState='error';
    renderBackupOptions();
    renderUiState(msg,'error',uiText.backupLoadError,loadBackups);
  }
}
async function restoreBackup(){
  const select=document.getElementById('backupSelect');
  const button=document.getElementById('restoreBackupBtn');
  const msg=document.getElementById('backupMsg');
  const backupId=select.value;
  if(!backupId||!(await requestConfirmation(uiText.backupConfirm,uiText.backupRestore))) return;
  button.disabled=true;
  renderUiState(msg,'loading',uiText.backupRestoring);
  try{
    const response=await fetch('/api/backups/restore',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({backupId:backupId})
    });
    const result=await response.json();
    if(!response.ok||result.status!=='ok') throw new Error('backup restore failed');
    await loadConfig();
    await loadBackups();
    renderUiState(msg,'success',uiText.backupSuccess);
  }catch(e){
    renderUiState(msg,'error',uiText.backupError);
  }finally{
    button.disabled=backupState!=='ready';
  }
}
// Keyboard navigation
let focusedTileIndex=0;
function updateTileFocus(moveFocus=true){
  const allBtns=document.querySelectorAll('#grid .tile:not(.placeholder)');
  allBtns.forEach((btn,idx)=>{
    const focused=idx===focusedTileIndex;
    btn.classList.toggle('focused',focused);
    if(focused&&moveFocus) btn.focus({preventScroll:true});
  });
}
function focusTileByDir(dir){
  const tiles=tilesForPage(cfg.currentPage);
  const cols=cfg.layoutMode==='klein'?3:2;
  if(dir==='right'){
    if((focusedTileIndex+1)%cols!==0&&focusedTileIndex+1<tiles.length) focusedTileIndex++;
  }else if(dir==='left'){
    if(focusedTileIndex%cols!==0) focusedTileIndex--;
  }else if(dir==='down'){
    if(focusedTileIndex+cols<tiles.length) focusedTileIndex+=cols;
  }else if(dir==='up'){
    if(focusedTileIndex-cols>=0) focusedTileIndex-=cols;
  }
  updateTileFocus();
}
document.addEventListener('keydown',function(e){
  if(e.key==='Escape'){
    if(!document.getElementById('availabilityBlock').classList.contains('hidden')){ e.preventDefault(); hideAvailabilityBlock(); return; }
    if(!document.getElementById('themeOverlay').classList.contains('hidden')){ e.preventDefault(); closeThemePicker(); return; }
    if(!document.getElementById('installOverlay').classList.contains('hidden')){ e.preventDefault(); closeInstallOverlay(); return; }
    if(!document.getElementById('profileOverlay').classList.contains('hidden')){ e.preventDefault(); closeProfilePicker(); return; }
    if(!document.getElementById('pin').classList.contains('hidden')){ e.preventDefault(); cancelPin(); return; }
    if(!document.getElementById('admin').classList.contains('hidden')){ e.preventDefault(); closeAdmin(); return; }
  }
  if(!document.getElementById('admin').classList.contains('hidden')) return;
  if(!document.getElementById('pin').classList.contains('hidden')) return;
  if(!document.getElementById('profileOverlay').classList.contains('hidden')) return;
  if(!document.getElementById('firstRunOverlay').classList.contains('hidden')) return;
  if(!document.getElementById('availabilityBlock').classList.contains('hidden')) return;
  if(!document.getElementById('timerBlock').classList.contains('hidden')) return;
  if(!document.getElementById('timerWarning').classList.contains('hidden')) return;
  if(!document.getElementById('startOverlay').classList.contains('hidden')) return;
  const tiles=tilesForPage(cfg.currentPage);
  if(tiles.length===0) return;
  const tileFocused=document.activeElement&&document.activeElement.matches('#grid .tile:not(.placeholder)');
  const tileKey=tileFocused&&(e.key==='ArrowRight'||e.key==='ArrowLeft'||e.key==='ArrowDown'||e.key==='ArrowUp');
  if(tileKey||e.key==='Escape'){
    e.preventDefault();
  }
  if(tileFocused&&e.key==='ArrowRight') focusTileByDir('right');
  else if(tileFocused&&e.key==='ArrowLeft') focusTileByDir('left');
  else if(tileFocused&&e.key==='ArrowDown') focusTileByDir('down');
  else if(tileFocused&&e.key==='ArrowUp') focusTileByDir('up');
  else if(e.key==='Escape') exitKids();
});

bootstrapLauncher();
