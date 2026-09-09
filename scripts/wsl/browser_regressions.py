"""Focused real-browser regression checks; all mutation endpoints are fixtures."""

import json
import time
from browser_package_install import run_catalog_install_scenarios


def wait_for_values(browser, expression, expected, message, timeout=5):
    """Wait for actual UI convergence and report each value, without rerunning a journey."""
    deadline = time.monotonic() + timeout
    actual = None
    while time.monotonic() < deadline:
        actual = browser.evaluate(expression)
        if actual == expected:
            return
        time.sleep(0.1)
    raise AssertionError(f"{message}: expected {expected!r}; last observed {actual!r}")


def assert_js(browser, expression, message):
    if browser.evaluate(expression) is not True:
        raise AssertionError(message)


def run_regression_scenarios(browser, artifacts, base_url):
    browser.wait_for("typeof cfg!=='undefined' && cfg!==null && bootstrapPromise===null")
    browser.evaluate("""
        window.__regressionOriginalConfig=JSON.parse(JSON.stringify(cfg));
        cfg.theme='custom'; cfg.accessibilityHighContrast=false;
        cfg.customColors={bg1:'#123456',text:'#abcdef',btnText:'#fedcba'};
        cfg.customBackground='/themes/ocean.jpg'; renderAll();
    """)
    assert_js(browser, """
        document.body.style.getPropertyValue('--text')==='#abcdef' &&
        document.body.style.getPropertyValue('--btn-text')==='#fedcba' &&
        document.getElementById('themeBg').style.opacity==='1'
    """, "The custom palette/background was not applied")
    browser.evaluate("cfg.customColors={text:'#112233'}; cfg.customBackground=''; renderAll()")
    assert_js(browser, """
        document.body.style.getPropertyValue('--text')==='#112233' &&
        document.body.style.getPropertyValue('--btn-text')==='' &&
        document.body.style.getPropertyValue('--bg1')==='' &&
        document.getElementById('themeBg').style.backgroundImage===''
    """, "A partial custom profile inherited the previous profile's palette")
    browser.evaluate("cfg.theme='weltraum'; renderAll()")
    assert_js(browser, """
        Object.values(COZY_CUSTOM_THEME_TOKENS).every(token=>!document.body.style.getPropertyValue(token)) &&
        document.getElementById('themeBg').style.opacity==='' &&
        document.body.classList.contains('theme-weltraum')
    """, "Switching back to a built-in theme retained custom CSS overrides")
    browser.evaluate("""
        cfg.theme='custom'; cfg.customColors={text:'#abcdef',bg1:'#123456'};
        cfg.customBackground='/themes/ocean.jpg'; cfg.accessibilityHighContrast=true; renderAll();
        enterAdmin(); activateAdminSection('appearance');
    """)
    assert_js(browser, """
        getComputedStyle(document.body).getPropertyValue('--text').trim()==='#111' &&
        getComputedStyle(document.getElementById('themeBg')).display==='none' &&
        document.getElementById('appearancePreview').classList.contains('access-high-contrast') &&
        getComputedStyle(document.getElementById('appearancePreview')).getPropertyValue('--text').trim()==='#111'
    """, "Custom colors override high contrast in the launcher or Parent preview")
    browser.screenshot(artifacts / 'custom-high-contrast.png')
    print('  ✓ custom palettes reset across profiles/themes and respect high contrast', flush=True)

    browser.evaluate("""
        cfg=window.__regressionOriginalConfig; renderAll(); enterAdmin(); activateAdminSection('system');
        window.__fixtureOriginalFetch=window.fetch.bind(window);
        window.__fixtureMode='rejected'; window.__fixtureRequests=[];
        window.__fixtureReply=()=>{
            if(window.__fixtureMode==='network') return Promise.reject(new TypeError('synthetic offline'));
            if(window.__fixtureMode==='rejected') return Promise.resolve(new Response('{}',{status:403}));
            if(window.__fixtureMode==='unavailable') return Promise.resolve(new Response('{}',{status:503}));
            if(window.__fixtureMode==='malformed') return Promise.resolve(new Response('not JSON'));
            if(window.__fixtureMode==='unacknowledged') return Promise.resolve(new Response('{}'));
            if(window.__fixtureMode==='unsupported') return Promise.resolve(new Response('{"status":"unsupported"}'));
            return Promise.resolve(new Response(JSON.stringify(window.__fixtureSuccess)));
        };
        window.fetch=(input,options)=>{
            if(['/api/update','/api/install-package','/exit-kids'].includes(String(input))){
                window.__fixtureRequests.push(String(input));
                if(window.__fixtureMode==='pending') return new Promise(resolve=>{window.__fixtureResolve=resolve;});
                return window.__fixtureReply();
            }
            return window.__fixtureOriginalFetch(input,options);
        };
    """)
    try:
        for mode in ('rejected', 'unavailable', 'network', 'malformed', 'unacknowledged'):
            browser.evaluate(f"window.__fixtureMode={json.dumps(mode)}; void installUpdate()")
            browser.wait_for("confirmationIsOpen()")
            browser.click('#confirmActionBtn')
            browser.wait_for("!updateTriggerPending")
            assert_js(browser, """
                document.getElementById('updating').classList.contains('hidden') &&
                document.getElementById('updateMsg').textContent.includes(uiText.updateStartError) &&
                document.querySelector('#updateMsg button')!==null &&
                !document.getElementById('updateNowBtn').disabled
            """, f"An unsuccessful update ({mode}) was presented as started")
        browser.screenshot(artifacts / 'update-start-error.png')
        browser.evaluate("window.__fixtureRequests=[]; void installUpdate()")
        browser.click('#confirmCancelBtn')
        browser.wait_for("!updateTriggerPending")
        assert_js(browser, "window.__fixtureRequests.length===0", "Cancel still requested an update")
        browser.evaluate("""
            window.__fixtureMode='pending'; window.__fixtureSuccess={status:'triggered'};
            void installUpdate();
        """)
        browser.click('#confirmActionBtn')
        browser.wait_for("typeof window.__fixtureResolve==='function'")
        browser.evaluate("void installUpdate()")
        assert_js(browser, """
            window.__fixtureRequests.length===1 && document.getElementById('updateNowBtn').disabled &&
            document.getElementById('updating').classList.contains('hidden')
        """, "Duplicate update or success overlay before the server acknowledgement")
        browser.evaluate("window.__fixtureResolve(new Response(JSON.stringify(window.__fixtureSuccess)))")
        browser.wait_for("!updateTriggerPending && !document.getElementById('updating').classList.contains('hidden')")
        # Catch the old, unconditional delayed /exit-kids request as well.
        browser.evaluate("new Promise(resolve=>setTimeout(resolve,3200))", await_promise=True)
        assert_js(browser, "!window.__fixtureRequests.includes('/exit-kids')", "Update UI issued a redundant exit")
        browser.evaluate("document.getElementById('updating').classList.add('hidden')")
        print('  ✓ update errors, cancellation, duplicate requests, and acknowledgement are handled safely', flush=True)

        browser.evaluate("""
            window.__fixtureRec={id:'tuxpaint',package:'tuxpaint',name_en:'Tux Paint',name_de:'Tux Paint'};
            window.__fixtureSuccess={status:'manual',provider:'dnf',command:'sudo dnf install tuxpaint'};
            window.__fixtureMode='success';
        """)
        browser.evaluate("showManualInstall(window.__fixtureRec)", await_promise=True)
        assert_js(browser, """
            document.getElementById('installCommand').textContent==='sudo dnf install tuxpaint' &&
            !document.getElementById('installCopyBtn').disabled &&
            document.getElementById('installMessage').textContent===uiText.installManual &&
            document.getElementById('installMessage').getBoundingClientRect().height>0
        """, "Install instructions did not use the acknowledged native-provider plan")
        browser.screenshot(artifacts / 'native-install-instructions.png')
        for mode in ('rejected', 'unavailable', 'network', 'malformed', 'unacknowledged', 'unsupported'):
            browser.evaluate(f"window.__fixtureMode={json.dumps(mode)}; showManualInstall(window.__fixtureRec)", await_promise=True)
            expected = 'installUnsupported' if mode == 'unsupported' else 'installError'
            assert_js(browser, f"""
                document.getElementById('installCommand').textContent==='' &&
                document.getElementById('installCopyBtn').disabled &&
                document.querySelector('#installOverlay .command-box').classList.contains('hidden') &&
                document.getElementById('installMessage').textContent.includes(uiText.{expected})
            """, f"Install failure ({mode}) exposed a guessed or stale command")
        browser.evaluate("window.__fixtureMode='pending'; void showManualInstall(window.__fixtureRec)")
        assert_js(browser, """
            document.getElementById('installMessage').textContent.includes(uiText.installLoading) &&
            document.getElementById('installCopyBtn').disabled
        """, "Loading instructions exposed an old command")
        browser.click('#installCloseBtn')
        browser.evaluate("window.__fixtureResolve(new Response(JSON.stringify(window.__fixtureSuccess)))")
        browser.evaluate("new Promise(resolve=>setTimeout(resolve,100))", await_promise=True)
        assert_js(browser, """
            document.getElementById('installOverlay').classList.contains('hidden') &&
            pendingInstallCommand==='' && document.getElementById('installCopyBtn').disabled
        """, "A late response repopulated a closed install dialog")
        browser.evaluate("window.__fixtureMode='network'; showManualInstall(window.__fixtureRec)", await_promise=True)
        browser.evaluate("window.__fixtureMode='success'")
        browser.click('#installMessage button')
        browser.wait_for("!document.getElementById('installCopyBtn').disabled")
        browser.click('#installCloseBtn')
        browser.evaluate("""
            window.__fixtureMode='pending'; void showManualInstall(window.__fixtureRec);
            window.__oldInstallResolve=window.__fixtureResolve;
            window.__fixtureMode='success';
        """)
        browser.evaluate("showManualInstall(window.__fixtureRec)", await_promise=True)
        browser.evaluate("window.__oldInstallResolve(new Response('{\"status\":\"manual\",\"command\":\"stale command\"}'))")
        browser.evaluate("new Promise(resolve=>setTimeout(resolve,100))", await_promise=True)
        assert_js(browser, "pendingInstallCommand==='sudo dnf install tuxpaint'", "An older request replaced newer instructions")
        for language in ('de', 'en'):
            browser.evaluate(f"loadInterfaceLanguage({json.dumps(language)})", await_promise=True)
            browser.evaluate(f"cfg.language={json.dumps(language)}; renderLocalizedChrome(); showManualInstall(window.__fixtureRec)", await_promise=True)
            browser.set_device_metrics(800, 600)
            assert_js(browser, """
                typeof uiText.installManual==='string' && uiText.installManual.length>80 &&
                ['installLoading','installError','installUnsupported','updateStartError'].every(key=>
                    typeof uiText[key]==='string' && uiText[key].length>10) &&
                document.getElementById('installMessage').getBoundingClientRect().height>0 &&
                document.querySelector('#installOverlay .install-box').getBoundingClientRect().top>=0 &&
                document.getElementById('installCloseBtn').getBoundingClientRect().bottom<=600 &&
                document.documentElement.scrollWidth<=800
            """, f"{language} installation guidance was missing or clipped at 800x600")
            browser.screenshot(artifacts / f'native-install-{language}-800x600.png')
        browser.set_device_metrics(1440, 900)
        browser.click('#installCloseBtn')
        print('  ✓ native instructions, unsupported/error/retry, and late install responses are honest', flush=True)
    finally:
        browser.evaluate("window.fetch=window.__fixtureOriginalFetch")

    run_catalog_install_scenarios(browser, artifacts)
    browser.devtools.call('Page.navigate', {'url': base_url + '/media.html?tile=music'})
    browser.wait_for("typeof mediaConfig!=='undefined' && mediaConfig!==null && document.querySelectorAll('#mediaGrid .media-card').length===2")
    browser.evaluate("""
        window.__mediaTheme={...mediaConfig,theme:'custom',accessibilityHighContrast:false,
            customColors:{text:'#abcdef'},customBackground:'/themes/ocean.jpg'};
        applyMediaTheme(window.__mediaTheme);
    """)
    assert_js(browser, "document.body.style.getPropertyValue('--text')==='#abcdef'", "Media custom theme was not applied")
    browser.evaluate("applyMediaTheme({...window.__mediaTheme,accessibilityHighContrast:true})")
    assert_js(browser, """
        getComputedStyle(document.body).getPropertyValue('--text').trim()==='#111' &&
        getComputedStyle(document.getElementById('themeBg')).display==='none'
    """, "Media custom colors override high contrast")
    assert_js(browser, """
        Array.from(document.querySelectorAll('.media-play-mark')).every(mark=>
            getComputedStyle(mark.querySelector('.ui-icon')).color===getComputedStyle(mark).color &&
            getComputedStyle(mark.querySelector('.ui-icon')).fill!==getComputedStyle(mark).backgroundColor)
    """, "A fallback cover made the play icon invisible against its background")
    browser.screenshot(artifacts / 'media-custom-high-contrast.png')
    browser.evaluate("applyMediaTheme({...mediaConfig,theme:'rosa',accessibilityHighContrast:false})")
    assert_js(browser, "document.body.style.getPropertyValue('--text')===''", "Media theme switch retained custom colors")
    assert_js(browser, """
        Array.from(document.querySelectorAll('.media-play-mark')).every(mark=>
            getComputedStyle(mark.querySelector('.ui-icon')).fill!==getComputedStyle(mark).backgroundColor)
    """, "The normal-theme play icon disappeared on a fallback cover")
    print('  ✓ media library shares the same custom-theme and accessibility rules', flush=True)
