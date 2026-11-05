"""Real Parent UI checks with a local benchmark job fixture, never a native core."""

import json
from pathlib import Path


def run_benchmark_scenarios(browser):
    browser.evaluate("enterAdmin(); activateAdminSection('retro')")
    browser.wait_for("ps1Runtime && retroBenchmarkState.status==='idle'")
    if browser.evaluate("document.getElementById('retroBenchmarkRun').disabled") is not True:
        raise AssertionError("An absent reviewed core left the benchmark action enabled")
    browser.evaluate("""
      window.__benchFetch=window.fetch;
      window.__benchState={status:'idle'}; window.__benchMode='normal'; window.__benchStarts=0; window.__benchCancels=[];
      window.__benchJob={status:'running',jobId:'aaaaaaaaaaaaaaaa',scopeKey:'bbbbbbbbbbbbbbbbbbbbbbbb',startedAt:'2026-11-05T10:00:00+00:00'};
      window.__benchResult={throughputFps:120.25,p95FrameMs:8.125,targetFps:60,status:'within-budget',coreVersion:'fixture'};
      window.fetch=(resource,options={})=>{
        const path=String(resource), body=options.body?JSON.parse(options.body):{};
        const reply=(data,status=200)=>Promise.resolve(new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}}));
        if(path==='/api/retro/benchmark'&&options.method==='POST'){
          __benchStarts++;
          if(body.system!=='ps1'||Object.keys(body).length!==1) throw new Error('Unexpected benchmark workload');
          if(__benchMode==='busy') return reply({status:'busy'},409);
          if(__benchMode==='pending') return new Promise(resolve=>{window.__benchResolve=resolve;});
          __benchState={...__benchJob};
          if(__benchMode==='lost') return Promise.reject(new Error('Synthetic lost acknowledgement'));
          return reply(__benchState,202);
        }
        if(path==='/api/retro/benchmark') return reply(__benchState);
        if(path==='/api/retro/benchmark/cancel'){
          __benchCancels.push(body.jobId);
          if(body.jobId===__benchState.jobId) __benchState={...__benchState,status:'canceled',error:'canceled'};
          return reply({...__benchJob,jobId:body.jobId,status:'canceled',error:'canceled'});
        }
        if(path==='/api/retro/benchmark/clear'){
          if(body.jobId!==__benchState.jobId) return reply({status:'stale'},409);
          __benchState={status:'idle'}; return reply(__benchState);
        }
        return __benchFetch(resource,options);
      };
      ps1Runtime.core=true; renderRetroBenchmark();
    """)
    browser.click("#retroBenchmarkRun")
    browser.wait_for("retroBenchmarkState.jobId==='aaaaaaaaaaaaaaaa' && !retroBenchmarkMutating")
    browser.click("#retroBenchmarkRun")
    if browser.evaluate("__benchStarts===1 && !document.getElementById('retroBenchmarkCancel').hidden && document.getElementById('retroBenchmarkRun').disabled") is not True:
        raise AssertionError("The active benchmark did not expose cancellation or prevent duplicate starts")
    browser.click("#retroBenchmarkCancel")
    browser.wait_for("retroBenchmarkState.status==='canceled' && !retroBenchmarkMutating")
    if browser.evaluate("document.getElementById('retroBenchmarkStatus').textContent===uiText.retroBenchmarkCanceled && __benchCancels.includes('aaaaaaaaaaaaaaaa')") is not True:
        raise AssertionError("Cancellation did not use the current job ID")
    browser.evaluate("__benchMode='busy'")
    browser.click("#retroBenchmarkRun")
    browser.wait_for("retroBenchmarkState.error==='busy' && !retroBenchmarkMutating")
    browser.evaluate("__benchMode='lost'")
    browser.click("#retroBenchmarkRun")
    browser.wait_for("retroBenchmarkState.unavailable===true && !retroBenchmarkMutating")
    previous_starts = browser.evaluate("__benchStarts")
    browser.click("#retroBenchmarkRun")
    browser.wait_for("retroBenchmarkState.status==='running' && !retroBenchmarkState.unavailable")
    if browser.evaluate("__benchStarts") != previous_starts:
        raise AssertionError("Recovering a lost acknowledgement started another benchmark")
    browser.evaluate("__benchState={...__benchJob,status:'complete',result:__benchResult}")
    browser.wait_for("retroBenchmarkState.status==='complete'")
    browser.evaluate("window.__benchDevice=retroDevice; retroDevice={systems:[{catalog:'retroarch',resultKey:'bbbbbbbbbbbbbbbbbbbbbbbb'}]}; renderRetroBenchmark()")
    if browser.evaluate("document.getElementById('retroBenchmarkResult').textContent.includes(uiText.retroBenchmarkScopeCurrent)") is not True:
        raise AssertionError("A matching result did not show its current scope")
    browser.evaluate("retroDevice.systems[0].resultKey='updated-device'; renderRetroBenchmark()")
    if browser.evaluate("document.getElementById('retroBenchmarkResult').textContent.includes(uiText.retroBenchmarkScopeStale)") is not True:
        raise AssertionError("A changed device did not mark the previous measurement stale")
    browser.evaluate("retroDevice=__benchDevice; renderRetroBenchmark()")
    if browser.evaluate("document.getElementById('retroBenchmarkResult').textContent.includes(uiText.retroBenchmarkPass) && !document.getElementById('retroBenchmarkClear').hidden") is not True:
        raise AssertionError("The qualified workload result or removal control was missing")
    browser.click("#retroBenchmarkClear")
    browser.wait_for("retroBenchmarkState.status==='idle' && !retroBenchmarkMutating")
    if browser.evaluate("document.getElementById('retroBenchmarkResult').children.length===0") is not True:
        raise AssertionError("The removed benchmark result stayed visible")
    browser.evaluate("__benchMode='pending'")
    browser.click("#retroBenchmarkRun")
    browser.wait_for("typeof __benchResolve==='function'")
    browser.evaluate("closeAdmin(); __benchResolve(new Response(JSON.stringify({...__benchJob,jobId:'cccccccccccccccc'}),{status:202}))")
    browser.wait_for("__benchCancels.includes('cccccccccccccccc')")
    if browser.evaluate("document.getElementById('admin').classList.contains('hidden') && retroBenchmarkState.status==='idle'") is not True:
        raise AssertionError("A late benchmark acknowledgement changed the closed Parent UI")
    browser.evaluate("__benchMode='normal'; __benchState={...__benchJob,status:'complete',result:__benchResult}; enterAdmin(); activateAdminSection('retro')")
    browser.wait_for("ps1Runtime && retroBenchmarkState.status==='complete'")
    browser.set_device_metrics(800, 600)
    for language in ("de", "en", "es", "fr", "it"):
        browser.evaluate(f"loadInterfaceLanguage({json.dumps(language)})", await_promise=True)
        browser.evaluate("renderAll()")
        if browser.evaluate("document.documentElement.scrollWidth<=innerWidth+2 && document.getElementById('retroBenchmarkTitle').textContent===uiText.retroBenchmarkTitle && document.getElementById('retroBenchmarkResult').textContent.includes(uiText.retroBenchmarkPass)") is not True:
            raise AssertionError("Localized benchmark controls overflowed or retained old result text")
    browser.evaluate("document.getElementById('retroBenchmarkTitle').scrollIntoView({block:'start'})")
    browser.screenshot(Path(browser.log_path).parent / "retro-benchmark-result.png")
    browser.set_device_metrics(1440, 900)
    browser.evaluate("__benchState={status:'idle'}; retroBenchmarkState={status:'idle'}; closeAdmin(); window.fetch=__benchFetch")
    browser.evaluate("loadInterfaceLanguage('en')", await_promise=True)
    browser.evaluate("renderAll()")
    print("  ✓ Parent benchmark handles cancellation, lost replies, scoped removal, late acknowledgements and five languages", flush=True)
