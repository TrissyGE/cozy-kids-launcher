let firstRunStep=0;
let firstRunBusy=false;
const FIRST_RUN_TEXT={
  de:{progress:'Schritt {current} von {total}',languageTitle:'Willkommen bei Cozy Kids',languageBody:'In welcher Sprache soll der Launcher angezeigt werden?',childTitle:'Für wen ist dieser Launcher?',childBody:'Name, Avatar und Überschrift können später jederzeit geändert werden.',childName:'Name des Kindes',childAvatar:'Avatar-Emoji',homeTitle:'Überschrift auf dem Startbildschirm',appsTitle:'Welche Kacheln sollen sichtbar sein?',appsBody:'Programme können später in den Eltern-Einstellungen ergänzt oder geändert werden.',timeTitle:'Erste Bildschirmzeit-Regel',timeBody:'Lege eine einfache Sitzungsdauer fest oder starte zunächst ohne Timer.',appearanceTitle:'Wie soll es aussehen?',appearanceBody:'Wähle ein Thema und die Größe der Kacheln.',skip:'Vorerst überspringen',back:'Zurück',next:'Weiter',finish:'Fertig',saving:'Einrichtung wird gespeichert...',error:'Die Einrichtung konnte nicht gespeichert werden. Bitte erneut versuchen.',nameRequired:'Bitte einen Namen eingeben.',noApps:'Noch keine Kacheln verfügbar.',large:'Große Kacheln',small:'Kleine Kacheln'},
  en:{progress:'Step {current} of {total}',languageTitle:'Welcome to Cozy Kids',languageBody:'Which language should the launcher use?',childTitle:'Who is this launcher for?',childBody:'The name, avatar, and home title can be changed at any time.',childName:"Child's name",childAvatar:'Avatar emoji',homeTitle:'Home screen title',appsTitle:'Which tiles should be visible?',appsBody:'Apps can be added or changed later in Parent settings.',timeTitle:'First screen-time rule',timeBody:'Choose a simple session length or start without a timer.',appearanceTitle:'How should it look?',appearanceBody:'Choose a theme and tile size.',skip:'Skip for now',back:'Back',next:'Next',finish:'Finish',saving:'Saving setup...',error:'Setup could not be saved. Please try again.',nameRequired:'Please enter a name.',noApps:'No tiles are available yet.',large:'Large tiles',small:'Small tiles'}
};
const FIRST_RUN_STEPS=['language','child','apps','time','appearance'];

function firstRunText(){
  return FIRST_RUN_TEXT[cfg&&cfg.language==='de'?'de':'en'];
}

function maybeOpenFirstRun(){
  const overlay=document.getElementById('firstRunOverlay');
  if(!cfg||cfg.setupCompleted!==false){
    overlay.classList.add('hidden');
    return;
  }
  overlay.classList.remove('hidden');
  renderFirstRun();
}

function firstRunLabel(text,control){
  const label=document.createElement('label');
  label.className='admin-field-label';
  const caption=document.createElement('span');
  caption.textContent=text;
  label.append(caption,control);
  return label;
}

function firstRunInput(id,value,placeholder,maxLength){
  const input=document.createElement('input');
  input.id=id;
  input.value=value||'';
  input.placeholder=placeholder||'';
  input.maxLength=maxLength;
  return input;
}

function renderFirstRun(){
  if(!cfg||cfg.setupCompleted!==false) return;
  const text=firstRunText();
  const step=FIRST_RUN_STEPS[firstRunStep];
  document.getElementById('firstRunProgress').textContent=text.progress
    .replace('{current}',String(firstRunStep+1))
    .replace('{total}',String(FIRST_RUN_STEPS.length));
  const dots=document.getElementById('firstRunProgressDots');
  dots.replaceChildren();
  FIRST_RUN_STEPS.forEach((unused,index)=>{
    const dot=document.createElement('span');
    dot.className=index<=firstRunStep?'complete':'';
    dots.appendChild(dot);
  });
  const titles={language:text.languageTitle,child:text.childTitle,apps:text.appsTitle,time:text.timeTitle,appearance:text.appearanceTitle};
  const descriptions={language:text.languageBody,child:text.childBody,apps:text.appsBody,time:text.timeBody,appearance:text.appearanceBody};
  document.getElementById('firstRunTitle').textContent=titles[step];
  document.getElementById('firstRunDescription').textContent=descriptions[step];
  setIconLabel(document.getElementById('firstRunSkipBtn'),'close',text.skip);
  setIconLabel(document.getElementById('firstRunBackBtn'),'back',text.back);
  setIconLabel(document.getElementById('firstRunNextBtn'),firstRunStep===FIRST_RUN_STEPS.length-1?'save':'nav-right',firstRunStep===FIRST_RUN_STEPS.length-1?text.finish:text.next);
  document.getElementById('firstRunBackBtn').disabled=firstRunStep===0||firstRunBusy;
  document.getElementById('firstRunNextBtn').disabled=firstRunBusy;
  document.getElementById('firstRunSkipBtn').disabled=firstRunBusy;
  clearUiState(document.getElementById('firstRunMessage'));
  const content=document.getElementById('firstRunContent');
  content.replaceChildren();
  if(step==='language') renderFirstRunLanguage(content);
  else if(step==='child') renderFirstRunChild(content,text);
  else if(step==='apps') renderFirstRunApps(content,text);
  else if(step==='time') renderFirstRunTime(content);
  else renderFirstRunAppearance(content,text);
  requestAnimationFrame(()=>{
    const focusTarget=content.querySelector('button[aria-pressed="true"]')
      ||content.querySelector('input,select,button');
    if(focusTarget) focusTarget.focus({preventScroll:true});
  });
}

