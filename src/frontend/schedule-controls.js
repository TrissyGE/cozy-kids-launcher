const SCHEDULE_DAYS=Object.freeze([
  ['monday','weekdayMonday'],
  ['tuesday','weekdayTuesday'],
  ['wednesday','weekdayWednesday'],
  ['thursday','weekdayThursday'],
  ['friday','weekdayFriday'],
  ['saturday','weekdaySaturday'],
  ['sunday','weekdaySunday']
]);
const DEFAULT_SCHEDULE_DAYS=Object.freeze(Object.fromEntries(
  SCHEDULE_DAYS.map(([day])=>[day,[{start:'07:00',end:'20:00'}]])
));

function freshSchedule(){ return {enabled:false,days:{}}; }
function populatedSchedule(){ return {enabled:true,days:structuredClone(DEFAULT_SCHEDULE_DAYS)}; }
function ensureScheduleData(){
  if(!cfg.weeklySchedule||typeof cfg.weeklySchedule!=='object') cfg.weeklySchedule=freshSchedule();
  if(!cfg.appAvailability||typeof cfg.appAvailability!=='object') cfg.appAvailability={};
}
function scheduleForApp(tileId,create=false){
  ensureScheduleData();
  if(create&&!cfg.appAvailability[tileId]) cfg.appAvailability[tileId]=freshSchedule();
  return cfg.appAvailability[tileId]||freshSchedule();
}
function setProfileScheduleEnabled(enabled){
  ensureScheduleData();
  if(enabled&&!Object.keys(cfg.weeklySchedule.days||{}).length) cfg.weeklySchedule=populatedSchedule();
  else cfg.weeklySchedule.enabled=enabled;
  renderScheduleControls();
}
function setAppScheduleEnabled(enabled){
  const tileId=selectedAppScheduleId;
  if(!tileId) return;
  const schedule=scheduleForApp(tileId,true);
  if(enabled&&!Object.keys(schedule.days||{}).length) cfg.appAvailability[tileId]=populatedSchedule();
  else schedule.enabled=enabled;
  renderScheduleControls();
}
function selectAppSchedule(tileId){ selectedAppScheduleId=tileId; renderScheduleControls(); }
function clearAppSchedule(){
  if(!selectedAppScheduleId) return;
  delete cfg.appAvailability[selectedAppScheduleId];
  renderScheduleControls();
}
function timeInput(value,label,onchange,allowEndOfDay=false){
  const input=document.createElement('input');
  input.type='text';
  input.inputMode='numeric';
  input.pattern=allowEndOfDay?'(?:[01][0-9]|2[0-3]):[0-5][0-9]|24:00':'(?:[01][0-9]|2[0-3]):[0-5][0-9]';
  input.maxLength=5;
  input.value=value;
  input.setAttribute('aria-label',label);
  input.onchange=()=>onchange(input.value);
  return input;
}
function renderScheduleEditor(container,schedule,onchange){
  container.replaceChildren();
  const days=schedule.days||{};
  for(const [day,labelKey] of SCHEDULE_DAYS){
    const row=document.createElement('section');
    row.className='schedule-day';
    const heading=document.createElement('h5');
    heading.textContent=uiText[labelKey];
    const windows=document.createElement('div');
    windows.className='schedule-windows';
    const dayWindows=Array.isArray(days[day])?days[day]:[];
    if(!dayWindows.length){
      const empty=document.createElement('span');
      empty.className='muted schedule-empty';
      empty.textContent=uiText.scheduleNoWindows;
      windows.appendChild(empty);
    }
    dayWindows.forEach((window,index)=>{
      const windowRow=document.createElement('div');
      windowRow.className='schedule-window';
      const start=timeInput(window.start,uiText[labelKey]+' – '+uiText.scheduleStart,value=>{ window.start=value; onchange(); });
      const separator=document.createElement('span');
      separator.textContent='–';
      const end=timeInput(window.end,uiText[labelKey]+' – '+uiText.scheduleEnd,value=>{ window.end=value; onchange(); },true);
      const remove=document.createElement('button');
      remove.type='button';
      remove.className='smallbtn schedule-remove';
      setIconOnly(remove,'delete',uiText.scheduleRemoveWindow);
      remove.onclick=()=>{
        dayWindows.splice(index,1);
        if(dayWindows.length) days[day]=dayWindows; else delete days[day];
        onchange();
        renderScheduleControls();
      };
      windowRow.append(start,separator,end,remove);
      windows.appendChild(windowRow);
    });
    const add=document.createElement('button');
    add.type='button';
    add.className='smallbtn schedule-add';
    setIconLabel(add,'add',uiText.scheduleAddWindow);
    const last=dayWindows[dayWindows.length-1];
    add.disabled=dayWindows.length>=4||!!(last&&last.end==='24:00');
    add.onclick=()=>{
      const nextStart=last?last.end:'08:00';
      const hour=Math.min(24,Number(nextStart.slice(0,2))+1);
      const nextEnd=hour===24?'24:00':String(hour).padStart(2,'0')+':'+nextStart.slice(3);
      if(!days[day]) days[day]=[];
      days[day].push({start:nextStart,end:nextEnd});
      onchange();
      renderScheduleControls();
    };
    row.append(heading,windows,add);
    container.appendChild(row);
  }
}
function renderScheduleControls(){
  if(!cfg) return;
  ensureScheduleData();
  document.getElementById('weeklyScheduleTitle').textContent=uiText.weeklyScheduleTitle;
  document.getElementById('weeklyScheduleHint').textContent=uiText.weeklyScheduleHint;
  document.getElementById('weeklyScheduleEnabledLabel').textContent=uiText.scheduleEnabled;
  const weeklyEnabled=document.getElementById('weeklyScheduleEnabled');
  weeklyEnabled.checked=!!cfg.weeklySchedule.enabled;
  document.getElementById('weeklyScheduleDays').hidden=!weeklyEnabled.checked;
  renderScheduleEditor(document.getElementById('weeklyScheduleDays'),cfg.weeklySchedule,()=>{});

  document.getElementById('appScheduleTitle').textContent=uiText.appScheduleTitle;
  document.getElementById('appScheduleHint').textContent=uiText.appScheduleHint;
  document.getElementById('appScheduleSelectLabel').textContent=uiText.scheduleSelectApp;
  const select=document.getElementById('appScheduleTile');
  select.replaceChildren();
  for(const tile of cfg.tiles){
    const option=document.createElement('option');
    option.value=tile.id;
    option.textContent=(tile.emoji?tile.emoji+' ':'')+(tile.label||tile.id);
    select.appendChild(option);
  }
  if(!cfg.tiles.some(tile=>tile.id===selectedAppScheduleId)) selectedAppScheduleId=cfg.tiles[0]?cfg.tiles[0].id:'';
  select.value=selectedAppScheduleId;
  const appSchedule=scheduleForApp(selectedAppScheduleId);
  const appEnabled=document.getElementById('appScheduleEnabled');
  appEnabled.checked=!!appSchedule.enabled;
  appEnabled.disabled=!selectedAppScheduleId;
  document.getElementById('appScheduleEnabledLabel').textContent=uiText.scheduleEnabled;
  const clear=document.getElementById('clearAppScheduleBtn');
  setIconLabel(clear,'delete',uiText.scheduleClearApp);
  clear.disabled=!selectedAppScheduleId||!cfg.appAvailability[selectedAppScheduleId];
  const editor=document.getElementById('appScheduleDays');
  editor.hidden=!appEnabled.checked;
  renderScheduleEditor(editor,appSchedule,()=>{
    if(selectedAppScheduleId) cfg.appAvailability[selectedAppScheduleId]=appSchedule;
  });
}
function removeTileSchedule(tileId){
  if(cfg.appAvailability) delete cfg.appAvailability[tileId];
  if(selectedAppScheduleId===tileId) selectedAppScheduleId='';
}

