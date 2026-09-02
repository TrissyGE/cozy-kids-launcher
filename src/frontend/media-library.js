const MEDIA_FALLBACK_TEXT=Object.freeze({
  mediaLibraryTitle:'Movies & music',
  mediaLibraryHint:'Choose something to play',
  mediaLibraryBack:'Back to home',
  mediaLibraryLoading:'Looking for your media...',
  mediaLibraryEmpty:'No music or videos were found here yet.',
  mediaLibraryError:'The media library could not be loaded.',
  mediaLibraryRetry:'Try again',
  mediaLibraryVideo:'Video',
  mediaLibraryAudio:'Music',
  mediaLibraryPlay:'Play {title}',
  mediaLibraryStarting:'Starting {title}...',
  mediaLibraryPlayError:'This media could not be started.',
  mediaLibraryUnavailable:'This media tile is not available right now.',
  mediaLibraryTruncated:'Showing the first 2,000 items.'
});

let mediaText=MEDIA_FALLBACK_TEXT;
let mediaConfig=null;
let mediaTileId='';

function mediaHome(){ window.location='/index.html'; }

function mediaTile(config,tileId){
  return (config.tiles||[]).find(tile=>tile.id===tileId&&tile.visible!==false&&
    Array.isArray(tile.cmd)&&tile.cmd.length===1&&tile.cmd[0]==='special:filme-musik');
}

function applyMediaTheme(config){
  document.body.className='media-page theme-'+(config.theme||'rosa');
  const background=document.getElementById('themeBg');
  if(config.theme!=='custom'){
    background.style.backgroundImage='';
    return;
  }
  const colors=config.customColors||{};
  for(const [name,variable] of Object.entries({
    bg1:'--bg1',bg2:'--bg2',text:'--text',btn:'--btn',card:'--card',
    btnText:'--btn-text',smallbtnBg:'--smallbtn-bg',inputBorder:'--input-border',
    recShadow:'--rec-shadow',shadow:'--shadow'
  })){
    if(colors[name]) document.body.style.setProperty(variable,colors[name]);
  }
  background.style.backgroundImage=config.customBackground?
    'url('+JSON.stringify(config.customBackground)+')':'';
  background.style.opacity=config.customBackground?'1':'0';
}

async function loadMediaText(language){
  const normalized=language==='de'?'de':'en';
  document.documentElement.lang=normalized;
  try{
    const response=await fetch('/frontend/locales/'+normalized+'.json',{cache:'no-store'});
    if(!response.ok) throw new Error('Locale unavailable');
    const locale=await response.json();
    if(locale&&typeof locale==='object'&&!Array.isArray(locale)) mediaText={...MEDIA_FALLBACK_TEXT,...locale};
  }catch(e){}
}

function localizeMediaPage(tile){
  const title=(tile&&tile.label)||mediaText.mediaLibraryTitle;
  document.title=title+' · Cozy Kids Launcher';
  document.getElementById('mediaTitle').textContent=title;
  document.getElementById('mediaHint').textContent=mediaText.mediaLibraryHint;
  setIconLabel(document.getElementById('mediaBack'),'back',mediaText.mediaLibraryBack);
}

function showMediaState(kind,message,retryAction=null){
  const state=document.getElementById('mediaState');
  state.hidden=false;
  state.className='ui-state media-library-state ui-state-'+kind;
  state.setAttribute('role',kind==='error'?'alert':'status');
  state.setAttribute('aria-busy',kind==='loading'?'true':'false');
  const text=document.createElement('span');
  text.className='ui-state-message';
  text.textContent=message;
  const children=[text];
  if(retryAction){
    const button=document.createElement('button');
    button.type='button';
    button.className='smallbtn ui-state-retry';
    button.textContent=mediaText.mediaLibraryRetry;
    button.addEventListener('click',retryAction);
    children.push(button);
  }
  state.replaceChildren(...children);
}

function hideMediaState(){
  const state=document.getElementById('mediaState');
  state.hidden=true;
  state.setAttribute('aria-busy','false');
}

function mediaCoverFallback(container,kind){
  const playMark=container.querySelector('.media-play-mark');
  container.classList.add('media-cover-fallback');
  const icon=createLocalIcon(kind==='video'?'video':'media');
  container.replaceChildren(...(icon?[icon]:[]),...(playMark?[playMark]:[]));
}

