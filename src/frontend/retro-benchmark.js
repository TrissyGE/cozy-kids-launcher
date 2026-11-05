let retroBenchmarkState={status:'idle'}, retroBenchmarkGeneration=0, retroBenchmarkMutating=false;
const retroBenchmarkActive=state=>['running','canceling'].includes(state.status);

function benchmarkReply(data){
  if(!data||!['idle','running','canceling','complete','error','canceled'].includes(data.status)) throw new Error('Invalid benchmark status');
  if(data.status!=='idle'&&!/^[a-f0-9]{16}$/.test(data.jobId||'')) throw new Error('Invalid benchmark job');
  if(data.status==='complete'&&(!data.result||
    ![data.result.throughputFps,data.result.p95FrameMs,data.result.targetFps].every(value=>typeof value==='number'&&Number.isFinite(value)))){
    throw new Error('Invalid benchmark result');
  }
  return data;
}

function clearRetroBenchmarkView(){
  ++retroBenchmarkGeneration;
  const current=retroBenchmarkState;
  if(retroBenchmarkActive(current)&&current.jobId){
    void fetch('/api/retro/benchmark/cancel',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({jobId:current.jobId})}).catch(()=>{});
  }
  retroBenchmarkState={status:'idle'};
  retroBenchmarkMutating=false;
  renderRetroBenchmark();
}

function renderRetroBenchmark(){
  const state=retroBenchmarkState, active=retroBenchmarkActive(state);
  document.getElementById('retroBenchmarkTitle').textContent=uiText.retroBenchmarkTitle;
  document.getElementById('retroBenchmarkGuide').textContent=uiText.retroBenchmarkGuide;
  const run=document.getElementById('retroBenchmarkRun');
  run.textContent=state.unavailable?uiText.retry:uiText.retroBenchmarkStart;
  run.disabled=!retroSession||retroSession.signal.aborted||retroBenchmarkMutating||
    (!state.unavailable&&(active||!ps1Runtime?.core));
  const cancel=document.getElementById('retroBenchmarkCancel');
  cancel.textContent=uiText.retroBenchmarkCancel;
  cancel.hidden=!active;
  cancel.disabled=retroBenchmarkMutating||!state.jobId||state.status==='canceling';
  const clear=document.getElementById('retroBenchmarkClear');
  clear.textContent=uiText.retroBenchmarkClear;
  clear.hidden=active||!state.jobId;
  clear.disabled=retroBenchmarkMutating;
  const errors={unavailable:uiText.retroBenchmarkMissing,busy:uiText.retroBenchmarkBusy,
    canceled:uiText.retroBenchmarkCanceled,interrupted:uiText.retroBenchmarkInterrupted,
    timeout:uiText.retroBenchmarkTimeout,failed:uiText.retroBenchmarkFailed};
  document.getElementById('retroBenchmarkStatus').textContent=state.unavailable?uiText.retroBenchmarkFailed:
    active?uiText.retroBenchmarkRunning:state.status==='complete'?uiText.retroBenchmarkMeasured:
    errors[state.error]||(!ps1Runtime?.core?uiText.retroBenchmarkMissing:uiText.retroBenchmarkEmpty);
  const result=document.getElementById('retroBenchmarkResult');
  result.replaceChildren();
  if(state.status==='complete'){
    const data=state.result;
    const number=new Intl.NumberFormat(interfaceLanguage(),{maximumFractionDigits:2});
    const row=retroDevice?.systems.find(item=>item.catalog==='retroarch');
    const scope=document.createElement('p');
    scope.textContent=!row?uiText.retroBenchmarkScopeUnknown:
      row.resultKey===state.scopeKey?uiText.retroBenchmarkScopeCurrent:uiText.retroBenchmarkScopeStale;
    result.appendChild(scope);
    for(const message of [
      data.status==='within-budget'?uiText.retroBenchmarkPass:uiText.retroBenchmarkLimited,
      `${uiText.retroBenchmarkThroughput}: ${number.format(data.throughputFps)} / ${number.format(data.targetFps)} FPS`,
      `${uiText.retroBenchmarkLatency}: ${number.format(data.p95FrameMs)} ms`,
      `PCSX ReARMed ${data.coreVersion}`
    ]){
      const line=document.createElement('p'); line.textContent=message; result.appendChild(line);
    }
    const date=new Date(state.startedAt);
    if(Number.isFinite(date.getTime())){
      const line=document.createElement('p');
      line.textContent=new Intl.DateTimeFormat(interfaceLanguage(),{dateStyle:'short',timeStyle:'short'}).format(date);
      result.appendChild(line);
    }
  }
}

