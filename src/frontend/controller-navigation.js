// Shared directional navigation for the child launcher and media library.
function createControllerNavigation(getScope){
  const directions={
    ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]
  };
  let enabled=false;
  let pollId=null;
  let lastScope=null;
  let lastPad=null;
  let lastAction='';
  let activationHeld=false;
  let nextRepeat=0;
  let needsRelease=true;

  function availableButtons(scope){
    return Array.from(document.querySelectorAll(scope.buttons)).filter(button=>
      !button.disabled&&!button.closest('[hidden],.hidden,[inert]')&&button.getClientRects().length
    );
  }

  function move(key,buttons,focused){
    if(!focused){
      buttons[0]?.focus();
      return Boolean(buttons.length);
    }
    const [dx,dy]=directions[key];
    const origin=focused.getBoundingClientRect();
    let best=null;
    let bestScore=Infinity;
    for(const button of buttons){
      const rect=button.getBoundingClientRect();
      const x=(rect.left+rect.right-origin.left-origin.right)/2;
      const y=(rect.top+rect.bottom-origin.top-origin.bottom)/2;
      const forward=x*dx+y*dy;
      if(forward<=4) continue;
      const score=forward+2*Math.abs(x*dy-y*dx);
      if(score<bestScore){
        best=button;
        bestScore=score;
      }
    }
    if(best) best.focus();
    return Boolean(best);
  }

  function controllerAction(pad){
    if(pad.buttons[1]?.pressed) return 'back';
    if(pad.buttons[0]?.pressed) return 'select';
    if(pad.buttons[12]?.pressed) return 'ArrowUp';
    if(pad.buttons[13]?.pressed) return 'ArrowDown';
    if(pad.buttons[14]?.pressed) return 'ArrowLeft';
    if(pad.buttons[15]?.pressed) return 'ArrowRight';
    const [x=0,y=0]=pad.axes;
    if(Math.max(Math.abs(x),Math.abs(y))<0.65) return '';
    return Math.abs(x)>Math.abs(y)
      ?(x<0?'ArrowLeft':'ArrowRight')
      :(y<0?'ArrowUp':'ArrowDown');
  }

  function reset(){
    lastScope=null;
    lastPad=null;
    lastAction='';
    activationHeld=false;
    needsRelease=true;
  }

  function poll(){
    if(document.hidden||!document.hasFocus()){ reset(); return; }
    const scope=getScope();
    if(!scope?.buttons){ reset(); return; }
    let pad;
    try{
      pad=Array.from(navigator.getGamepads()).find(device=>device?.connected&&device.mapping==='standard');
    }catch(e){ reset(); return; }
    if(!pad){ reset(); return; }
    if(lastPad!==pad.index||lastScope!==scope.buttons){
      reset();
      lastPad=pad.index;
      lastScope=scope.buttons;
    }
    const action=controllerAction(pad);
    if(!action){
      needsRelease=false;
      lastAction='';
      activationHeld=false;
      return;
    }
    if(needsRelease) return;
    const now=performance.now();
    const direction=Object.hasOwn(directions,action);
    if(direction) activationHeld=false;
    else if(activationHeld) return;
    else activationHeld=true;
    if(action===lastAction&&(!direction||now<nextRepeat)) return;
    nextRepeat=now+(action===lastAction?140:360);
    lastAction=action;
    document.documentElement.classList.add('controller-focus');
    if(action==='back'){ scope.back?.(); return; }
    const buttons=availableButtons(scope);
    const focused=buttons.includes(document.activeElement)?document.activeElement:null;
    if(direction) move(action,buttons,focused);
    else if(focused) focused.click();
    else buttons[0]?.focus();
  }

  window.addEventListener('blur',reset);
  window.addEventListener('gamepaddisconnected',reset);
  document.addEventListener('pointerdown',()=>document.documentElement.classList.remove('controller-focus'),true);
  document.addEventListener('visibilitychange',reset);
  document.addEventListener('keydown',event=>{
    if(!enabled||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey) return;
    const scope=getScope();
    if(scope?.modal&&!scope.modal.contains(event.target)&&
        (event.key==='Enter'||event.key===' '||Object.hasOwn(directions,event.key))){
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if(!scope?.buttons) return;
    const buttons=availableButtons(scope);
    if(!buttons.includes(event.target)&&event.target!==document.body) return;
    if(event.key==='Enter'&&event.repeat){
      event.preventDefault();
      return;
    }
    if(!Object.hasOwn(directions,event.key)) return;
    const focused=buttons.includes(event.target)?event.target:null;
    move(event.key,buttons,focused);
    event.preventDefault();
    event.stopImmediatePropagation();
  },true);

  return function setEnabled(value){
    if(value===enabled) return;
    enabled=value;
    reset();
    if(!value) document.documentElement.classList.remove('controller-focus');
    if(pollId!==null) window.clearInterval(pollId);
    pollId=value&&typeof navigator.getGamepads==='function'?window.setInterval(poll,50):null;
  };
}