function mediaCard(item){
  const shell=document.createElement('article');
  shell.className='media-card-shell';
  shell.setAttribute('role','listitem');
  const button=document.createElement('button');
  button.type='button';
  button.className='media-card';
  button.dataset.mediaId=item.id;
  button.setAttribute('aria-label',mediaText.mediaLibraryPlay.replace('{title}',item.title));
  button.addEventListener('click',()=>playMedia(item,button));
  const cover=document.createElement('span');
  cover.className='media-cover';
  if(item.coverUrl){
    const image=document.createElement('img');
    image.src=item.coverUrl;
    image.alt='';
    image.loading='lazy';
    image.addEventListener('error',()=>mediaCoverFallback(cover,item.kind),{once:true});
    cover.appendChild(image);
  }else{
    mediaCoverFallback(cover,item.kind);
  }
  const play=document.createElement('span');
  play.className='media-play-mark';
  play.setAttribute('aria-hidden','true');
  const playIcon=createLocalIcon('play');
  if(playIcon) play.appendChild(playIcon);
  cover.appendChild(play);
  const copy=document.createElement('span');
  copy.className='media-card-copy';
  const title=document.createElement('span');
  title.className='media-card-title';
  title.textContent=item.title;
  const kind=document.createElement('span');
  kind.className='media-card-kind';
  kind.textContent=item.kind==='video'?mediaText.mediaLibraryVideo:mediaText.mediaLibraryAudio;
  copy.append(title,kind);
  button.append(cover,copy);
  shell.appendChild(button);
  return shell;
}

function renderMediaCatalog(payload){
  const grid=document.getElementById('mediaGrid');
  grid.replaceChildren(...payload.items.map(mediaCard));
  grid.hidden=payload.items.length===0;
  const truncated=document.getElementById('mediaTruncated');
  truncated.hidden=!payload.truncated;
  truncated.textContent=payload.truncated?mediaText.mediaLibraryTruncated:'';
  if(payload.items.length===0){
    showMediaState('empty',mediaText.mediaLibraryEmpty);
  }else{
    hideMediaState();
  }
}

async function loadMediaCatalog(){
  showMediaState('loading',mediaText.mediaLibraryLoading);
  document.getElementById('mediaGrid').hidden=true;
  try{
    const response=await fetch('/api/media',{cache:'no-store'});
    if(!response.ok) throw new Error('Catalog unavailable');
    const payload=await response.json();
    if(!payload||!Array.isArray(payload.items)||typeof payload.truncated!=='boolean'){
      throw new Error('Invalid catalog');
    }
    renderMediaCatalog(payload);
  }catch(e){
    showMediaState('error',mediaText.mediaLibraryError,loadMediaCatalog);
  }
}

async function playMedia(item,button){
  button.disabled=true;
  button.classList.add('is-starting');
  showMediaState('loading',mediaText.mediaLibraryStarting.replace('{title}',item.title));
  try{
    const response=await fetch('/api/media/play',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mediaId:item.id,tileId:mediaTileId})
    });
    if(response.status===403){
      button.classList.remove('is-starting');
      showMediaState('error',mediaText.mediaLibraryUnavailable);
      return;
    }
    if(!response.ok) throw new Error('Launch failed');
    hideMediaState();
  }catch(e){
    button.classList.remove('is-starting');
    showMediaState('error',mediaText.mediaLibraryPlayError);
  }finally{
    button.disabled=false;
  }
}

function handleMediaKeys(event){
  if(event.key==='Escape'){
    event.preventDefault();
    mediaHome();
    return;
  }
  if(!event.target.matches('.media-card')||!event.key.startsWith('Arrow')) return;
  const cards=Array.from(document.querySelectorAll('.media-card'));
  const index=cards.indexOf(event.target);
  const columns=getComputedStyle(document.getElementById('mediaGrid')).gridTemplateColumns.split(' ').length;
  const offset={ArrowLeft:-1,ArrowRight:1,ArrowUp:-columns,ArrowDown:columns}[event.key];
  const target=cards[index+offset];
  if(target){ event.preventDefault(); target.focus(); }
}

async function initializeMediaLibrary(){
  document.getElementById('mediaBack').addEventListener('click',mediaHome);
  document.addEventListener('keydown',handleMediaKeys);
  mediaTileId=new URLSearchParams(window.location.search).get('tile')||'';
  try{
    const response=await fetch('/api/config',{cache:'no-store'});
    if(!response.ok) throw new Error('Config unavailable');
    mediaConfig=await response.json();
    await loadMediaText(mediaConfig.language);
    const tile=mediaTile(mediaConfig,mediaTileId);
    if(!tile){ mediaHome(); return; }
    applyMediaTheme(mediaConfig);
    localizeMediaPage(tile);
    await loadMediaCatalog();
  }catch(e){
    await loadMediaText('en');
    localizeMediaPage(null);
    showMediaState('error',mediaText.mediaLibraryError,()=>window.location.reload());
  }
}

initializeMediaLibrary();
