function profileText(){
  return PROFILE_TEXT[cfg&&cfg.language==='de'?'de':'en'];
}

function activeProfileSummary(){
  const profiles=Array.isArray(cfg&&cfg.profiles)?cfg.profiles:[];
  return profiles.find(profile=>profile.id===cfg.activeProfileId)||{
    id:cfg.activeProfileId||'default',
    name:cfg.name||'',
    avatar:cfg.avatar||''
  };
}

function profileStorageKey(){
  return 'cozyLastLaunched:'+(cfg&&cfg.activeProfileId?cfg.activeProfileId:'default');
}

function renderProfileButton(){
  const button=document.getElementById('profileBtn');
  if(!button||!cfg) return;
  const profile=activeProfileSummary();
  const avatar=document.createElement('span');
  avatar.className='profile-button-avatar';
  avatar.setAttribute('aria-hidden','true');
  avatar.textContent=profile.avatar||'👤';
  const name=document.createElement('span');
  name.textContent=profile.name||profileText().pickerTitle;
  button.replaceChildren(avatar,name);
  button.setAttribute('aria-label',profileText().pickerTitle+': '+(profile.name||''));
  button.setAttribute('aria-haspopup','dialog');
}

function renderProfileAdmin(){
  const text=profileText();
  document.getElementById('profileManageHint').textContent=text.manageHint;
  document.getElementById('profileListTitle').textContent=text.listTitle;
  document.getElementById('profileEditorTitle').textContent=text.editorTitle;
  document.getElementById('profileNameLabel').textContent=text.name;
  document.getElementById('profileAvatarLabel').textContent=text.avatar;
  document.getElementById('profileLauncherTitleLabel').textContent=text.launcherTitle;
  document.getElementById('profileCreateTitle').textContent=text.createTitle;
  document.getElementById('cfgProfileName').value=cfg.name||'';
  document.getElementById('cfgProfileAvatar').value=cfg.avatar||'';
  const nameInput=document.getElementById('newProfileName');
  const avatarInput=document.getElementById('newProfileAvatar');
  nameInput.placeholder=text.namePlaceholder;
  avatarInput.placeholder=text.avatarPlaceholder;
  setIconLabel(document.getElementById('createProfileBtn'),'add',text.create);

  const list=document.getElementById('profileList');
  list.replaceChildren();
  for(const profile of cfg.profiles||[]){
    const active=profile.id===cfg.activeProfileId;
    const card=document.createElement('article');
    card.className='profile-card'+(active?' active':'');
    card.dataset.profileId=profile.id;
    const main=document.createElement('div');
    main.className='profile-card-main';
    const avatar=document.createElement('span');
    avatar.className='profile-avatar';
    avatar.setAttribute('aria-hidden','true');
    avatar.textContent=profile.avatar||'👤';
    const details=document.createElement('div');
    const name=document.createElement('strong');
    name.textContent=profile.name;
    details.appendChild(name);
    if(active){
      const badge=document.createElement('span');
      badge.className='profile-badge';
      badge.textContent=text.active;
      details.appendChild(badge);
    }
    main.append(avatar,details);
    const actions=document.createElement('div');
    actions.className='profile-actions';
    if(!active){
      const select=document.createElement('button');
      select.type='button';
      select.className='smallbtn';
      setIconLabel(select,'child',text.select);
      select.onclick=()=>activateProfile(profile.id,{admin:true});
      actions.appendChild(select);
      const remove=document.createElement('button');
      remove.type='button';
      remove.className='smallbtn danger';
      setIconLabel(remove,'delete',text.remove);
      remove.onclick=()=>deleteProfileFromAdmin(profile.id);
      actions.appendChild(remove);
    }
    card.append(main,actions);
    list.appendChild(card);
  }
}

async function profileApi(path,body){
  const response=await fetch(path,{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)
  });
  const result=await response.json();
  if(!response.ok||result.status!=='ok') throw new Error(result.message||'Profile request failed');
  return result;
}

async function activateProfile(profileId,options={}){
  if(!cfg||profileId===cfg.activeProfileId){
    if(options.picker) closeProfilePicker();
    return;
  }
  const message=options.admin
    ?document.getElementById('profileAdminMessage')
    :document.getElementById('profilePickerMessage');
  if(message) renderUiState(message,'loading',uiText.saveLoading);
  try{
    const result=await profileApi('/api/profiles/select',{profileId:profileId});
    cfg=result.config;
    adminPage=0;
    adminTileQuery='';
    adminTileVisibility='all';
    adminSelectedTileIds.clear();
    focusedTileIndex=0;
    timerWarningShown=false;
    if(message) clearUiState(message);
    if(options.picker) closeProfilePicker();
    await pollAvailability();
    if(options.admin) await loadActivityDashboard();
    renderAll();
    pollTimer();
  }catch(e){
    if(message) renderUiState(message,'error',profileText().error);
  }
}