async function loadRetroBenchmark(signal){
  const generation=++retroBenchmarkGeneration;
  try{
    do{
      const response=await fetch('/api/retro/benchmark',{cache:'no-store',signal});
      if(!response.ok) throw new Error('Benchmark status unavailable');
      const data=benchmarkReply(await response.json());
      if(signal.aborted||generation!==retroBenchmarkGeneration) return;
      retroBenchmarkState=data; renderRetroBenchmark();
      if(!retroBenchmarkActive(data)){
        if(data.status==='complete') void runRetroDeviceCheck();
        return;
      }
      await new Promise(resolve=>setTimeout(resolve,700));
    }while(!signal.aborted&&generation===retroBenchmarkGeneration);
  }catch(e){
    if(!signal.aborted&&generation===retroBenchmarkGeneration){
      retroBenchmarkState={...retroBenchmarkState,unavailable:true}; renderRetroBenchmark();
    }
  }
}

async function startRetroBenchmark(){
  const signal=retroSession?.signal;
  if(!signal||signal.aborted||document.getElementById('retroBenchmarkRun').disabled) return;
  if(retroBenchmarkState.unavailable) return loadRetroBenchmark(signal);
  const generation=++retroBenchmarkGeneration;
  retroBenchmarkState={status:'running'}; retroBenchmarkMutating=true; renderRetroBenchmark();
  try{
    // Consume the acknowledgement even when Parent settings close. A late
    // accepted job can then be canceled by its ID without changing the new UI.
    const response=await fetch('/api/retro/benchmark',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({system:'ps1'})});
    const data=await response.json();
    if(signal.aborted||generation!==retroBenchmarkGeneration){
      if(response.ok&&data.jobId) void fetch('/api/retro/benchmark/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jobId:data.jobId})}).catch(()=>{});
      return;
    }
    if(!response.ok){
      retroBenchmarkState={status:'error',error:['busy','unavailable'].includes(data.status)?data.status:'failed'};
      return;
    }
    retroBenchmarkState=benchmarkReply(data);
    void loadRetroBenchmark(signal);
  }catch(e){
    if(!signal.aborted&&generation===retroBenchmarkGeneration) retroBenchmarkState={status:'idle',unavailable:true};
  }finally{
    if(!signal.aborted){retroBenchmarkMutating=false;renderRetroBenchmark();}
  }
}

async function changeRetroBenchmark(action){
  const signal=retroSession?.signal, current=retroBenchmarkState;
  if(!signal||signal.aborted||!current.jobId||retroBenchmarkMutating) return;
  const generation=++retroBenchmarkGeneration;
  retroBenchmarkMutating=true; renderRetroBenchmark();
  try{
    const response=await fetch('/api/retro/benchmark/'+action,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({jobId:current.jobId}),signal});
    if(!response.ok) throw new Error('Benchmark action unavailable');
    const data=benchmarkReply(await response.json());
    if(signal.aborted||generation!==retroBenchmarkGeneration) return;
    retroBenchmarkState=data;
    if(action==='clear') void runRetroDeviceCheck();
    else void loadRetroBenchmark(signal);
  }catch(e){
    if(!signal.aborted&&generation===retroBenchmarkGeneration) retroBenchmarkState={...current,unavailable:true};
  }finally{
    if(!signal.aborted){retroBenchmarkMutating=false;renderRetroBenchmark();}
  }
}