function renderFirstRunLanguage(content){
  const choices=document.createElement('div');
  choices.className='first-run-language-grid';
  for(const [language,label,emoji] of [['de','Deutsch','🇩🇪'],['en','English','🇬🇧']]){
    const button=document.createElement('button');
    button.type='button';
    button.className='first-run-choice';
    button.dataset.language=language;
    button.setAttribute('aria-pressed',String(cfg.language===language));
    const icon=document.createElement('span');
    icon.className='first-run-choice-icon';
    icon.setAttribute('aria-hidden','true');
    icon.textContent=emoji;
    const name=document.createElement('strong');
    name.textContent=label;
    button.append(icon,name);
    button.onclick=()=>selectFirstRunLanguage(language);
    choices.appendChild(button);
  }
  content.appendChild(choices);
}

async function selectFirstRunLanguage(language){
  if(firstRunBusy) return;
  cfg.language=normalizedInterfaceLanguage(language);
  await loadInterfaceLanguage(cfg.language);
  cfg.parentLabel=uiText.defaultParentLabel||(cfg.language==='de'?'Papa':'Parent');
  cfg.exitLabel=uiText.defaultExitLabel||(cfg.language==='de'?'Kindermodus beenden':'Exit kids mode');
  cfg.shutdownLabel=uiText.defaultShutdownLabel||(cfg.language==='de'?'Ausschalten':'Shut down');
  cfg.title=uiText.defaultTitle||(cfg.language==='de'?'Hallo Kiddo 🌈':'Hello Kiddo 🌈');
  const labels={paint:uiText.tilePaint,games:uiText.tileGames,music:uiText.tileMusic,browser:uiText.tileBrowser};
  for(const tile of cfg.tiles){ if(labels[tile.id]) tile.label=labels[tile.id]; }
  renderAll();
}

function renderFirstRunChild(content,text){
  const grid=document.createElement('div');
  grid.className='first-run-fields';
  const name=firstRunInput('firstRunChildName',cfg.name,text.childName,40);
  const avatar=firstRunInput('firstRunChildAvatar',cfg.avatar,text.childAvatar,16);
  const title=firstRunInput('firstRunHomeTitle',cfg.title,text.homeTitle,80);
  grid.append(firstRunLabel(text.childName,name),firstRunLabel(text.childAvatar,avatar),firstRunLabel(text.homeTitle,title));
  content.appendChild(grid);
}

function renderFirstRunApps(content,text){
  const grid=document.createElement('div');
  grid.className='first-run-app-grid';
  if(!cfg.tiles.length){
    const empty=document.createElement('p');
    empty.className='muted';
    empty.textContent=text.noApps;
    grid.appendChild(empty);
  }
  for(const tile of cfg.tiles){
    const label=document.createElement('label');
    label.className='first-run-app-choice';
    const checkbox=document.createElement('input');
    checkbox.type='checkbox';
    checkbox.dataset.tileId=tile.id;
    checkbox.checked=tile.visible!==false;
    const visual=createTileVisual(tile.emoji,'first-run-app-icon');
    const name=document.createElement('strong');
    name.textContent=tile.label;
    label.append(checkbox,visual,name);
    grid.appendChild(label);
  }
  content.appendChild(grid);
}

function renderFirstRunTime(content){
  const select=document.createElement('select');
  select.id='firstRunTimerMinutes';
  for(const [value,label] of [['0',uiText.timerOff],['15',uiText.timerMinutes15],['30',uiText.timerMinutes30],['60',uiText.timerMinutes60]]){
    const option=document.createElement('option');
    option.value=value;
    option.textContent=label;
    select.appendChild(option);
  }
  select.value=[0,15,30,60].includes(cfg.timerMinutes)?String(cfg.timerMinutes):'0';
  content.appendChild(select);
}

