const SUPPORTED_INTERFACE_LANGUAGES=Object.freeze(['de','en']);

function normalizedInterfaceLanguage(language){
  return SUPPORTED_INTERFACE_LANGUAGES.includes(language)?language:'en';
}

async function loadInterfaceLanguage(language){
  const normalized=normalizedInterfaceLanguage(language);
  try{
    const response=await fetch('/frontend/locales/'+normalized+'.json',{cache:'no-store'});
    if(!response.ok) throw new Error('Locale could not be loaded');
    const locale=await response.json();
    if(!locale||typeof locale!=='object'||Array.isArray(locale)||!locale.adminTitle){
      throw new Error('Invalid locale response');
    }
    uiText=locale;
  }catch(e){
    // Keep the installer-rendered language as a complete offline fallback.
  }
  document.documentElement.lang=normalized;
}

function renderLocalizedChrome(){
  document.getElementById('pinTitle').textContent=uiText.pinTitle;
  document.getElementById('pinInput').placeholder=uiText.pinPlaceholder;
  setIconLabel(document.getElementById('pinCancelBtn'),'back',uiText.back);
  document.getElementById('updateProgressTitle').textContent=uiText.updateProgress;
  setIconLabel(document.getElementById('installCopyBtn'),'copy',uiText.copyCommand);
  setIconLabel(document.getElementById('installCloseBtn'),'close',uiText.close);
  document.getElementById('themePickerTitle').textContent=uiText.adminAppearance;
  setIconLabel(document.getElementById('themePickerCloseBtn'),'close',uiText.close);
  document.getElementById('timerBlockTitle').textContent=uiText.timerExpiredTitle;
  document.getElementById('timerBlockBody').textContent=uiText.timerExpiredBody;
  document.getElementById('timerBlockPin').placeholder=uiText.pinPlaceholder;
  document.getElementById('timerBlockExitBtn').textContent=uiText.timerExit;
  document.getElementById('timerOptionOff').textContent=uiText.timerOff;
  document.getElementById('timerOption15').textContent=uiText.timerMinutes15;
  document.getElementById('timerOption30').textContent=uiText.timerMinutes30;
  document.getElementById('timerOption60').textContent=uiText.timerMinutes60;
  document.getElementById('timerOptionCustom').textContent=uiText.timerCustom;
  document.getElementById('layoutOptionLarge').textContent=uiText.layoutLarge;
  document.getElementById('layoutOptionSmall').textContent=uiText.layoutSmall;
  document.getElementById('worldThemeOptionsTitle').textContent=uiText.worldThemeOptions||'World theme effects';
  document.getElementById('themeMotionLabel').textContent=uiText.themeMotion||'Gentle background motion';
  document.getElementById('themeTimeOfDayLabel').textContent=uiText.themeTimeOfDay||'Match the local time of day';
  document.getElementById('worldThemeOptionsHint').textContent=uiText.worldThemeHint||'Available for illustrated worlds. The device reduced-motion preference always takes priority.';
  document.getElementById('feedbackOptionsTitle').textContent=uiText.feedbackOptions||'Audio feedback';
  document.getElementById('soundFeedbackLabel').textContent=uiText.soundFeedback||'Gentle local sounds';
  document.getElementById('speechFeedbackLabel').textContent=uiText.speechFeedback||'Read app names aloud (Linux)';
  document.getElementById('feedbackOptionsHint').textContent=uiText.feedbackHint||'Both options are per child and off by default.';
  document.getElementById('accessibilityOptionsTitle').textContent=uiText.accessibilityOptions||'Accessibility presets';
  document.getElementById('accessibilityLargeTextLabel').textContent=uiText.accessibilityLargeText||'Larger text';
  document.getElementById('accessibilityHighContrastLabel').textContent=uiText.accessibilityHighContrast||'High contrast';
  document.getElementById('accessibilityReducedMotionLabel').textContent=uiText.accessibilityReducedMotion||'Reduce motion';
  document.getElementById('accessibilityKeyboardFocusLabel').textContent=uiText.accessibilityKeyboardFocus||'Keyboard mode with a strong focus marker';
  document.getElementById('accessibilityOptionsHint').textContent=uiText.accessibilityHint||'Combine any options for this child profile.';
  document.getElementById('cfgTimerCustom').placeholder=uiText.timerMinutes;
  document.getElementById('cfgPin').placeholder=uiText.pinSet;
  document.getElementById('cfgPinConfirm').placeholder=uiText.pinConfirm;
  setIconLabel(document.getElementById('setPinBtn'),'lock',cfg&&cfg.pinConfigured?uiText.pinChange:uiText.pinSet);
  setIconLabel(document.getElementById('removePinBtn'),'delete',uiText.pinRemove);
  setIconLabel(document.getElementById('updateNowBtn'),'update',uiText.updateNow);
  setIconLabel(document.getElementById('exportConfigBtn'),'download',uiText.exportConfig);
  setIconLabel(document.getElementById('importConfigBtn'),'upload',uiText.importConfig);
  setIconLabel(document.getElementById('exportDiagnosticsBtn'),'diagnostics',uiText.exportDiagnostics);
  document.getElementById('backupTitle').textContent=uiText.backupTitle;
  document.getElementById('backupPinPreserved').textContent=uiText.backupPinPreserved;
  setIconLabel(document.getElementById('restoreBackupBtn'),'restore',uiText.backupRestore);
}
