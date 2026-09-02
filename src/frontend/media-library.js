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
  mediaLibraryTruncated:'Showing the first 2,000 items.',
  mediaLibraryViews:'Media library views',
  mediaLibraryAll:'All media',
  mediaLibraryFavorites:'Favorites',
  mediaLibraryRecents:'Recently played',
  mediaLibraryFavoritesEmpty:'No favorites yet. Use the star on a cover to add one.',
  mediaLibraryRecentsEmpty:'Nothing has been played here yet.',
  mediaLibraryFavoriteAdd:'Add {title} to favorites',
  mediaLibraryFavoriteRemove:'Remove {title} from favorites',
  mediaLibraryFavoriteError:'This favorite could not be saved.'
});

let mediaText=MEDIA_FALLBACK_TEXT;
let mediaConfig=null;
let mediaTileId='';
let mediaItems=[];
let mediaFavoriteIds=new Set();
let mediaRecentIds=[];
let mediaFilter='all';

function mediaHome(){ window.location='/index.html'; }

function mediaTile(config,tileId){
  return (config.tiles||[]).find(tile=>tile.id===tileId&&tile.visible!==false&&
    Array.isArray(tile.cmd)&&tile.cmd.length===1&&tile.cmd[0]==='special:filme-musik');
}

function applyMediaTheme(config){
  applyThemeRuntime(document.body,config,['media-page']);
  applyAccessibilityRuntime(document.body,config);
  scheduleThemeRuntimeRefresh(document.body,()=>mediaConfig,['media-page']);
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
  const filters=document.getElementById('mediaFilters');
  filters.setAttribute('aria-label',mediaText.mediaLibraryViews);
  const labels={
    all:mediaText.mediaLibraryAll,
    favorites:mediaText.mediaLibraryFavorites,
    recents:mediaText.mediaLibraryRecents
  };
  filters.querySelectorAll('[data-media-filter]').forEach(button=>{
    button.textContent=labels[button.dataset.mediaFilter];
  });
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

function mediaFavoriteLabel(item,favorite){
  return (favorite?mediaText.mediaLibraryFavoriteRemove:mediaText.mediaLibraryFavoriteAdd)
    .replace('{title}',item.title);
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
  const favorite=mediaFavoriteIds.has(item.id);
  const favoriteButton=document.createElement('button');
  favoriteButton.type='button';
  favoriteButton.className='media-favorite';
  favoriteButton.dataset.favoriteId=item.id;
  favoriteButton.setAttribute('aria-pressed',favorite?'true':'false');
  setIconOnly(favoriteButton,'star',mediaFavoriteLabel(item,favorite));
  favoriteButton.addEventListener('click',()=>toggleMediaFavorite(item,favoriteButton));
  shell.append(button,favoriteButton);
  return shell;
}

function visibleMediaItems(){
  if(mediaFilter==='favorites'){
    return mediaItems.filter(item=>mediaFavoriteIds.has(item.id));
  }
  if(mediaFilter==='recents'){
    const byId=new Map(mediaItems.map(item=>[item.id,item]));
    return mediaRecentIds.map(mediaId=>byId.get(mediaId)).filter(Boolean);
  }
  return mediaItems;
}

function emptyMediaMessage(){
  if(mediaFilter==='favorites') return mediaText.mediaLibraryFavoritesEmpty;
  if(mediaFilter==='recents') return mediaText.mediaLibraryRecentsEmpty;
  return mediaText.mediaLibraryEmpty;
}

function renderMediaCatalog(){
  const items=visibleMediaItems();
  const grid=document.getElementById('mediaGrid');
  grid.replaceChildren(...items.map(mediaCard));
  grid.hidden=items.length===0;
  document.querySelectorAll('[data-media-filter]').forEach(button=>{
    const active=button.dataset.mediaFilter===mediaFilter;
    button.classList.toggle('is-active',active);
    button.setAttribute('aria-pressed',active?'true':'false');
  });
  if(items.length===0){
    showMediaState('empty',emptyMediaMessage());
  }else{
    hideMediaState();
  }
}

function setMediaFilter(filter){
  if(!['all','favorites','recents'].includes(filter)) return;
  mediaFilter=filter;
  renderMediaCatalog();
  const first=document.querySelector('.media-card');
  if(first) first.focus();
}

async function loadMediaCatalog(){
  showMediaState('loading',mediaText.mediaLibraryLoading);
  document.getElementById('mediaGrid').hidden=true;
  try{
    const response=await fetch('/api/media',{cache:'no-store'});
    if(!response.ok) throw new Error('Catalog unavailable');
    const payload=await response.json();
    if(!payload||!Array.isArray(payload.items)||typeof payload.truncated!=='boolean'||
        !Array.isArray(payload.favoriteIds)||!Array.isArray(payload.recentIds)){
      throw new Error('Invalid catalog');
    }
    mediaItems=payload.items;
    mediaFavoriteIds=new Set(payload.favoriteIds);
    mediaRecentIds=payload.recentIds;
    const truncated=document.getElementById('mediaTruncated');
    truncated.hidden=!payload.truncated;
    truncated.textContent=payload.truncated?mediaText.mediaLibraryTruncated:'';
    renderMediaCatalog();
  }catch(e){
    showMediaState('error',mediaText.mediaLibraryError,loadMediaCatalog);
  }
}

async function toggleMediaFavorite(item,button){
  const favorite=!mediaFavoriteIds.has(item.id);
  button.disabled=true;
  try{
    const response=await fetch('/api/media/favorite',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({mediaId:item.id,tileId:mediaTileId,favorite:favorite})
    });
    if(response.status===403){
      showMediaState('error',mediaText.mediaLibraryUnavailable);
      return;
    }
    if(!response.ok) throw new Error('Favorite failed');
    const payload=await response.json();
    if(!payload||payload.favorite!==favorite) throw new Error('Invalid favorite response');
    if(favorite) mediaFavoriteIds.add(item.id); else mediaFavoriteIds.delete(item.id);
    renderMediaCatalog();
    const updated=Array.from(document.querySelectorAll('[data-favorite-id]'))
      .find(candidate=>candidate.dataset.favoriteId===item.id);
    if(updated) updated.focus();
    else document.querySelector('[data-media-filter="favorites"]').focus();
  }catch(e){
    showMediaState('error',mediaText.mediaLibraryFavoriteError);
  }finally{
    button.disabled=false;
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
    mediaRecentIds=[item.id,...mediaRecentIds.filter(mediaId=>mediaId!==item.id)].slice(0,50);
    if(mediaFilter==='recents') renderMediaCatalog();
    hideMediaState();
    playCelebrationMoment(mediaConfig);
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
  document.getElementById('mediaFilters').addEventListener('click',event=>{
    const button=event.target.closest('[data-media-filter]');
    if(button) setMediaFilter(button.dataset.mediaFilter);
  });
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
