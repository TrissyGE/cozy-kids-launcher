let confirmationResolve=null;
let confirmationReturnFocus=null;

function confirmationIsOpen(){
  return !document.getElementById('confirmOverlay').classList.contains('hidden');
}

function requestConfirmation(message,actionLabel){
  if(confirmationIsOpen()) return Promise.resolve(false);
  const overlay=document.getElementById('confirmOverlay');
  const cancelButton=document.getElementById('confirmCancelBtn');
  const actionButton=document.getElementById('confirmActionBtn');
  confirmationReturnFocus=document.activeElement;
  document.getElementById('confirmTitle').textContent=uiText.confirmTitle;
  document.getElementById('confirmMessage').textContent=String(message||'');
  setIconLabel(cancelButton,'close',uiText.confirmCancel);
  setIconLabel(actionButton,'save',actionLabel||uiText.confirmContinue);
  overlay.classList.remove('hidden');
  return new Promise(resolve=>{
    confirmationResolve=resolve;
    requestAnimationFrame(()=>cancelButton.focus());
  });
}

function resolveConfirmation(confirmed){
  const overlay=document.getElementById('confirmOverlay');
  if(overlay.classList.contains('hidden')) return;
  overlay.classList.add('hidden');
  const resolve=confirmationResolve;
  confirmationResolve=null;
  const returnFocus=confirmationReturnFocus;
  confirmationReturnFocus=null;
  if(returnFocus&&returnFocus.isConnected&&!returnFocus.disabled) returnFocus.focus();
  if(resolve) resolve(confirmed===true);
}

document.addEventListener('keydown',event=>{
  if(!confirmationIsOpen()) return;
  if(event.key==='Escape'){
    event.preventDefault();
    event.stopImmediatePropagation();
    resolveConfirmation(false);
    return;
  }
  if(event.key!=='Tab') return;
  const buttons=[
    document.getElementById('confirmCancelBtn'),
    document.getElementById('confirmActionBtn')
  ].filter(button=>!button.disabled);
  const index=buttons.indexOf(document.activeElement);
  if(index<0){
    event.preventDefault();
    event.stopImmediatePropagation();
    buttons[0].focus();
  }else if(event.shiftKey&&index===0){
    event.preventDefault();
    event.stopImmediatePropagation();
    buttons[buttons.length-1].focus();
  }else if(!event.shiftKey&&index===buttons.length-1){
    event.preventDefault();
    event.stopImmediatePropagation();
    buttons[0].focus();
  }
},true);
