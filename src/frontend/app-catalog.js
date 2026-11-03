let catalogQuery='', catalogCategory='all', catalogStatus='all';

function catalogText(record,key){
  const value=record[key+'_'+cfg.language]||record[key+'_en'];
  return typeof value==='string'?value:'';
}

function catalogName(rec){
  return catalogText(rec,'name')||catalogText(rec,'label')||rec.id;
}

function catalogAdded(rec){
  return cfg.tiles.some(tile=>tile.id===rec.id||JSON.stringify(tile.cmd||[])===JSON.stringify(rec.cmd||[]));
}

function catalogCategoryLabel(category){
  return ({all:uiText.catalogAll,creative:uiText.catalogCreative,learning:uiText.catalogLearning,
    game:uiText.catalogGames,browser:uiText.catalogWeb})[category]||category;
}

function renderRecommendations(){
  renderRetroEmulators();
  const container=document.getElementById('recommendations');
  container.replaceChildren();
  const panel=document.createElement('section'); panel.className='panel';
  const header=document.createElement('div'); header.className='catalog-heading';
  const title=document.createElement('h2'); title.textContent=uiText.appBrowserTitle;
  const refresh=document.createElement('button'); refresh.className='smallbtn';
  refresh.id='catalogRefresh'; setIconLabel(refresh,'refresh',uiText.catalogRefresh);
  refresh.disabled=recommendationState==='loading'; refresh.onclick=loadRecommendations;
  const statusButton=document.createElement('button'); statusButton.className='smallbtn';
  statusButton.id='catalogInstallStatus'; setIconLabel(statusButton,'download',uiText.packageStatus); statusButton.onclick=openPackageStatus;
  header.append(title,refresh,statusButton); panel.appendChild(header); container.appendChild(panel);
  if(recommendationState!=='ready'){
    const status=document.createElement('div'); status.id='recommendationState';
    status.setAttribute('aria-live','polite');
    const messages={loading:uiText.recommendationsLoading,empty:uiText.recommendationsEmpty,error:uiText.recommendationsError};
    renderUiState(status,recommendationState,messages[recommendationState],recommendationState==='loading'?null:loadRecommendations);
    panel.appendChild(status); return;
  }
  const controls=document.createElement('div'); controls.className='catalog-controls';
  const searchLabel=document.createElement('label'); searchLabel.textContent=uiText.catalogSearch;
  const search=document.createElement('input'); search.type='search'; search.id='catalogSearch';
  search.value=catalogQuery; search.maxLength=120;
  search.oninput=()=>{catalogQuery=search.value; renderCatalogResults();}; searchLabel.appendChild(search);
  controls.appendChild(searchLabel);
  function addFilter(id,labelText,values,current,change){
    const label=document.createElement('label'); label.textContent=labelText;
    const select=document.createElement('select'); select.id=id;
    for(const [value,text] of values){const option=document.createElement('option'); option.value=value; option.textContent=text; select.appendChild(option);}
    select.value=current; select.onchange=()=>{change(select.value); renderCatalogResults();};
    label.appendChild(select); controls.appendChild(label);
  }
  addFilter('catalogCategory',uiText.catalogCategory,['all','creative','learning','game','browser'].map(key=>[key,catalogCategoryLabel(key)]),catalogCategory,value=>catalogCategory=value);
  addFilter('catalogStatus',uiText.catalogStatus,[['all',uiText.catalogAll],['installed',uiText.installed],['missing',uiText.notInstalled],['added',uiText.added]],catalogStatus,value=>catalogStatus=value);
  const count=document.createElement('p'); count.id='catalogCount'; count.className='muted'; count.setAttribute('role','status');
  const results=document.createElement('div'); results.id='catalogResults';
  const hint=document.createElement('p'); hint.className='muted'; hint.textContent=uiText.catalogHint;
  panel.append(controls,count,results,hint); renderCatalogResults();
}

function renderCatalogResults(){
  const results=document.getElementById('catalogResults'); if(!results) return;
  results.replaceChildren();
  const query=catalogQuery.trim().toLocaleLowerCase(cfg.language);
  const generalApps=recommendations.filter(rec=>!rec.retroEmulator);
  const matches=generalApps.filter(rec=>{
    const text=[catalogName(rec),catalogText(rec,'label'),catalogText(rec,'desc'),catalogCategoryLabel(rec.category)].join(' ').toLocaleLowerCase(cfg.language);
    return (!query||text.includes(query))&&(catalogCategory==='all'||rec.category===catalogCategory)&&
      (catalogStatus==='all'||(catalogStatus==='installed'&&rec.installed)||(catalogStatus==='missing'&&!rec.installed)||(catalogStatus==='added'&&catalogAdded(rec)));
  }).sort((a,b)=>Number(catalogAdded(a))-Number(catalogAdded(b))||Number(b.installed)-Number(a.installed)||catalogName(a).localeCompare(catalogName(b),cfg.language));
  document.getElementById('catalogCount').textContent=localizedCount('catalogCount',matches.length,generalApps.length);
  if(!matches.length){renderUiState(results,'empty',uiText.catalogNoMatches); return;}
  const grid=document.createElement('div'); grid.className='rec-grid';
  for(const rec of matches){
    const card=document.createElement('article'); card.className='rec-card'; card.dataset.catalogId=rec.id;
    const name=document.createElement('h3'); name.className='name'; name.textContent=catalogName(rec);
    const desc=document.createElement('div'); desc.className='desc'; desc.textContent=catalogText(rec,'desc');
    const state=document.createElement('div'); state.className='status '+(rec.installed?'installed':'missing');
    state.textContent=rec.category==='browser'?uiText.catalogWeb:rec.installed?uiText.installed:uiText.notInstalled;
    const actions=document.createElement('div'); actions.className='actions';
    const button=document.createElement('button'); button.className='smallbtn';
    if(!rec.installed){
      setIconLabel(button,'download',uiText.install);
      button.disabled=!catalogCanInstall(rec);
      button.onclick=()=>triggerInstall(rec);
    }
    else if(rec.installOnly){button.hidden=true;}
    else if(catalogAdded(rec)){button.disabled=true; setIconLabel(button,'save',uiText.added);}
    else {setIconLabel(button,'add',uiText.addTile); button.onclick=()=>addCatalogTile(rec,button);}
    actions.appendChild(button);
    card.append(createTileVisual(rec.emoji,'emoji'),name,desc,state,actions);
    if(!rec.installed&&!catalogCanInstall(rec)) card.append(catalogPackageHint(rec));
    card.append(catalogDetails(rec));
    grid.appendChild(card);
  }
  results.appendChild(grid);
}

