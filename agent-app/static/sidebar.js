/* Navigation stays on the left; all plot/code controls retain their handlers. */
const sidebarUI = (() => {
  const get = id => document.getElementById(id);
  const side = document.createElement('aside');
  side.id='appSidebar'; side.setAttribute('aria-label','工作区导航');
  side.innerHTML=`<div class="sidebar-brand"></div><button id="toggleSidebar" type="button" title="收起侧栏" aria-label="收起侧栏">‹</button>
    <div class="sidebar-content"><section class="sidebar-project"><h2>工作区</h2><div id="sidebarActions"></div><label>当前数据<div id="sidebarDataset"></div></label></section>
    <section class="sidebar-history"><h2>历史版本</h2><input id="historySearch" placeholder="搜索图型或文件名" aria-label="搜索历史版本"><div id="sidebarHistory" role="list"></div></section>
    <section class="sidebar-account"><div class="sidebar-account-heading"><h2>模型与账号</h2><button id="refreshConnection" type="button" title="刷新账号和额度">刷新</button></div><div id="connectionSummary" aria-live="polite">正在读取连接信息…</div><div id="sidebarModelSettings"></div></section></div>`;
  document.body.prepend(side);
  side.querySelector('.sidebar-brand').append(document.querySelector('.app-brand'));
  get('sidebarActions').append(get('uploadButton'),get('parametersButton'));
  get('sidebarDataset').append(get('datasetSelect'));
  get('sidebarModelSettings').append(get('settingsButton'));
  get('settingsButton').textContent='管理模型与登录';
  const historyRow=document.querySelector('.history-row');
  historyRow.hidden=true; // Keep the existing select as the single history event path.
  const header=document.querySelector('.app-header');
  const expand=document.createElement('button'); expand.id='expandSidebar';expand.textContent='☰';expand.title='展开侧栏';expand.setAttribute('aria-label','展开侧栏');header.prepend(expand);
  const title=document.createElement('span');title.className='workspace-title';title.textContent='科研作图工作台';header.insertBefore(title,get('modePill'));
  document.body.classList.add('with-sidebar');
  try { const saved=localStorage.getItem('labfigure.sidebarCollapsed');document.body.classList.toggle('sidebar-collapsed',saved===null?matchMedia('(max-width:800px)').matches:saved==='true'); } catch {}
  function toggle() {
    const collapsed=document.body.classList.toggle('sidebar-collapsed');
    try { localStorage.setItem('labfigure.sidebarCollapsed',String(collapsed)); } catch {}
    window.dispatchEvent(new Event('resize'));
  }
  get('toggleSidebar').onclick=expand.onclick=toggle;
  function history() {
    if(typeof S==='undefined')return;
    const q=get('historySearch').value.toLocaleLowerCase();
    const container=get('sidebarHistory');container.replaceChildren();
    let count=0;
    for(const run of S.runs) {
      const name=S.catalog[run.spec.chart]?.name||run.spec.chart;
      if(!(name+' '+run.dataset_name).toLocaleLowerCase().includes(q))continue;
      const b=document.createElement('button');b.type='button';b.className='sidebar-run';b.disabled=S.busy;
      b.classList.toggle('selected',S.result?.id===run.id);
      b.setAttribute('aria-current',S.result?.id===run.id?'true':'false');
      const label=document.createElement('strong');label.textContent=name;
      const file=document.createElement('span');file.textContent=run.dataset_name;
      const time=document.createElement('small');time.textContent=new Date(run.created*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
      b.append(label,time,file);b.title=name+' · '+run.dataset_name;
      b.onclick=()=>{if(S.busy)return;get('historySelect').value=run.id;get('historySelect').dispatchEvent(new Event('change'));};
      container.append(b);if(++count>=100)break;
    }
    if(!count){const p=document.createElement('p');p.className='hint';p.textContent=q?'没有匹配的版本':'生成图片后，版本会保存在这里';container.append(p);}
  }
  get('historySearch').oninput=history;
  new MutationObserver(history).observe(get('historySelect'),{childList:true,attributes:true,attributeFilter:['disabled']});
  function text(parent,tag,value,cls) { const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;parent.append(n);return n; }
  function windowName(minutes) {
    if(minutes==null)return '时间窗口未知';
    if(minutes%1440===0)return minutes/1440+' 天';
    if(minutes%60===0)return minutes/60+' 小时';
    return minutes+' 分钟';
  }
  let serial=0, signature='', queued=false;
  async function refresh() {
    if(typeof S==='undefined'||!S.settings?.provider)return;
    const ticket=++serial, box=get('connectionSummary');
    get('refreshConnection').disabled=true; box.replaceChildren();text(box,'p','正在核对账号与额度…','hint');
    try {
      const r=await api('/api/connection/info');
      if(ticket!==serial)return;
      box.replaceChildren();
      text(box,'strong',r.provider_name+' · '+(r.connection==='account'?'账号':'API'),'connection-name');
      text(box,'p',r.model,'connection-model');
      if(!r.enabled)text(box,'p','模型已停用 · 当前使用本地模板','hint');
      text(box,'p',r.identity|| (r.connection==='account'?(r.logged_in===false?'未登录':'账号身份暂不可读取'):(r.credential_id?'密钥标识 '+r.credential_id:'未设置密钥')),'connection-identity');
      if(r.plan)text(box,'small','套餐：'+r.plan);
      if(r.endpoint)text(box,'small',r.endpoint,'connection-endpoint');
      text(box,'p',r.message,'hint');
      for(const w of r.windows||[]) {
        const row=document.createElement('div');row.className='quota-window';
        const label=w.bucket+' · '+windowName(w.window_minutes);
        text(row,'small',label);
        text(row,'strong',w.remaining_percent==null?'额度未知':'剩余 '+w.remaining_percent+'%');
        if(w.remaining_percent!=null){const meter=document.createElement('progress');meter.max=100;meter.value=w.remaining_percent;meter.setAttribute('aria-label',label+'剩余额度');row.append(meter);}
        if(w.resets_at)text(row,'small',new Date(w.resets_at*1000).toLocaleString('zh-CN')+' 重置');
        box.append(row);
      }
      for(const b of r.balances||[])text(box,'strong','可用余额 '+b.available.toFixed(2)+' '+b.currency,'connection-balance');
      text(box,'p',r.quota_message,'hint');
      if(r.console_url){const link=text(box,'a','官方用量页');link.href=r.console_url;link.target='_blank';link.rel='noopener noreferrer';}
      text(box,'small','更新于 '+new Date(r.checked_at*1000).toLocaleTimeString('zh-CN'),'connection-updated');
    } catch(error) { if(ticket===serial){box.replaceChildren();text(box,'p','账号或额度读取失败，点击刷新重试。','hint');} }
    finally { if(ticket===serial)get('refreshConnection').disabled=false; }
  }
  function sync() {
    if(typeof S==='undefined')return;
    const next=JSON.stringify([S.settings.provider,S.settings.connection,S.settings.model,S.settings.base_url,S.settings.has_key,S.settings.enabled]);
    if(next===signature)return;signature=next;
    if(!queued){queued=true;queueMicrotask(()=>{queued=false;refresh();});}
  }
  get('refreshConnection').onclick=refresh;
  new MutationObserver(sync).observe(get('modePill'),{childList:true,subtree:true,characterData:true});
  // Re-check after enabling settings or finishing a login, including a same-provider account change.
  get('settingsDialog').addEventListener('close',refresh);
  return {refresh,history,windowName};
})();