function renderFirstRunAppearance(content,text){
  const themes=document.createElement('div');
  themes.className='first-run-theme-grid';
  for(const theme of ALL_THEMES.filter(item=>item.id!=='custom')){
    const button=document.createElement('button');
    button.type='button';
    button.className='theme-thumb'+(theme.id===cfg.theme?' active':'');
    button.dataset.theme=theme.id;
    button.setAttribute('aria-label',themeLabel(theme.id));
    button.setAttribute('aria-pressed',String(theme.id===cfg.theme));
    button.style.background=theme.type==='color'
      ?theme.gradient
      :'url('+theme.img+') center/cover no-repeat,linear-gradient(135deg,#e3d6ff,#d7ebff)';
    const label=document.createElement('span');
    label.className='thumb-label';
    label.textContent=themeLabel(theme.id);
    button.appendChild(label);
    button.onclick=()=>{
      cfg.theme=theme.id;
      themes.querySelectorAll('button').forEach(choice=>{ choice.classList.remove('active'); choice.setAttribute('aria-pressed','false'); });
      button.classList.add('active');
      button.setAttribute('aria-pressed','true');
    };
    themes.appendChild(button);
  }
  const layouts=document.createElement('div');
  layouts.className='first-run-layout-grid';
  for(const [layout,label] of [['gross',text.large],['klein',text.small]]){
    const button=document.createElement('button');
    button.type='button';
    button.className='smallbtn';
    button.dataset.layout=layout;
    button.setAttribute('aria-pressed',String(cfg.layoutMode===layout));
    setIconLabel(button,layout==='gross'?'apps':'overview',label);
    button.onclick=()=>{
      cfg.layoutMode=layout;
      layouts.querySelectorAll('button').forEach(choice=>choice.setAttribute('aria-pressed',String(choice===button)));
    };
    layouts.appendChild(button);
  }
  content.append(themes,layouts);
}

function captureFirstRunStep(){
  const step=FIRST_RUN_STEPS[firstRunStep];
  if(step==='child'){
    const name=document.getElementById('firstRunChildName').value.trim();
    if(!name){
      renderUiState(document.getElementById('firstRunMessage'),'error',firstRunText().nameRequired);
      document.getElementById('firstRunChildName').focus();
      return false;
    }
    cfg.name=name;
    cfg.avatar=document.getElementById('firstRunChildAvatar').value.trim();
    cfg.title=document.getElementById('firstRunHomeTitle').value.trim()||name;
  }else if(step==='apps'){
    document.querySelectorAll('#firstRunContent input[data-tile-id]').forEach(input=>{
      const tile=cfg.tiles.find(item=>item.id===input.dataset.tileId);
      if(tile) tile.visible=input.checked;
    });
  }else if(step==='time'){
    cfg.timerMinutes=parseInt(document.getElementById('firstRunTimerMinutes').value,10)||0;
  }
  return true;
}

function changeFirstRunStep(direction){
  if(firstRunBusy) return;
  if(direction>0&&!captureFirstRunStep()) return;
  if(direction>0&&firstRunStep===FIRST_RUN_STEPS.length-1){
    requestFirstRunCompletion();
    return;
  }
  firstRunStep=Math.max(0,Math.min(FIRST_RUN_STEPS.length-1,firstRunStep+direction));
  renderFirstRun();
  playFirstRunStepTransition(direction);
}

function skipFirstRun(){
  if(!firstRunBusy) requestFirstRunCompletion();
}

function requestFirstRunCompletion(){
  if(cfg.pinConfigured){ requestPin(persistFirstRun); return; }
  persistFirstRun();
}

async function persistFirstRun(){
  firstRunBusy=true;
  cfg.setupCompleted=true;
  const message=document.getElementById('firstRunMessage');
  renderUiState(message,'loading',firstRunText().saving);
  document.querySelectorAll('#firstRunOverlay button').forEach(button=>{ button.disabled=true; });
  try{
    await persistConfig();
    document.getElementById('firstRunOverlay').classList.add('hidden');
    firstRunStep=0;
    focusedTileIndex=0;
    renderAll();
  }catch(e){
    cfg.setupCompleted=false;
    renderUiState(message,'error',firstRunText().error);
  }finally{
    firstRunBusy=false;
    if(cfg.setupCompleted===false){
      document.getElementById('firstRunSkipBtn').disabled=false;
      document.getElementById('firstRunBackBtn').disabled=firstRunStep===0;
      document.getElementById('firstRunNextBtn').disabled=false;
    }
  }
}

document.addEventListener('keydown',event=>{
  const overlay=document.getElementById('firstRunOverlay');
  if(!overlay||overlay.classList.contains('hidden')||!document.getElementById('pin').classList.contains('hidden')) return;
  if(event.key==='Escape'){
    event.preventDefault();
    event.stopImmediatePropagation();
    return;
  }
  if(event.key!=='Tab') return;
  const controls=Array.from(overlay.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled])'));
  if(!controls.length) return;
  const index=controls.indexOf(document.activeElement);
  if(index<0||(event.shiftKey&&index===0)||(!event.shiftKey&&index===controls.length-1)){
    event.preventDefault();
    event.stopImmediatePropagation();
    controls[event.shiftKey?controls.length-1:0].focus();
  }
},true);
