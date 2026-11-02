"""Real DOM checks with fixture-only package mutations; never install on a CI host."""

import json


def run_catalog_install_scenarios(browser, artifacts):
    def check(expression, message):
        if browser.evaluate(expression) is not True:
            raise AssertionError(message)

    browser.evaluate("""(async()=>{
        window.__pkgClientConfig=JSON.parse(JSON.stringify(cfg));
        const stored=await fetch('/api/config');
        if(!stored.ok) throw new Error('Could not snapshot catalog fixture configuration');
        window.__pkgStoredConfig=await stored.json();
        window.__pkgFetch=window.fetch.bind(window); window.__pkgInstallCalls=0;
        window.__pkgRec={id:'e2e-catalog',package:'fixture',name_en:'Creative App',name_de:'Kreativ-App',
            label_en:'Creative App',label_de:'Kreativ-App',emoji:'🎨',cmd:['true','cozy-catalog-fixture'],installed:false};
        window.__pkgRecommendations=[...recommendations,window.__pkgRec]; recommendations=window.__pkgRecommendations;
        window.__pkgReady={status:'ready',jobId:'fixture-job',appId:'e2e-catalog',confirmationToken:'fixture-consent',
            packages:['fixture','<img src=x onerror=alert(1)>'],downloadBytes:10485760};
        window.__pkgState={status:'checking',appId:'e2e-catalog',jobId:'fixture-job',percent:null};
        window.__pkgMode='ok';
        window.fetch=(input,options)=>{
            const path=String(input);
            if(path==='/api/packages/prepare'){
                if(window.__pkgMode==='deferred') return new Promise(resolve=>{window.__pkgResolve=resolve;});
                return Promise.resolve(new Response(JSON.stringify(window.__pkgState)));
            }
            if(path==='/api/packages/status'){
                if(window.__pkgMode==='unauthorized') return Promise.resolve(new Response('{}',{status:403}));
                return Promise.resolve(new Response(JSON.stringify(window.__pkgState)));
            }
            if(path==='/api/packages/install'){
                window.__pkgInstallCalls++; window.__pkgInstallBody=JSON.parse(options.body);
                window.__pkgState={status:'installing',phase:'authorization',appId:'e2e-catalog',jobId:'fixture-job',percent:null};
                if(window.__pkgMode==='lost-reply') return Promise.reject(new TypeError('synthetic lost reply'));
                return Promise.resolve(new Response(JSON.stringify(window.__pkgState)));
            }
            if(path==='/api/recommendations'){
                window.__pkgRec.installed=window.__pkgState.status==='complete';
                return Promise.resolve(new Response(JSON.stringify(window.__pkgRecommendations)));
            }
            return window.__pkgFetch(input,options);
        };
        enterAdmin(); activateAdminSection('apps');
    })()""", await_promise=True)
    try:
        browser.evaluate("triggerInstall(window.__pkgRec)", await_promise=True)
        check("packageIsOpen() && document.getElementById('packageAction').hidden && window.__pkgInstallCalls===0",
              'A checking plan installed or offered confirmation prematurely')
        browser.evaluate("window.__pkgState=window.__pkgReady; refreshPackageStatus()", await_promise=True)
        check("""
            document.getElementById('installOverlay').classList.contains('hidden') &&
            document.getElementById('packageAction').textContent===uiText.packageConfirm &&
            document.querySelector('#packageList img')===null &&
            document.getElementById('packageList').textContent.includes('<img') &&
            document.getElementById('packageSummary').textContent.includes('10 MB')
        """, 'The review exposed terminal instructions, unsafe HTML, or an incorrect download size')
        browser.key_press('Escape')
        check("!packageIsOpen() && window.__pkgInstallCalls===0", 'Closing review started an installation')
        browser.evaluate("triggerInstall(window.__pkgRec)", await_promise=True)
        browser.evaluate("window.__pkgMode='lost-reply'")
        browser.click('#packageAction')
        browser.click('#packageAction')
        browser.wait_for("packageJob.status==='installing' && packageJob.phase==='authorization'")
        check("""
            window.__pkgInstallCalls===1 &&
            JSON.stringify(window.__pkgInstallBody)===JSON.stringify({jobId:'fixture-job',confirmationToken:'fixture-consent'}) &&
            !document.getElementById('packageProgress').hasAttribute('value') &&
            document.getElementById('packageMessage').textContent.includes(uiText.packageAuth)
        """, 'Double click/lost acknowledgement repeated consent or fabricated progress')
        browser.click('#packageClose')
        browser.evaluate("window.__pkgMode='ok'; window.__pkgState.phase='downloading'; window.__pkgState.percent=42; openPackageStatus()", await_promise=True)
        check("document.getElementById('packageProgress').value===42 && window.__pkgInstallCalls===1", 'Reopening failed to reconnect to progress')
        browser.screenshot(artifacts / 'catalog-install-progress.png')
        browser.evaluate("window.__pkgState={status:'complete',appId:'e2e-catalog',jobId:'fixture-job',percent:100}; refreshPackageStatus()", await_promise=True)
        check("document.getElementById('packageAction').textContent===uiText.packageAdd", 'Finished install did not offer adding a tile')
        browser.click('#packageAction')
        browser.wait_for("cfg.tiles.some(tile=>tile.id==='e2e-catalog') && document.getElementById('packageAction').hidden")
        saved = browser.evaluate("fetch('/api/config').then(r=>r.json())", await_promise=True)
        if not any(tile['id'] == 'e2e-catalog' for tile in saved['tiles']):
            raise AssertionError('The installed app tile was not persisted')
        for code, label in (('network', 'packageNetwork'), ('authorization', 'packageAuthorization'),
                            ('busy', 'packageBusy'), ('unsupported', 'packageUnsupported'),
                            ('changes_required', 'packageChanges'), ('plan_changed', 'packageChanged'),
                            ('interrupted', 'packageInterrupted')):
            browser.evaluate(f"window.__pkgState={{status:'error',appId:'e2e-catalog',error:{json.dumps(code)}}}; refreshPackageStatus()", await_promise=True)
            check(f"document.getElementById('packageMessage').textContent.includes(uiText.{label}) && document.getElementById('packageAction').hidden",
                  f'Package error {code} lacked a safe recovery state')
        browser.evaluate("window.__pkgMode='unauthorized'; refreshPackageStatus()", await_promise=True)
        check("document.getElementById('packageMessage').textContent.includes(uiText.packageAuthorization) && window.__pkgInstallCalls===1", 'An expired Parent session repeated installation')
        browser.evaluate("window.__pkgMode='ok'; window.__pkgState=window.__pkgReady")
        for language in ('de', 'en'):
            browser.evaluate(f"loadInterfaceLanguage({json.dumps(language)})", await_promise=True)
            browser.evaluate(f"cfg.language={json.dumps(language)}; renderLocalizedChrome(); closePackageOverlay(); openPackageStatus()", await_promise=True)
            browser.set_device_metrics(800, 600)
            check("""
                document.getElementById('packageOverlay').getBoundingClientRect().width<=800 &&
                document.querySelector('.package-box').getBoundingClientRect().top>=0 &&
                document.getElementById('packageClose').getBoundingClientRect().bottom<=600 &&
                document.getElementById('packageHint').textContent===uiText.packageConsent &&
                document.querySelector('.package-box').scrollWidth<=document.querySelector('.package-box').clientWidth+1
            """, f'{language} package review clipped at 800x600')
            browser.screenshot(artifacts / f'catalog-install-review-{language}.png')
        browser.set_device_metrics(1440, 900)
        browser.evaluate("window.__pkgMode='deferred'; void triggerInstall(window.__pkgRec)")
        browser.click('#packageClose')
        browser.evaluate("window.__pkgResolve(new Response(JSON.stringify(window.__pkgReady)))")
        browser.evaluate("new Promise(resolve=>setTimeout(resolve,100))", await_promise=True)
        check("!packageIsOpen() && window.__pkgInstallCalls===1", 'A late preparation reopened the dialog or installed')
    finally:
        # Adding a tile deliberately exercises the real config endpoint. Restore
        # both server and client fixtures: earlier journeys can have unsaved UI
        # state that must not replace the server's media tile for the next check.
        browser.evaluate("""(async()=>{
            closePackageOverlay(); window.fetch=window.__pkgFetch;
            cfg=window.__pkgStoredConfig; await persistConfig();
            cfg=window.__pkgClientConfig; renderAll();
        })()""", await_promise=True)
    print('  ✓ terminal-free review, consent, progress, errors, reconnect, and adding a tile', flush=True)
