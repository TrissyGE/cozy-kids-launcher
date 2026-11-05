"""Focused Parent Flatpak journeys; package changes are local HTTP fixtures."""

import json


def run_flatpak_scenarios(browser, artifacts):
    def check(expression, message):
        if browser.evaluate(expression) is not True:
            raise AssertionError(message)
    browser.wait_for("typeof cfg==='object' && recommendations.some(rec=>rec.id==='tuxpaint') && !!uiText.flatpakSource")
    browser.evaluate("""(async()=>{
      window.__flatCfg=JSON.parse(JSON.stringify(cfg));
      window.__flatRecs=recommendations;
      window.__flatFetch=window.fetch.bind(window);
      window.__flatCalls=[]; window.__flatInstalls=0; window.__flatSaveFail=false;
      window.__flatCmd=['flatpak','run','--user','--arch=x86_64','--branch=stable','org.tuxpaint.Tuxpaint','--fullscreen=yes'];
      window.__flatRec={...recommendations.find(rec=>rec.id==='tuxpaint'),installed:false,
        cmd:['tuxpaint','--fullscreen=yes'],packageRoute:{mode:'direct',provider:'apt',operations:['install','update','remove']},
        flatpakRoute:{mode:'direct',provider:'flatpak',operations:['install'],installed:false,cmd:window.__flatCmd}};
      recommendations=[window.__flatRec]; recommendationState='ready';
      cfg.tiles=cfg.tiles.filter(tile=>tile.id!=='tuxpaint');
      cfg.tiles.push({id:'tuxpaint',label:'My Paint',emoji:'🎨',cmd:['tuxpaint','--fullscreen=yes'],visible:false});
      window.__flatJob={status:'ready',jobId:'flat-fixture',appId:'tuxpaint',source:'flatpak',provider:'flatpak',
        operation:'install',confirmationToken:'flat-consent',packages:['app/org.tuxpaint.Tuxpaint/x86_64/stable',
          'runtime/org.freedesktop.Platform/x86_64/25.08'],downloadBytes:10485760,
        flatpak:{scope:'user',remote:'flathub',url:'https://dl.flathub.org/repo/',permissions:[
          'Context.sockets=wayland','Context.sockets=pulseaudio','Context.devices=dri',
          'Context.filesystems=xdg-pictures/TuxPaint:create','Context.shared=ipc','Context.persistent=.tuxpaint']}};
      window.fetch=(input,options)=>{
        const path=String(input);
        if(path==='/api/packages/prepare'){
          window.__flatCalls.push(JSON.parse(options.body));
          return Promise.resolve(new Response(JSON.stringify(window.__flatJob)));
        }
        if(path==='/api/packages/status') return Promise.resolve(new Response(JSON.stringify(window.__flatJob)));
        if(path==='/api/packages/install'){
          window.__flatInstalls++;
          window.__flatConfirm=JSON.parse(options.body);
          window.__flatJob={...window.__flatJob,status:'installing',phase:'installing',percent:20};
          return Promise.resolve(new Response(JSON.stringify(window.__flatJob)));
        }
        if(path==='/api/recommendations'){
          window.__flatRec.flatpakRoute.installed=window.__flatJob.status==='complete';
          return Promise.resolve(new Response(JSON.stringify([window.__flatRec])));
        }
        if(path==='/api/save-config'&&window.__flatSaveFail) return Promise.resolve(new Response('{}',{status:500}));
        return window.__flatFetch(input,options);
      };
      enterAdmin(); activateAdminSection('apps'); catalogQuery=''; catalogStatus='all'; catalogCategory='all';
      catalogSources.set('tuxpaint','native'); renderRecommendations();
    })()""", await_promise=True)
    try:
        check("document.querySelector('[data-catalog-source=tuxpaint]').value==='native'", 'Native source changed without Parent choice')
        browser.evaluate("""(()=>{const select=document.querySelector('[data-catalog-source=tuxpaint]');
          select.value='flatpak'; select.dispatchEvent(new Event('change',{bubbles:true}));})()""")
        browser.click('[data-catalog-id=tuxpaint] .actions button')
        browser.wait_for("packageIsOpen() && packageJob.status==='ready'")
        check("JSON.stringify(window.__flatCalls[0])===JSON.stringify({appId:'tuxpaint',source:'flatpak'}) && window.__flatInstalls===0",
              'Review selected another source or installed before confirmation')
        check("document.getElementById('packageHint').textContent===uiText.flatpakConsent && !document.getElementById('packageFlatpakPermissions').hidden && document.getElementById('packageFlatpakPermissions').textContent.includes(uiText.flatpakAudio)",
              'Review omitted explicit Flatpak scope or microphone access')
        browser.set_device_metrics(800,600)
        for language in ('de','en','es','fr','it'):
            browser.evaluate(f"(async()=>{{cfg.language={json.dumps(language)};await loadInterfaceLanguage(cfg.language);renderLocalizedChrome();renderPackageJob();}})()",await_promise=True)
            check("document.getElementById('packageHint').textContent===uiText.flatpakConsent && document.querySelector('.package-box').scrollWidth<=document.querySelector('.package-box').clientWidth+1",
                  f'Flatpak review clipped or lost localization in {language}')
            browser.screenshot(artifacts/f'flatpak-review-{language}-800x600.png')
        browser.click('#packageAction')
        browser.wait_for("packageJob.status==='installing'")
        check("window.__flatInstalls===1 && JSON.stringify(window.__flatConfirm)===JSON.stringify({jobId:'flat-fixture',confirmationToken:'flat-consent'})",
              'Install submitted extra source/ref/permission arguments or repeated consent')
        browser.evaluate("""(async()=>{window.__flatJob.status='complete'; await refreshPackageStatus();})()""",await_promise=True)
        check("cfg.tiles.find(tile=>tile.id==='tuxpaint').cmd[0]==='tuxpaint' && document.getElementById('packageAction').textContent===uiText.catalogUseSource",
              'Installation silently rewrote the existing tile')
        browser.evaluate('window.__flatSaveFail=true')
        browser.click('#packageAction')
        browser.wait_for("!document.getElementById('packageAction').disabled")
        check("cfg.tiles.find(tile=>tile.id==='tuxpaint').cmd[0]==='tuxpaint'", 'Failed source save did not restore the existing command')
        browser.evaluate('window.__flatSaveFail=false')
        browser.click('#packageAction')
        browser.wait_for("cfg.tiles.find(tile=>tile.id==='tuxpaint').cmd[0]==='flatpak'")
        check("cfg.tiles.filter(tile=>tile.id==='tuxpaint').length===1 && cfg.tiles.find(tile=>tile.id==='tuxpaint').label==='My Paint' && cfg.tiles.find(tile=>tile.id==='tuxpaint').visible===false",
              'Source change duplicated the tile or changed family labels/visibility')
        browser.click('#packageClose')
        browser.evaluate("""window.__flatRec.flatpakRoute={mode:'unavailable',provider:'flatpak',reason:'flatpak_origin'};
          recommendations=[window.__flatRec]; renderCatalogResults();""")
        check("document.querySelector('[data-catalog-id=tuxpaint] .actions button').disabled && document.querySelector('[data-catalog-id=tuxpaint]').textContent.includes(uiText.flatpakOrigin)",
              'Unavailable Flatpak route fell back silently or hid the source error')
        browser.screenshot(artifacts/'flatpak-source-unavailable.png')
        print('  ✓ Flatpak source choice, exact consent, five-language permission review, tile-source rollback and explicit migration',flush=True)
    finally:
        browser.evaluate("""(async()=>{
          closePackageOverlay(); window.fetch=window.__flatFetch;
          cfg=window.__flatCfg; recommendations=window.__flatRecs; catalogSources.delete('tuxpaint');
          await loadInterfaceLanguage(cfg.language); await persistConfig(); renderAll();
        })()""",await_promise=True)
    injected=browser.devtools.call('Page.addScriptToEvaluateOnNewDocument',{'source':"""
      const originalFetch=window.fetch.bind(window);
      window.fetch=(input,options)=>String(input).startsWith('/frontend/locales/')?
        Promise.reject(new TypeError('fixture locale unavailable')):originalFetch(input,options);
    """})
    try:
        browser.devtools.call('Page.reload',{})
        browser.wait_for("typeof cfg==='object' && cfg?.setupCompleted===true && typeof uiText.flatpakConsent==='string'")
        check("typeof uiText.flatpakSource==='string' && typeof uiText.packageSource==='string' && typeof uiText.catalogUseSource==='string'",
              'Missing locale files lost the installer-rendered Flatpak fallback')
    finally:
        browser.devtools.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':injected['identifier']})
