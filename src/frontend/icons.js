const SVG_NAMESPACE='http://www.w3.org/2000/svg';

const LOCAL_ICON_PATHS=Object.freeze({
  'nav-left':['M15 18l-6-6 6-6'],
  'nav-right':['M9 6l6 6-6 6'],
  back:['M19 12H5','M11 18l-6-6 6-6'],
  save:['M5 4h11l3 3v13H5z','M8 4v6h8V4','M8 20v-6h8v6'],
  add:['M12 5v14','M5 12h14'],
  overview:['M4 11l8-7 8 7','M6 10v10h12V10','M10 20v-6h4v6'],
  child:['M9 9a3 3 0 1 0 6 0 3 3 0 0 0-6 0','M5 20c.8-4 3.1-6 7-6s6.2 2 7 6'],
  apps:['M4 4h6v6H4z','M14 4h6v6h-6z','M4 14h6v6H4z','M14 14h6v6h-6z'],
  timer:['M12 7v5l3 2','M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18','M9 1h6'],
  appearance:['M12 3a9 9 0 0 0 0 18h1.5a2 2 0 0 0 0-4h-1a1.5 1.5 0 0 1 0-3H12','M7 9h.01','M10 6h.01','M15 6h.01','M18 10h.01'],
  system:['M4 7h10','M18 7h2','M14 4v6','M4 17h2','M10 17h10','M6 14v6'],
  show:['M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6','M9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0'],
  hide:['M3 3l18 18','M10.6 6.1A10 10 0 0 1 12 6c6 0 9.5 6 9.5 6a15 15 0 0 1-2.2 3','M6.2 6.2A15 15 0 0 0 2.5 12s3.5 6 9.5 6a10 10 0 0 0 3-.4','M9.9 9.9a3 3 0 0 0 4.2 4.2'],
  delete:['M4 7h16','M9 7V4h6v3','M7 7l1 13h8l1-13','M10 11v5','M14 11v5'],
  refresh:['M20 7v5h-5','M4 17v-5h5','M18.5 9A7 7 0 0 0 6 6.5L4 9','M5.5 15A7 7 0 0 0 18 17.5l2-2.5'],
  download:['M12 3v12','M7 10l5 5 5-5','M5 21h14'],
  upload:['M12 21V9','M7 14l5-5 5 5','M5 3h14'],
  diagnostics:['M6 3h9l3 3v7','M15 3v4h4','M10 20a5 5 0 1 1 0-10 5 5 0 0 1 0 10','M14 18l4 4'],
  restore:['M4 7v5h5','M5.5 16A8 8 0 1 0 6 6.5L4 9','M12 8v5l3 2'],
  power:['M12 2v9','M6.3 5.8a8 8 0 1 0 11.4 0'],
  exit:['M10 4H5v16h5','M14 8l4 4-4 4','M9 12h9'],
  lock:['M6 10h12v10H6z','M8 10V7a4 4 0 0 1 8 0v3','M12 14v2'],
  copy:['M9 9h11v11H9z','M4 15V4h11'],
  close:['M6 6l12 12','M18 6L6 18'],
  update:['M12 3a9 9 0 0 1 8.5 6','M20 4v5h-5','M12 21a9 9 0 0 1-8.5-6','M4 20v-5h5'],
  battery:['M3 7h16v10H3z','M21 10v4'],
  charging:['M13 2L7 13h5l-1 9 6-12h-5z'],
  'battery-low':['M3 7h16v10H3z','M21 10v4','M6 10v4'],
  sunrise:['M4 18h16','M6 14a6 6 0 0 1 12 0','M12 3v3','M4.9 6.9L7 9','M19.1 6.9L17 9'],
  sun:['M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8','M12 2v2','M12 20v2','M4.9 4.9l1.4 1.4','M17.7 17.7l1.4 1.4','M2 12h2','M20 12h2','M4.9 19.1l1.4-1.4','M17.7 6.3l1.4-1.4'],
  sunset:['M4 18h16','M6 14a6 6 0 0 1 12 0','M12 3v3','M4.9 6.9L7 9','M19.1 6.9L17 9','M9 21h6'],
  moon:['M20 15.5A8 8 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5'],
  star:['M12 3l2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z'],
  paint:['M4 15l8-8 5 5-8 8H4z','M13 6l2-2 5 5-2 2','M4 20h5'],
  puzzle:['M4 5h6a2 2 0 1 1 4 0h6v6a2 2 0 1 0 0 4v5h-6a2 2 0 1 0-4 0H4v-5a2 2 0 1 0 0-4z'],
  media:['M9 18V6l10-2v12','M9 10l10-2','M5 21a4 3 0 1 0 0-6 4 3 0 0 0 0 6','M15 19a4 3 0 1 0 0-6 4 3 0 0 0 0 6'],
  video:['M3 5h14v14H3z','M17 10l4-3v10l-4-3z'],
  play:['M8 5l11 7-11 7z'],
  globe:['M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0','M3 12h18','M12 3c3 3 3 15 0 18','M12 3c-3 3-3 15 0 18'],
  sparkles:['M12 3l1.4 4.6L18 9l-4.6 1.4L12 15l-1.4-4.6L6 9l4.6-1.4z','M19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7z','M5 3l.7 2.3L8 6l-2.3.7L5 9l-.7-2.3L2 6l2.3-.7z']
});