async function createProfileFromAdmin(){
  const nameInput=document.getElementById('newProfileName');
  const avatarInput=document.getElementById('newProfileAvatar');
  const message=document.getElementById('profileAdminMessage');
  const name=nameInput.value.trim();
  if(!name){
    renderUiState(message,'error',profileText().nameRequired);
    nameInput.focus();
    return;
  }
  const button=document.getElementById('createProfileBtn');
  button.disabled=true;
  renderUiState(message,'loading',uiText.saveLoading);
  try{
    const created=await profileApi('/api/profiles/create',{name:name,avatar:avatarInput.value.trim()});
    cfg.profiles=created.profiles;
    nameInput.value='';
    avatarInput.value='';
    await activateProfile(created.profileId,{admin:true});
  }catch(e){
    renderUiState(message,'error',profileText().error);
  }finally{
    button.disabled=false;
  }
}

async function deleteProfileFromAdmin(profileId){
  if(!(await requestConfirmation(profileText().removeConfirm,profileText().remove))) return;
  const message=document.getElementById('profileAdminMessage');
  renderUiState(message,'loading',uiText.saveLoading);
  try{
    const result=await profileApi('/api/profiles/delete',{profileId:profileId});
    cfg.profiles=result.profiles;
    clearUiState(message);
    await loadActivityDashboard();
    renderProfileAdmin();
    renderProfileButton();
  }catch(e){
    renderUiState(message,'error',profileText().error);
  }
}

function renderProfilePicker(){
  const text=profileText();
  document.getElementById('profilePickerTitle').textContent=text.pickerTitle;
  document.getElementById('profilePickerHint').textContent=text.pickerHint;
  setIconLabel(document.getElementById('profilePickerClose'),'close',text.close);
  clearUiState(document.getElementById('profilePickerMessage'));
  const grid=document.getElementById('profilePickerGrid');
  grid.replaceChildren();
  for(const profile of cfg.profiles||[]){
    const button=document.createElement('button');
    button.type='button';
    button.className='profile-choice';
    button.dataset.profileId=profile.id;
    button.setAttribute('aria-pressed',String(profile.id===cfg.activeProfileId));
    const avatar=document.createElement('span');
    avatar.className='profile-choice-avatar';
    avatar.setAttribute('aria-hidden','true');
    avatar.textContent=profile.avatar||'👤';
    const name=document.createElement('strong');
    name.textContent=profile.name;
    button.append(avatar,name);
    button.onclick=()=>{
      if(profile.id===cfg.activeProfileId){ closeProfilePicker(); return; }
      if(cfg.pinConfigured) requestPin(()=>activateProfile(profile.id,{picker:true}));
      else activateProfile(profile.id,{picker:true});
    };
    grid.appendChild(button);
  }
}

function openProfilePicker(){
  const overlay=document.getElementById('profileOverlay');
  if(!overlay.classList.contains('hidden')) return;
  profilePickerReturnFocus=document.activeElement;
  renderProfilePicker();
  overlay.classList.remove('hidden');
  requestAnimationFrame(()=>{
    const active=overlay.querySelector('.profile-choice[aria-pressed="true"]');
    (active||overlay.querySelector('.profile-choice')||document.getElementById('profilePickerClose')).focus();
  });
}

function closeProfilePicker(){
  const overlay=document.getElementById('profileOverlay');
  if(overlay.classList.contains('hidden')) return;
  overlay.classList.add('hidden');
  clearUiState(document.getElementById('profilePickerMessage'));
  const returnFocus=profilePickerReturnFocus;
  profilePickerReturnFocus=null;
  if(returnFocus&&returnFocus.isConnected&&!returnFocus.disabled) returnFocus.focus();
}

document.addEventListener('keydown',event=>{
  const overlay=document.getElementById('profileOverlay');
  if(!overlay||overlay.classList.contains('hidden')||!document.getElementById('pin').classList.contains('hidden')) return;
  if(event.key==='Escape'){
    event.preventDefault();
    event.stopImmediatePropagation();
    closeProfilePicker();
    return;
  }
  if(event.key!=='Tab') return;
  const controls=Array.from(overlay.querySelectorAll('button:not([disabled])'));
  if(!controls.length) return;
  const index=controls.indexOf(document.activeElement);
  if(index<0||(event.shiftKey&&index===0)||(!event.shiftKey&&index===controls.length-1)){
    event.preventDefault();
    event.stopImmediatePropagation();
    controls[event.shiftKey?controls.length-1:0].focus();
  }
},true);
