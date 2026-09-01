function pageSize(){ return cfg.layoutMode === 'klein' ? 9 : 4; }
function visibleTiles(){ return cfg.tiles.filter(t => t.visible); }
function pageCount(){ return Math.max(1, Math.ceil(visibleTiles().length / pageSize())); }
function tilesForPage(page){ const all=visibleTiles(); const size=pageSize(); return all.slice(page*size, page*size + size); }
async function loadConfig(){
  const response=await fetch('/api/config',{cache:'no-store'});
  if(!response.ok) throw new Error('Config could not be loaded');
  const data=await response.json();
  if(!data||typeof data!=='object'||!Array.isArray(data.tiles)) throw new Error('Invalid config response');
  cfg=data;
  if(typeof cfg.currentPage!=='number') cfg.currentPage=0;
  renderAll();
}
async function loadApps(refreshAdmin=false){
  appCatalogState='loading';
  if(cfg&&typeof renderCatalogStates==='function') renderCatalogStates();
  try{
    const response=await fetch('/api/apps',{cache:'no-store'});
    if(!response.ok) throw new Error('App catalog could not be loaded');
    const data=await response.json();
    if(!Array.isArray(data)) throw new Error('Invalid app catalog response');
    appOptions=data;
    appCatalogState=appOptions.length?'ready':'empty';
  }catch(e){
    appOptions=[];
    appCatalogState='error';
  }
  if(cfg&&refreshAdmin) renderAdmin();
}
async function loadRecommendations(){
  recommendationState='loading';
  if(cfg&&typeof renderRecommendations==='function') renderRecommendations();
  try{
    const response=await fetch('/api/recommendations',{cache:'no-store'});
    if(!response.ok) throw new Error('Recommendations could not be loaded');
    const data=await response.json();
    if(!Array.isArray(data)) throw new Error('Invalid recommendations response');
    recommendations=data;
    recommendationState=recommendations.length?'ready':'empty';
  }catch(e){
    recommendations=[];
    recommendationState='error';
  }
  if(cfg&&typeof renderRecommendations==='function') renderRecommendations();
}
async function loadFeatures(){
  try{
    const response=await fetch('/api/features',{cache:'no-store'});
    if(!response.ok) return;
    const data=await response.json();
    if(data&&typeof data==='object') features=data;
  }catch(e){}
}
async function loadBrowsers(refreshAdmin=false){
  browserCatalogState='loading';
  if(cfg&&typeof renderCatalogStates==='function') renderCatalogStates();
  try{
    const response=await fetch('/api/browsers',{cache:'no-store'});
    if(!response.ok) throw new Error('Browser catalog could not be loaded');
    const data=await response.json();
    if(!Array.isArray(data)) throw new Error('Invalid browser catalog response');
    browserOptions=data;
    browserCatalogState=browserOptions.some(browser=>browser.installed)?'ready':'empty';
  }catch(e){
    browserOptions=[];
    browserCatalogState='error';
  }
  if(cfg&&refreshAdmin) renderAdmin();
}
function showLauncherStartupState(state){
  const grid=document.getElementById('grid');
  const title=document.getElementById('title');
  document.getElementById('kids').classList.remove('hidden');
  document.getElementById('admin').classList.add('hidden');
  document.querySelector('.cornerbar').classList.add('hidden');
  document.getElementById('navLeft').classList.add('hidden');
  document.getElementById('navRight').classList.add('hidden');
  title.textContent=state==='error'?uiText.startupErrorTitle:'';
  grid.className='grid {{DEFAULT_LAYOUT}}';
  grid.replaceChildren();
  const status=document.createElement('section');
  status.id='startupState';
  status.setAttribute('aria-live','polite');
  renderUiState(
    status,
    state,
    state==='error'?uiText.startupError:uiText.startupLoading,
    state==='error'?bootstrapLauncher:null
  );
  status.classList.add('launcher-state');
  grid.appendChild(status);
}
async function bootstrapLauncher(){
  if(bootstrapPromise) return bootstrapPromise;
  showLauncherStartupState('loading');
  bootstrapPromise=(async()=>{
    try{
      await loadConfig();
    }catch(e){
      cfg=null;
      showLauncherStartupState('error');
      return false;
    }
    await Promise.all([
      loadApps(),
      loadRecommendations(),
      loadFeatures(),
      loadBrowsers()
    ]);
    try{ await autoScanRecommendations(); }catch(e){}
    await pollTimer();
    if(timerPollInterval===null) timerPollInterval=setInterval(pollTimer,10000);
    await startupUpdateCheck();
    return true;
  })();
  try{
    return await bootstrapPromise;
  }finally{
    bootstrapPromise=null;
  }
}
function applyDynamicTheme(){
  const body=document.body;
  const bg=document.getElementById('themeBg');
  if(!cfg || cfg.theme!=='custom'){
    if(bg) bg.style.backgroundImage='';
    return;
  }
  const c=cfg.customColors||{};
  if(c.bg1) body.style.setProperty('--bg1',c.bg1);
  if(c.bg2) body.style.setProperty('--bg2',c.bg2);
  if(c.text) body.style.setProperty('--text',c.text);
  if(c.btn) body.style.setProperty('--btn',c.btn);
  if(c.card) body.style.setProperty('--card',c.card);
  if(c.btnText) body.style.setProperty('--btn-text',c.btnText);
  if(c.smallbtnBg) body.style.setProperty('--smallbtn-bg',c.smallbtnBg);
  if(c.inputBorder) body.style.setProperty('--input-border',c.inputBorder);
  if(c.recShadow) body.style.setProperty('--rec-shadow',c.recShadow);
  if(c.shadow) body.style.setProperty('--shadow',c.shadow);
  if(bg){
    if(cfg.customBackground){
      bg.style.backgroundImage='url('+cfg.customBackground+')';
      bg.style.opacity='1';
    }else{
      bg.style.backgroundImage='';
      bg.style.opacity='0';
    }
  }
}
function renderAll(){
  document.body.className='theme-'+(cfg.theme||'{{DEFAULT_THEME}}');
  applyDynamicTheme();
  document.getElementById('title').textContent=cfg.title||'{{DEFAULT_TITLE}}';
  const isAdmin=!document.getElementById('admin').classList.contains('hidden');
  const cornerbar=document.querySelector('.cornerbar');
  cornerbar.classList.toggle('hidden',isAdmin);
  const parentBtn=document.getElementById('parentBtn');
  parentBtn.textContent=isAdmin?(uiText.back||'{{LABEL_BACK}}'):(cfg.parentLabel||'{{DEFAULT_PARENT_LABEL}}');
  parentBtn.style.position='relative';
  let badge=parentBtn.querySelector('.update-badge');
  if(updateAvailable && !isAdmin){
    if(!badge){
      badge=document.createElement('span');
      badge.className='update-badge';
      parentBtn.appendChild(badge);
    }
    badge.textContent='1';
  }else if(badge){
    badge.remove();
  }
  document.getElementById('exitBtn').textContent=cfg.exitLabel||'{{DEFAULT_EXIT_LABEL}}';
  const shutdownBtn=document.getElementById('shutdownBtn');
  shutdownBtn.textContent=cfg.shutdownLabel||'{{SHUTDOWN_LABEL}}';
  shutdownBtn.style.display=features.shutdownAvailable?'':'none';
  document.getElementById('grid').className='grid '+(cfg.layoutMode||'{{DEFAULT_LAYOUT}}');
  const pc=pageCount();
  if(cfg.currentPage>=pc) cfg.currentPage=pc-1;
  if(cfg.currentPage<0) cfg.currentPage=0;
  renderKids();
  renderAdmin();
  renderNav();
}
function renderKids(){
  const grid=document.getElementById('grid');
  grid.innerHTML='';
  const tiles=tilesForPage(cfg.currentPage);
  const size=pageSize();
  let lastLaunched='';
  try{ lastLaunched=localStorage.getItem('cozyLastLaunched')||''; }catch(e){}
  if(tiles.length===0){
    const empty=document.createElement('div');
    empty.className='empty-state';
    const emptyEmoji=document.createElement('div');
    emptyEmoji.className='emoji';
    emptyEmoji.textContent=uiText.emptyStateEmoji||'🤔';
    const emptyText=document.createElement('p');
    emptyText.textContent=uiText.emptyStateText||'Frag Mama oder Papa, um Apps hinzuzufügen!';
    empty.append(emptyEmoji,emptyText);
    grid.appendChild(empty);
    return;
  }
  for(let i=0;i<size;i++){
    if(i<tiles.length){
      const tile=tiles[i];
      const btn=document.createElement('button');
      btn.className='tile'+(tile.id===lastLaunched?' last-launched':'');
      btn.style.position='relative';
      btn.onclick=()=>launchTile(tile.id);
      btn.onfocus=()=>{ focusedTileIndex=i; updateTileFocus(false); };
      const tileEmoji=document.createElement('div');
      tileEmoji.className='emoji';
      tileEmoji.textContent=tile.emoji||'✨';
      const tileLabel=document.createElement('div');
      tileLabel.textContent=tile.label||'';
      btn.append(tileEmoji,tileLabel);
      if(tile.id===lastLaunched){
        const star=document.createElement('div');
        star.className='last-star';
        star.textContent='⭐';
        btn.appendChild(star);
      }
      grid.appendChild(btn);
    } else {
      const ph=document.createElement('div');
      ph.className='tile placeholder';
      const phEmoji=document.createElement('div');
      phEmoji.className='emoji';
      phEmoji.textContent='✨';
      ph.append(phEmoji,document.createElement('div'));
      grid.appendChild(ph);
    }
  }
  if(focusedTileIndex>=tiles.length) focusedTileIndex=0;
  updateTileFocus();
}
function renderNav(){ const homeHidden=document.getElementById('kids').classList.contains('hidden'); document.getElementById('navLeft').classList.toggle('hidden', homeHidden||cfg.currentPage<=0); document.getElementById('navRight').classList.toggle('hidden', homeHidden||cfg.currentPage>=pageCount()-1); }
function changePage(dir){ cfg.currentPage=Math.max(0,Math.min(pageCount()-1,cfg.currentPage+dir)); focusedTileIndex=0; renderAll(); }
function showStartFeedback(tile){
  const overlay=document.getElementById('startOverlay');
  const emoji=document.getElementById('startEmoji');
  const text=document.getElementById('startText');
  emoji.textContent=tile.emoji||'✨';
  text.textContent=(uiText.startingApp||'Starte {app}...').replace('{app}',tile.label||'');
  overlay.classList.remove('hidden');
  setTimeout(()=>overlay.classList.add('hidden'),1500);
}
function launchTile(id){
  const tile=cfg.tiles.find(t=>t.id===id);
  if(!tile) return;
  try{ localStorage.setItem('cozyLastLaunched',id); }catch(e){}
  showStartFeedback(tile);
  fetch('/launch/'+encodeURIComponent(id), {method:'POST'}).then(r=>{ if(r.redirected) window.location=r.url; }).catch(()=>{});
}

