"""Catalog discovery checks; no real packages or family settings are changed."""

import json


def run_catalog_discovery_scenarios(browser, artifacts):
    def check(expression, message):
        if browser.evaluate(expression) is not True:
            raise AssertionError(message)

    browser.evaluate("""
        window.__discoveryConfig=JSON.parse(JSON.stringify(cfg));
        window.__discoveryRecommendations=recommendations;
        window.__discoveryFetch=window.fetch;
        cfg.tiles=[{id:'discovery-existing',label:'Existing',emoji:'🎨',cmd:['true'],visible:false}];
        recommendations=[
            {id:'discovery-paint',name_en:'Tiny Paint',name_de:'Kleines Malen',desc_en:'Drawing pictures',desc_de:'Bilder zeichnen',
             category:'creative',installed:true,cmd:['true'],guidance:{offline:'yes',input:['mouse'],age_en:'3–12',age_de:'3–12',license:'GPL',source:'https://tuxpaint.org/'}},
            {id:'discovery-learn',name_en:'Learning Fixture',name_de:'Lern-Beispiel',category:'learning',installed:false,package:'fixture',cmd:['missing-fixture']},
            {id:'discovery-web',name_en:'Web Fixture',name_de:'Web-Beispiel',category:'browser',installed:true,cmd:['special:external-browser:https://example.com']}
        ];
        catalogQuery=''; catalogCategory='all'; catalogStatus='all';
        enterAdmin(); activateAdminSection('apps');
    """)
    try:
        browser.set_value('#catalogSearch', 'drawing')
        check("document.querySelectorAll('#catalogResults .rec-card').length===1", 'Localized description search did not filter the catalog')
        browser.evaluate("document.querySelector('[data-catalog-id=\"discovery-paint\"] summary').focus()")
        browser.key_press('Enter')
        check("document.querySelector('[data-catalog-id=\"discovery-paint\"] details').open && document.getElementById('catalogResults').textContent.includes('3–12')", 'Keyboard details did not expose app guidance')
        browser.key_press('Enter')
        browser.set_value('#catalogSearch', '')
        browser.evaluate("document.getElementById('catalogStatus').value='added'; document.getElementById('catalogStatus').dispatchEvent(new Event('change'))")
        check("document.querySelectorAll('#catalogResults .rec-card').length===1 && document.querySelector('[data-catalog-id=\"discovery-paint\"] .actions button').disabled", 'A hidden existing tile was offered as a duplicate')
        browser.evaluate("document.getElementById('catalogStatus').value='missing'; document.getElementById('catalogStatus').dispatchEvent(new Event('change')); document.getElementById('catalogCategory').value='creative'; document.getElementById('catalogCategory').dispatchEvent(new Event('change'))")
        check("document.querySelectorAll('#catalogResults .rec-card').length===0 && document.getElementById('catalogResults').textContent.includes(uiText.catalogNoMatches)", 'Combined filters did not show a clear empty state')
        browser.evaluate("catalogCategory='learning'; catalogStatus='all'; renderRecommendations()")
        browser.click('[data-catalog-id="discovery-learn"] summary')
        check("document.querySelector('[data-catalog-id=\"discovery-learn\"] details').textContent.includes(uiText.catalogUnknown)", 'Unreviewed app details implied verified metadata')

        # Exercise a real card's save action with a rejected local fixture reply.
        browser.evaluate("""
            catalogCategory='browser'; renderRecommendations();
            window.fetch=(input,options)=>String(input)==='/api/save-config'?
                Promise.resolve(new Response('{}',{status:403})):window.__discoveryFetch(input,options);
        """)
        browser.click('[data-catalog-id="discovery-web"] .actions button')
        browser.wait_for("document.querySelector('[data-catalog-id=\"discovery-web\"] [role=alert]')!==null")
        check("cfg.tiles.length===1 && !cfg.tiles.some(tile=>tile.id==='discovery-web')", 'A rejected tile save left a phantom tile')
        browser.evaluate("window.fetch=window.__discoveryFetch; catalogCategory='all'; catalogStatus='all'; renderRecommendations()")
        for language in ('de', 'en'):
            browser.evaluate(f"loadInterfaceLanguage({json.dumps(language)})", await_promise=True)
            browser.evaluate(f"cfg.language={json.dumps(language)}; renderRecommendations()")
            browser.set_device_metrics(800, 600)
            check("""
                document.getElementById('recommendations').scrollWidth<=document.getElementById('recommendations').clientWidth+1 &&
                Array.from(document.querySelectorAll('#recommendations button,#recommendations summary,#recommendations input,#recommendations select'))
                    .filter(item=>item.getClientRects().length).every(item=>item.getBoundingClientRect().height>=44) &&
                document.getElementById('catalogInstallStatus').textContent.includes(uiText.packageStatus)
            """, f'{language} app store clips controls or loses install-status access at 800x600')
            browser.screenshot(artifacts / f'catalog-discovery-{language}.png')
    finally:
        browser.evaluate("loadInterfaceLanguage(window.__discoveryConfig.language)", await_promise=True)
        browser.evaluate("""
            window.fetch=window.__discoveryFetch; cfg=window.__discoveryConfig;
            recommendations=window.__discoveryRecommendations;
            catalogQuery=''; catalogCategory='all'; catalogStatus='all'; renderAll();
            delete window.__discoveryFetch; delete window.__discoveryConfig; delete window.__discoveryRecommendations;
        """)
        browser.set_device_metrics(1440, 900)
    print('  ✓ app store search, combined filters, details, duplicate prevention, rollback and bilingual controls', flush=True)