function blockedTileIds(){
  return new Set(Array.isArray(availabilityStatus.blockedTileIds)?availabilityStatus.blockedTileIds:[]);
}
function showAvailabilityBlock(reason='profile_schedule'){
  const overlay=document.getElementById('availabilityBlock');
  overlay.dataset.reason=reason;
  document.getElementById('availabilityBlockTitle').textContent=uiText.scheduleBlockedTitle;
  document.getElementById('availabilityBlockBody').textContent=reason==='app_schedule'?uiText.scheduleAppBlocked:uiText.scheduleProfileBlocked;
  const close=document.getElementById('availabilityBlockClose');
  setIconLabel(close,'close',uiText.close);
  close.hidden=reason!=='app_schedule';
  setIconLabel(document.getElementById('availabilityParentsBtn'),'system',uiText.scheduleOpenParents);
  setIconLabel(document.getElementById('availabilityExitBtn'),'exit',uiText.timerExit);
  overlay.classList.remove('hidden');
  (close.hidden?document.getElementById('availabilityParentsBtn'):close).focus();
}
function hideAvailabilityBlock(force=false){
  const overlay=document.getElementById('availabilityBlock');
  if(!force&&overlay.dataset.reason==='profile_schedule'&&!availabilityStatus.profileAllowed) return;
  overlay.classList.add('hidden');
}
function openParentsFromAvailability(){ hideAvailabilityBlock(true); openAdmin(); }
async function pollAvailability(){
  try{
    const response=await fetch('/api/availability/status',{cache:'no-store'});
    if(!response.ok) return;
    const data=await response.json();
    if(!data||typeof data.profileAllowed!=='boolean'||!Array.isArray(data.blockedTileIds)) return;
    const changed=data.profileAllowed!==availabilityStatus.profileAllowed||
      data.blockedTileIds.join('\n')!==availabilityStatus.blockedTileIds.join('\n');
    availabilityStatus=data;
    if(!data.profileAllowed){
      if(document.getElementById('admin').classList.contains('hidden')) showAvailabilityBlock('profile_schedule');
    }else if(document.getElementById('availabilityBlock').dataset.reason==='profile_schedule'){
      hideAvailabilityBlock(true);
    }
    if(cfg&&changed) renderKids();
  }catch(e){}
}
document.getElementById('availabilityBlock').addEventListener('keydown',event=>{
  if(event.key!=='Tab') return;
  const buttons=Array.from(document.querySelectorAll('#availabilityBlock button:not([hidden]):not([disabled])'));
  if(!buttons.length) return;
  const index=buttons.indexOf(document.activeElement);
  const next=event.shiftKey
    ? (index<=0?buttons.length-1:index-1)
    : (index<0||index===buttons.length-1?0:index+1);
  event.preventDefault();
  buttons[next].focus();
});
