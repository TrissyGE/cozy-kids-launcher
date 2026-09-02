const COZY_ACCESSIBILITY_CLASSES=Object.freeze({
  accessibilityLargeText:'access-large-text',
  accessibilityHighContrast:'access-high-contrast',
  accessibilityReducedMotion:'access-reduced-motion',
  accessibilityKeyboardFocus:'access-keyboard-focus'
});

function accessibilityClassTarget(element){
  if(!element) return null;
  return element===document.body?document.documentElement:element;
}

function applyAccessibilityRuntime(element,config){
  const target=accessibilityClassTarget(element);
  if(!target) return null;
  const active=[];
  for(const [field,className] of Object.entries(COZY_ACCESSIBILITY_CLASSES)){
    const enabled=!!config&&config[field]===true;
    target.classList.toggle(className,enabled);
    if(enabled) active.push(field);
  }
  return active;
}
