const COZY_FEEDBACK_TONES=Object.freeze({
  navigate:[440,494,.055],
  launch:[523,659,.10],
  success:[659,880,.16],
  return:[587,698,.10],
  blocked:[262,196,.14]
});
let cozyFeedbackAudioContext=null;
let cozySpeechTimer=null;
let cozyLastSpeechTile='';
let cozyLastSpeechAt=0;

function feedbackAudioContext(){
  const AudioContextClass=window.AudioContext||window.webkitAudioContext;
  if(!AudioContextClass) return null;
  if(!cozyFeedbackAudioContext) cozyFeedbackAudioContext=new AudioContextClass();
  return cozyFeedbackAudioContext;
}

function playFeedbackSound(kind){
  if(!cfg||cfg.soundFeedbackEnabled!==true) return false;
  const tone=COZY_FEEDBACK_TONES[kind];
  if(!tone) return false;
  try{
    const context=feedbackAudioContext();
    if(!context) return false;
    if(context.state==='suspended') context.resume().catch(()=>{});
    const start=context.currentTime;
    const oscillator=context.createOscillator();
    const gain=context.createGain();
    oscillator.type='sine';
    oscillator.frequency.setValueAtTime(tone[0],start);
    oscillator.frequency.exponentialRampToValueAtTime(tone[1],start+tone[2]);
    gain.gain.setValueAtTime(.0001,start);
    gain.gain.exponentialRampToValueAtTime(.035,start+.012);
    gain.gain.exponentialRampToValueAtTime(.0001,start+tone[2]);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.onended=()=>{ oscillator.disconnect(); gain.disconnect(); };
    oscillator.start(start);
    oscillator.stop(start+tone[2]+.01);
    return true;
  }catch(e){
    return false;
  }
}

function cancelTileSpeech(){
  if(cozySpeechTimer!==null) clearTimeout(cozySpeechTimer);
  cozySpeechTimer=null;
}

function feedbackUiAllowsSpeech(){
  const kids=document.getElementById('kids');
  if(!kids||kids.classList.contains('hidden')) return false;
  return [
    'pin','themeOverlay','installOverlay','profileOverlay','firstRunOverlay',
    'availabilityBlock','timerBlock','timerWarning','startOverlay'
  ].every(id=>{
    const element=document.getElementById(id);
    return !element||element.classList.contains('hidden');
  });
}

function scheduleTileSpeech(tileId){
  cancelTileSpeech();
  if(
    !cfg||cfg.speechFeedbackEnabled!==true||
    !features.speechFeedbackAvailable||
    typeof tileId!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(tileId)
  ) return;
  cozySpeechTimer=setTimeout(()=>{
    cozySpeechTimer=null;
    if(!feedbackUiAllowsSpeech()) return;
    const focused=document.activeElement;
    if(!focused||focused.dataset.tileId!==tileId) return;
    const now=performance.now();
    if(cozyLastSpeechTile===tileId&&now-cozyLastSpeechAt<1200) return;
    cozyLastSpeechTile=tileId;
    cozyLastSpeechAt=now;
    fetch('/api/feedback/speak',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({tileId})
    }).catch(()=>{});
  },240);
}

function announceFocusedTile(){
  const focused=document.activeElement;
  if(focused&&focused.matches('#grid .tile[data-tile-id]')){
    scheduleTileSpeech(focused.dataset.tileId);
  }
}