const LOCAL_TILE_ICON_NAMES=new Set(['paint','puzzle','media','globe','sparkles']);
const LEGACY_TILE_ICONS=Object.freeze({
  '🎨':'paint',
  '🧩':'puzzle',
  '🎵':'media',
  '🌐':'globe',
  '✨':'sparkles'
});

function createLocalIcon(name,className='ui-icon'){
  const paths=LOCAL_ICON_PATHS[name];
  if(!paths) return null;
  const svg=document.createElementNS(SVG_NAMESPACE,'svg');
  svg.setAttribute('viewBox','0 0 24 24');
  svg.setAttribute('fill','none');
  svg.setAttribute('stroke','currentColor');
  svg.setAttribute('stroke-width','2');
  svg.setAttribute('stroke-linecap','round');
  svg.setAttribute('stroke-linejoin','round');
  svg.setAttribute('aria-hidden','true');
  svg.setAttribute('focusable','false');
  svg.classList.add('ui-icon');
  svg.classList.add(...String(className||'ui-icon').split(/\s+/).filter(Boolean));
  for(const data of paths){
    const path=document.createElementNS(SVG_NAMESPACE,'path');
    path.setAttribute('d',data);
    svg.appendChild(path);
  }
  return svg;
}

function setIconLabel(element,name,label){
  if(!element) return;
  const icon=createLocalIcon(name);
  const text=document.createElement('span');
  text.className='icon-label';
  text.textContent=label;
  element.replaceChildren(...(icon?[icon,text]:[text]));
  if(element.tagName==='BUTTON') element.setAttribute('aria-label',label);
}

function setIconOnly(element,name,label){
  if(!element) return;
  const icon=createLocalIcon(name);
  element.replaceChildren(...(icon?[icon]:[]));
  element.setAttribute('aria-label',label);
  element.title=label;
}

function localTileIconName(value){
  const normalized=String(value||'');
  if(normalized.startsWith('icon:')){
    const name=normalized.slice(5);
    return LOCAL_TILE_ICON_NAMES.has(name)?name:'';
  }
  return LEGACY_TILE_ICONS[normalized]||'';
}

function createTileVisual(value,className='emoji'){
  const iconName=localTileIconName(value||'✨');
  if(iconName){
    return createLocalIcon(iconName,className+' local-tile-icon');
  }
  const emoji=document.createElement('span');
  emoji.className=className;
  emoji.textContent=value||'✨';
  return emoji;
}

function renderTileVisual(container,value,className='emoji'){
  if(!container) return;
  container.replaceChildren(createTileVisual(value,className));
}

function hydrateLocalIcons(root=document){
  root.querySelectorAll('[data-local-icon]').forEach(element=>{
    if(element.dataset.localIconReady==='true') return;
    const name=element.dataset.localIcon;
    const label=element.getAttribute('aria-label')||element.textContent.trim();
    if(element.hasAttribute('data-icon-only')) setIconOnly(element,name,label);
    else setIconLabel(element,name,label);
    element.dataset.localIconReady='true';
  });
}

hydrateLocalIcons();