// PIN handling
function handleParentClick(){ if(document.getElementById('admin').classList.contains('hidden')){ openAdmin(); } else { closeAdmin(); } }
function requestPin(callback){ pinCallback=callback; showPin(); }
function openAdmin(){ if(cfg.pinConfigured){ requestPin(enterAdmin); return; } enterAdmin(); }
function showPin(){ pinReturnFocus=document.activeElement; document.getElementById('pin').classList.remove('hidden'); document.getElementById('pinInput').value=''; document.getElementById('pinErr').textContent=''; document.getElementById('pinInput').focus(); }
function hidePin(){ document.getElementById('pin').classList.add('hidden'); }
function cancelPin(){ hidePin(); document.getElementById('pinInput').value=''; document.getElementById('pinErr').textContent=''; pinCallback=null; if(pinReturnFocus&&pinReturnFocus.isConnected) pinReturnFocus.focus(); pinReturnFocus=null; }
async function submitPin(){ const val=document.getElementById('pinInput').value; const r=await fetch('/api/verify-pin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:val})}); const data=await r.json(); if(data.valid){ hidePin(); pinReturnFocus=null; if(pinCallback){ pinCallback(); pinCallback=null; } } else { document.getElementById('pinErr').textContent=uiText.pinWrong; document.getElementById('pinInput').value=''; document.getElementById('pinInput').focus(); } }
function enterAdmin(){ adminPage=cfg.currentPage; adminSection='overview'; adminTileQuery=''; adminTileVisibility='all'; adminSelectedTileIds.clear(); document.getElementById('kids').classList.add('hidden'); document.getElementById('admin').classList.remove('hidden'); document.querySelector('.cornerbar').classList.add('hidden'); document.getElementById('parentBtn').textContent=uiText.back||'{{LABEL_BACK}}'; renderAdmin(); renderNav(); document.getElementById('adminNavOverview').focus(); loadBackups(); }
function closeAdmin(){ document.getElementById('admin').classList.add('hidden'); document.getElementById('kids').classList.remove('hidden'); document.querySelector('.cornerbar').classList.remove('hidden'); document.getElementById('parentBtn').textContent=cfg.parentLabel||'{{DEFAULT_PARENT_LABEL}}'; focusedTileIndex=0; renderAll(); }
function shutdownNow(){ if(cfg.pinConfigured){ requestPin(() => { fetch('/shutdown',{method:'POST'}).catch(()=>{}); }); return; } fetch('/shutdown',{method:'POST'}).catch(()=>{}); }
function exitKids(){ if(cfg.pinConfigured){ requestPin(() => { fetch('/exit-kids',{method:'POST'}).catch(()=>{}); }); return; } fetch('/exit-kids',{method:'POST'}).catch(()=>{}); }

const ALL_THEMES=[
  {id:'rosa',type:'color',gradient:'linear-gradient(180deg,#ffd6e8,#ffeef6)'},
  {id:'lila',type:'color',gradient:'linear-gradient(180deg,#e3d6ff,#f4eeff)'},
  {id:'blau',type:'color',gradient:'linear-gradient(180deg,#d7ebff,#eef7ff)'},
  {id:'gruen',type:'color',gradient:'linear-gradient(180deg,#d9f7df,#effcf1)'},
  {id:'regenbogen',type:'color',gradient:'linear-gradient(180deg,#ffd6e8,#d7ebff)'},
  {id:'wald',type:'world',img:'/themes/forrest.jpg'},
  {id:'weltraum',type:'world',img:'/themes/space.jpg'},
  {id:'ocean',type:'world',img:'/themes/ocean.jpg'},
  {id:'dinosaurier',type:'world',img:'/themes/dinosaur.jpg'},
  {id:'baustelle',type:'world',img:'/themes/construction-site.jpg'},
  {id:'prinzessin',type:'world',img:'/themes/princess.jpg'},
  {id:'bauernhof',type:'world',img:'/themes/farm.jpg'},
  {id:'katzen',type:'world',img:'/themes/cats.jpg'},
  {id:'hunde',type:'world',img:'/themes/dogs.jpg'},
  {id:'custom',type:'color',gradient:'linear-gradient(180deg,#ffd6e8,#ffeef6)'}
];
const THEME_LABELS={
  de:{rosa:'Rosa',lila:'Lila',blau:'Blau',gruen:'Grün',regenbogen:'Regenbogen',wald:'Wald',weltraum:'Weltraum',ocean:'Ozean',dinosaurier:'Dinosaurier',baustelle:'Baustelle',prinzessin:'Prinzessin',bauernhof:'Bauernhof',katzen:'Katzen',hunde:'Hunde',custom:'Eigene Farben'},
  en:{rosa:'Pink',lila:'Purple',blau:'Blue',gruen:'Green',regenbogen:'Rainbow',wald:'Forest',weltraum:'Space',ocean:'Ocean',dinosaurier:'Dinosaurs',baustelle:'Construction',prinzessin:'Princess',bauernhof:'Farm',katzen:'Cats',hunde:'Dogs',custom:'Custom'}
};
function interfaceLanguage(){ return ((cfg&&cfg.language)||'{{ACTIVE_LANG}}')==='de'?'de':'en'; }
function themeLabel(id){ return THEME_LABELS[interfaceLanguage()][id]||id; }
function openThemePicker(){ document.getElementById('themeOverlay').classList.remove('hidden'); renderThemeChooser(); requestAnimationFrame(()=>{ const first=document.querySelector('#themeChooser .theme-thumb'); if(first) first.focus(); }); }
function closeThemePicker(){
  document.getElementById('themeOverlay').classList.add('hidden');
  updateThemeDisplay();
  const ctp=document.getElementById('customThemePanel');
  const isCustom=(document.getElementById('cfgTheme').value||'')==='custom';
  ctp.style.display=isCustom?'grid':'none';
  renderAppearancePreview();
  document.getElementById('openThemeBtn').focus();
}
function updateThemeDisplay(){ const id=document.getElementById('cfgTheme').value; document.getElementById('themeDisplay').textContent=themeLabel(id); }
function renderThemeChooser(){
  const container=document.getElementById('themeChooser');
  const current=document.getElementById('cfgTheme').value;
  container.innerHTML='';
  for(const t of ALL_THEMES){
    const el=document.createElement('button');
    el.type='button';
    el.className='theme-thumb'+(t.id===current?' active':'');
    el.setAttribute('aria-label',themeLabel(t.id));
    el.setAttribute('aria-pressed',t.id===current?'true':'false');
    el.style.background=t.type==='color'?t.gradient:'url('+t.img+') center/cover no-repeat';
    el.onclick=()=>{ document.getElementById('cfgTheme').value=t.id; renderThemeChooser(); closeThemePicker(); };
    const lbl=document.createElement('div');
    lbl.className='thumb-label';
    lbl.textContent=themeLabel(t.id);
    el.appendChild(lbl);
    container.appendChild(el);
  }
}
