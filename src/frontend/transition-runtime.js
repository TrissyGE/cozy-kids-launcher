const COZY_RETURN_MARKER='cozyLauncherReturnV1';
const cozyMotionTimers=new WeakMap();
let cozyFocusReturn=null;
let cozyFocusReturnExpiry=null;

function cozyMotionId(value){
  return typeof value==='string'&&/^[A-Za-z0-9_-]{1,80}$/.test(value);
}

function replayMotionClass(element,className,duration=600){
  if(!element) return;
  let timers=cozyMotionTimers.get(element);
  if(!timers){
    timers=new Map();
    cozyMotionTimers.set(element,timers);
  }
  if(timers.has(className)) clearTimeout(timers.get(className));
  element.classList.remove(className);
  void element.offsetWidth;
  element.classList.add(className);
  timers.set(className,setTimeout(()=>{
    element.classList.remove(className);
    timers.delete(className);
  },duration));
}

function playLauncherPageTransition(direction){
  replayMotionClass(
    document.getElementById('grid'),
    direction<0?'page-enter-back':'page-enter-next',
    320
  );
}

function playScreenTransition(element,returning=false){
  replayMotionClass(element,returning?'screen-enter-return':'screen-enter-forward',420);
}

function playAdminPanelTransition(panel){
  replayMotionClass(panel,'admin-panel-enter',280);
}

function playFirstRunStepTransition(direction){
  replayMotionClass(
    document.getElementById('firstRunContent'),
    direction<0?'setup-step-back':'setup-step-next',
    280
  );
}

function setLaunchMotionState(overlay,state){
  if(!overlay) return;
  overlay.classList.remove('launch-starting','launch-success');
  replayMotionClass(overlay,state==='success'?'launch-success':'launch-starting',700);
}

function playLauncherReturn(tileId){
  const kids=document.getElementById('kids');
  if(!kids||kids.classList.contains('hidden')) return;
  replayMotionClass(kids,'screen-returning',720);
  const tile=Array.from(document.querySelectorAll('#grid .tile[data-tile-id]'))
    .find(element=>element.dataset.tileId===tileId);
  if(tile) replayMotionClass(tile,'return-highlight',900);
}

function rememberLauncherPageReturn(profileId,tileId){
  if(!cozyMotionId(profileId)||!cozyMotionId(tileId)) return;
  try{
    sessionStorage.setItem(COZY_RETURN_MARKER,JSON.stringify({profileId,tileId}));
  }catch(e){}
}

function playStoredLauncherReturn(profileId){
  let raw='';
  try{
    raw=sessionStorage.getItem(COZY_RETURN_MARKER)||'';
    sessionStorage.removeItem(COZY_RETURN_MARKER);
  }catch(e){ return; }
  if(!raw||raw.length>200) return;
  try{
    const marker=JSON.parse(raw);
    if(marker&&marker.profileId===profileId&&cozyMotionId(marker.tileId)){
      playLauncherReturn(marker.tileId);
    }
  }catch(e){}
}

function cancelLauncherFocusReturn(){
  cozyFocusReturn=null;
  if(cozyFocusReturnExpiry!==null) clearTimeout(cozyFocusReturnExpiry);
  cozyFocusReturnExpiry=null;
}

function armLauncherFocusReturn(tileId){
  cancelLauncherFocusReturn();
  if(!cozyMotionId(tileId)) return;
  cozyFocusReturn={tileId,armedAt:Date.now(),blurred:false};
  cozyFocusReturnExpiry=setTimeout(()=>{
    if(cozyFocusReturn&&!cozyFocusReturn.blurred) cancelLauncherFocusReturn();
  },3500);
}

function noteLauncherLostFocus(){
  if(!cozyFocusReturn||Date.now()-cozyFocusReturn.armedAt>3500) return;
  cozyFocusReturn.blurred=true;
  if(cozyFocusReturnExpiry!==null) clearTimeout(cozyFocusReturnExpiry);
  cozyFocusReturnExpiry=null;
}

function noteLauncherRegainedFocus(){
  if(!cozyFocusReturn||!cozyFocusReturn.blurred) return;
  const tileId=cozyFocusReturn.tileId;
  cancelLauncherFocusReturn();
  playLauncherReturn(tileId);
}

window.addEventListener('blur',noteLauncherLostFocus);
window.addEventListener('focus',noteLauncherRegainedFocus);
document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState==='hidden') noteLauncherLostFocus();
  else if(document.visibilityState==='visible') noteLauncherRegainedFocus();
});