function catalogCanInstall(rec){
  return !rec.packageRoute||rec.packageRoute.mode==='direct';
}

function catalogPackageHint(rec){
  const hint=document.createElement('p');
  hint.className='muted';
  hint.textContent=uiText.packageUnsupported;
  if(rec.packageRoute?.package){
    const name=document.createElement('code');
    name.textContent=rec.packageRoute.package;
    hint.append(' ',name);
  }
  return hint;
}

function catalogReviewDate(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value)) return uiText.catalogUnknown;
  const date=new Date(value+'T00:00:00Z');
  if(Number.isNaN(date.getTime())||date.toISOString().slice(0,10)!==value) return uiText.catalogUnknown;
  try {return date.toLocaleDateString(cfg.language,{year:'numeric',month:'short',day:'numeric',timeZone:'UTC'});}
  catch(error){return value;}
}

function catalogDetails(rec){
  const details=document.createElement('details'); details.className='catalog-details';
  const summary=document.createElement('summary'); summary.textContent=uiText.catalogDetails; details.appendChild(summary);
  const list=document.createElement('dl');
  function row(label,value){const term=document.createElement('dt'); term.textContent=label; const description=document.createElement('dd'); description.textContent=value||uiText.catalogUnknown; list.append(term,description);}
  const info=rec.guidance||{};
  row(uiText.catalogAge,catalogText(info,'age'));
  row(uiText.catalogOffline,({yes:uiText.catalogOfflineYes,partial:uiText.catalogOfflinePartial,no:uiText.catalogOfflineNo})[info.offline]);
  row(uiText.catalogLicense,info.license);
  row(uiText.catalogInput,(info.input||[]).map(key=>({mouse:uiText.catalogMouse,keyboard:uiText.catalogKeyboard,touch:uiText.catalogTouch})[key]).filter(Boolean).join(', '));
  row(uiText.catalogNetwork,[catalogText(info,'network'),rec.category==='browser'?uiText.catalogWebPrivacy:''].filter(Boolean).join(' '));
  row(uiText.catalogReviewed,catalogReviewDate(info.reviewed));
  details.appendChild(list);
  const sources=document.createElement('div'); sources.className='catalog-sources';
  const seen=new Set();
  function addSource(value,label){
    if(typeof value!=='string') return;
    let url;
    try {url=new URL(value);}catch(error){return;}
    if(url.protocol!=='https:'||!url.hostname||url.username||url.password||seen.has(url.href)) return;
    seen.add(url.href);
    const link=document.createElement('a'); link.href=url.href; link.target='_blank'; link.rel='noopener noreferrer';
    link.textContent=label||uiText.catalogSource;
    sources.appendChild(link);
  }
  addSource(info.source,uiText.catalogSource);
  for(const reference of (Array.isArray(info.references)?info.references:[]).slice(0,4)){
    if(reference&&typeof reference==='object') addSource(reference.url,catalogText(reference,'label'));
  }
  if(sources.childElementCount) details.appendChild(sources);
  const aptPackage=rec.packages?.apt??rec.package;
  if(rec.installed&&catalogCanInstall(rec)&&typeof aptPackage==='string'&&aptPackage){
    const maintenance=document.createElement('div'); maintenance.className='actions catalog-maintenance';
    for(const [operation,label] of [['update',uiText.packageMaintenance.checkUpdate],['remove',uiText.packageMaintenance.remove]]){
      const button=document.createElement('button');
      button.type='button'; button.className='smallbtn'; button.dataset.packageOperation=operation;
      button.textContent=label; button.onclick=()=>preparePackageOperation(rec,operation);
      maintenance.appendChild(button);
    }
    details.appendChild(maintenance);
  }
  return details;
}

async function addCatalogTile(rec,button){
  if(rec.installOnly||catalogAdded(rec)) return;
  const tile={id:rec.id,label:catalogText(rec,'label')||rec.id,emoji:rec.emoji||'✨',cmd:rec.cmd||[],visible:true};
  cfg.tiles.push(tile); button.disabled=true;
  try {await persistConfig(); renderAll();}
  catch(error){
    const index=cfg.tiles.indexOf(tile); if(index>=0) cfg.tiles.splice(index,1);
    button.disabled=false;
    const message=document.createElement('p'); message.setAttribute('role','alert'); message.textContent=uiText.saveError;
    button.closest('.rec-card').appendChild(message);
  }
}
