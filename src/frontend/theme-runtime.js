const COZY_WORLD_THEME_IDS=Object.freeze([
  'wald','weltraum','ocean','dinosaurier','baustelle','prinzessin','bauernhof','katzen','hunde'
]);

let cozyThemeRefreshTimer=null;

function isWorldTheme(themeId){
  return COZY_WORLD_THEME_IDS.includes(themeId);
}

function themePeriodAt(value=new Date()){
  const hour=value.getHours();
  if(hour>=5&&hour<11) return 'morning';
  if(hour>=11&&hour<17) return 'day';
  if(hour>=17&&hour<21) return 'evening';
  return 'night';
}

function applyThemeRuntime(element,config,baseClasses=[],value=new Date()){
  if(!element) return null;
  const themeId=(config&&config.theme)||'rosa';
  const world=isWorldTheme(themeId);
  const classes=Array.isArray(baseClasses)
    ? baseClasses.filter(Boolean)
    : String(baseClasses||'').split(/\s+/).filter(Boolean);
  classes.push('theme-'+themeId);
  if(world){
    classes.push('theme-world');
    if(config.themeMotionEnabled===true) classes.push('theme-world-motion');
    if(config.themeTimeOfDayEnabled===true){
      const period=themePeriodAt(value);
      classes.push('theme-time-'+period);
      element.dataset.themePeriod=period;
    }else{
      delete element.dataset.themePeriod;
    }
  }else{
    delete element.dataset.themePeriod;
  }
  element.className=classes.join(' ');
  return {themeId,world,period:element.dataset.themePeriod||null};
}

function nextThemePeriodDelay(value=new Date()){
  for(const hour of [5,11,17,21]){
    const boundary=new Date(value);
    boundary.setHours(hour,0,0,0);
    if(boundary>value) return boundary-value+1000;
  }
  const tomorrow=new Date(value);
  tomorrow.setDate(tomorrow.getDate()+1);
  tomorrow.setHours(5,0,0,0);
  return tomorrow-value+1000;
}

function scheduleThemeRuntimeRefresh(element,configProvider,baseClasses=[]){
  if(cozyThemeRefreshTimer!==null){
    clearTimeout(cozyThemeRefreshTimer);
    cozyThemeRefreshTimer=null;
  }
  const config=configProvider();
  if(!config||!isWorldTheme(config.theme)||config.themeTimeOfDayEnabled!==true) return;
  cozyThemeRefreshTimer=setTimeout(()=>{
    const current=configProvider();
    applyThemeRuntime(element,current,baseClasses);
    scheduleThemeRuntimeRefresh(element,configProvider,baseClasses);
  },nextThemePeriodDelay());
}
