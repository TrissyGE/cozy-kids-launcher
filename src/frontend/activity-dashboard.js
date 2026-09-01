function setActivityTrackingEnabled(enabled){
  cfg.activityTrackingEnabled=!!enabled;
  renderActivityDashboard();
}

function formatActivityDuration(seconds){
  const safeSeconds=Math.max(0,Number(seconds)||0);
  if(safeSeconds<60) return uiText.activityLessMinute;
  const minutes=Math.round(safeSeconds/60);
  if(minutes<60) return uiText.activityMinutes.replace('{count}',String(minutes));
  const hours=Math.floor(minutes/60);
  const remainder=minutes%60;
  return uiText.activityHoursMinutes
    .replace('{hours}',String(hours))
    .replace('{minutes}',String(remainder));
}

function activityDisplay(record){
  const profiles=Array.isArray(activityData.profiles)?activityData.profiles:[];
  const profile=profiles.find(item=>item.id===record.profileId);
  const tiles=profile&&Array.isArray(profile.tiles)?profile.tiles:[];
  const tile=tiles.find(item=>item.id===record.tileId);
  return {
    profileName:(profile&&profile.name)||uiText.activityUnknownProfile,
    profileAvatar:(profile&&profile.avatar)||'👤',
    tileLabel:(tile&&tile.label)||uiText.activityUnknownApp,
    tileEmoji:(tile&&tile.emoji)||'⏱️'
  };
}

function activityDate(timestamp){
  const date=new Date(Number(timestamp)*1000);
  if(Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(interfaceLanguage()==='de'?'de-DE':'en',{
    dateStyle:'medium',
    timeStyle:'short'
  }).format(date);
}

function renderActivityDashboard(){
  if(!cfg) return;
  document.getElementById('activityTitle').textContent=uiText.activityTitle;
  document.getElementById('activityHint').textContent=uiText.activityHint;
  document.getElementById('activityEnabledLabel').textContent=uiText.activityEnabled;
  const toggle=document.getElementById('cfgActivityTracking');
  toggle.checked=!!cfg.activityTrackingEnabled;
  document.getElementById('activityTrackingStatus').textContent=toggle.checked
    ? uiText.activityEnabledStatus
    : uiText.activityDisabledStatus;
  document.getElementById('activityTimeLabel').textContent=uiText.activityTime;
  document.getElementById('activityTimeValue').textContent=formatActivityDuration(activityData.totalDurationSeconds);
  document.getElementById('activityLaunchesLabel').textContent=uiText.activityLaunches;
  document.getElementById('activityLaunchesValue').textContent=String(activityData.recordCount||0);
  document.getElementById('activityRecentTitle').textContent=uiText.activityRecent;
  const exportButton=document.getElementById('activityExportBtn');
  const clearButton=document.getElementById('activityClearBtn');
  setIconLabel(exportButton,'download',uiText.activityExport);
  setIconLabel(clearButton,'delete',uiText.activityClear);
  const hasRecords=(activityData.recordCount||0)>0;
  exportButton.disabled=!hasRecords||activityState==='loading';
  clearButton.disabled=!hasRecords||activityState==='loading';

  const message=document.getElementById('activityMessage');
  const list=document.getElementById('activityRecentList');
  list.replaceChildren();
  if(activityState==='loading'){
    renderUiState(message,'loading',uiText.activityLoading);
    return;
  }
  if(activityState==='error'){
    renderUiState(message,'error',uiText.activityError,loadActivityDashboard);
    return;
  }
  if(!hasRecords){
    renderUiState(message,'empty',uiText.activityEmpty);
    return;
  }
  clearUiState(message);
  for(const record of activityData.records.slice(0,12)){
    const display=activityDisplay(record);
    const item=document.createElement('li');
    item.className='activity-item';
    const visual=createTileVisual(display.tileEmoji,'activity-item-emoji');
    const content=document.createElement('div');
    content.className='activity-item-content';
    const title=document.createElement('strong');
    title.textContent=display.tileLabel;
    const meta=document.createElement('span');
    meta.className='muted';
    meta.textContent=display.profileAvatar+' '+display.profileName+' · '+activityDate(record.startedAt);
    content.append(title,meta);
    const duration=document.createElement('strong');
    duration.className='activity-item-duration';
    duration.textContent=formatActivityDuration(record.durationSeconds);
    item.append(visual,content,duration);
    list.appendChild(item);
  }
}

async function loadActivityDashboard(){
  activityState='loading';
  renderActivityDashboard();
  try{
    const response=await fetch('/api/activity',{cache:'no-store'});
    if(!response.ok) throw new Error('activity load failed');
    const data=await response.json();
    if(!data||!Array.isArray(data.records)||!Array.isArray(data.profiles)){
      throw new Error('invalid activity response');
    }
    activityData={
      recordCount:Number.isInteger(data.recordCount)?data.recordCount:data.records.length,
      totalDurationSeconds:Number.isInteger(data.totalDurationSeconds)?data.totalDurationSeconds:0,
      records:data.records,
      profiles:data.profiles
    };
    activityState=activityData.recordCount?'ready':'empty';
  }catch(e){
    activityData={recordCount:0,totalDurationSeconds:0,records:[],profiles:[]};
    activityState='error';
  }
  renderActivityDashboard();
}

async function exportActivity(){
  const response=await fetch('/api/activity/export');
  if(!response.ok) return;
  const blob=await response.blob();
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');
  link.href=url;
  link.download='cozy-kids-activity.json';
  link.click();
  URL.revokeObjectURL(url);
}

async function clearActivity(){
  if(!(await requestConfirmation(uiText.activityClearConfirm,uiText.activityClear))) return;
  const button=document.getElementById('activityClearBtn');
  button.disabled=true;
  try{
    const response=await fetch('/api/activity/clear',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:'{}'
    });
    if(!response.ok) throw new Error('activity clear failed');
    await loadActivityDashboard();
    renderUiState(document.getElementById('activityMessage'),'success',uiText.activityClearSuccess);
  }catch(e){
    renderUiState(document.getElementById('activityMessage'),'error',uiText.activityClearError);
    button.disabled=false;
  }
}
