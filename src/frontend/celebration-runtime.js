const COZY_CELEBRATION_POINTS=Object.freeze([
  Object.freeze({x:'-22vw',y:'-18vh',delay:'0ms',scale:'1.05',rotate:'-24deg'}),
  Object.freeze({x:'-10vw',y:'-27vh',delay:'35ms',scale:'.8',rotate:'18deg'}),
  Object.freeze({x:'7vw',y:'-25vh',delay:'70ms',scale:'1.15',rotate:'30deg'}),
  Object.freeze({x:'21vw',y:'-14vh',delay:'20ms',scale:'.9',rotate:'-20deg'}),
  Object.freeze({x:'24vw',y:'7vh',delay:'85ms',scale:'1.05',rotate:'24deg'}),
  Object.freeze({x:'11vw',y:'21vh',delay:'45ms',scale:'.82',rotate:'-28deg'}),
  Object.freeze({x:'-8vw',y:'23vh',delay:'95ms',scale:'1.1',rotate:'20deg'}),
  Object.freeze({x:'-23vw',y:'9vh',delay:'55ms',scale:'.88',rotate:'26deg'})
]);

let cozyCelebrationTimer=null;

function celebrationMotionAllowed(config,root=document){
  if(!config||config.celebrationEnabled!==true||config.accessibilityReducedMotion===true) return false;
  const doc=root&&root.nodeType===9?root:(root&&root.ownerDocument)||document;
  const view=doc.defaultView||window;
  return !(view.matchMedia&&view.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

function playCelebrationMoment(config,root=document){
  if(!celebrationMotionAllowed(config,root)) return false;
  const layer=root.getElementById?root.getElementById('celebrationLayer'):
    root.querySelector&&root.querySelector('#celebrationLayer');
  if(!layer) return false;
  if(cozyCelebrationTimer!==null) clearTimeout(cozyCelebrationTimer);
  cozyCelebrationTimer=null;
  layer.hidden=true;
  layer.classList.remove('is-active');
  layer.replaceChildren();
  for(const point of COZY_CELEBRATION_POINTS){
    const star=layer.ownerDocument.createElement('span');
    star.className='celebration-star';
    star.textContent='★';
    star.style.setProperty('--celebrate-x',point.x);
    star.style.setProperty('--celebrate-y',point.y);
    star.style.setProperty('--celebrate-delay',point.delay);
    star.style.setProperty('--celebrate-scale',point.scale);
    star.style.setProperty('--celebrate-rotate',point.rotate);
    layer.appendChild(star);
  }
  layer.hidden=false;
  void layer.offsetWidth;
  layer.classList.add('is-active');
  cozyCelebrationTimer=setTimeout(()=>{
    layer.hidden=true;
    layer.classList.remove('is-active');
    layer.replaceChildren();
    cozyCelebrationTimer=null;
  },900);
  return true;
}
