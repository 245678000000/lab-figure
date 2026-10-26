/* Presentation edits use the current editor buffer and save a new run. */
const figureEditUI = (() => {
  const get = id => document.getElementById(id);
  const button = document.createElement('button');
  button.id = 'editFigure';
  button.textContent = '在图上编辑';
  get('visualEdit').before(button);
  const dialog = document.createElement('dialog');
  dialog.id = 'figureEditDialog';
  dialog.className = 'wide-dialog';
  dialog.innerHTML = `
    <div class="dialog-heading"><h2>在图上编辑</h2><button id="closeFigureEdit" aria-label="关闭图片编辑">×</button></div>
    <form id="figureEditForm">
      <div class="figure-edit-layout"><section><div id="figureCanvasTools"></div><details class="more-options"><summary>更多文字与图例设置</summary>
        <p class="hint">输入即选中修改；取消勾选恢复代码原值。勾选后留空可隐藏文字。</p>
        <label><span class="checkbox"><input type="checkbox" id="editTitleEnabled">主标题</span><input id="editTitle" maxlength="120" placeholder="保持代码中的标题"></label>
        <label><span class="checkbox"><input type="checkbox" id="editXEnabled">横轴名称</span><input id="editX" maxlength="120" placeholder="保持代码中的横轴名称"></label>
        <label><span class="checkbox"><input type="checkbox" id="editYEnabled">纵轴名称</span><input id="editY" maxlength="120" placeholder="保持代码中的纵轴名称"></label>
        <details class="more-options" open><summary>字体大小（pt）</summary><p class="hint">留空沿用原样式；修改后同步用于导出。</p><div class="font-size-grid">
          <label>主标题<input id="fontTitle" type="number" min="5" max="48" step="any" placeholder="原字号"></label>
          <label>坐标名称<input id="fontAxis" type="number" min="5" max="48" step="any" placeholder="原字号"></label>
          <label>坐标刻度<input id="fontTicks" type="number" min="5" max="48" step="any" placeholder="原字号"></label>
          <label>图例<input id="fontLegend" type="number" min="5" max="48" step="any" placeholder="原字号"></label>
          <label>统计说明<input id="fontNote" type="number" min="5" max="48" step="any" placeholder="原字号"></label>
        </div><button id="resetFonts" type="button">恢复原字号</button></details>
        <label>图例（颜色、分组说明）<select id="editLegend"><option value="keep">保持代码位置</option><option value="manual">在预览中定位</option><option value="right">右侧</option><option value="left">左侧</option><option value="top">上方</option><option value="bottom">下方</option><option value="none">隐藏图例</option></select></label>
        <label>统计说明（相关系数、P 值等）<select id="editNote"><option value="keep">保持代码位置</option><option value="manual">在预览中定位</option></select></label>
        <div id="editPositionFields" hidden><label>当前定位对象<select id="editTarget"><option value="note">统计说明</option><option value="legend">图例</option></select></label>
          <div class="row"><label>距左边（%）<input id="editPosX" type="number" min="2" max="98" step="1"></label><label>距下边（%）<input id="editPosY" type="number" min="2" max="98" step="1"></label></div>
        </div>
      </details></section><section>
        <div id="editPreviewStage"><img id="editPreviewImage" alt="当前图像，选择定位后可点击或拖动标记" draggable="false"><button type="button" id="editLegendMarker" class="figure-edit-marker" hidden>图例</button><button type="button" id="editNoteMarker" class="figure-edit-marker" hidden>统计说明</button></div>
        <p class="hint">底部相关系数、P 值是统计说明，可以直接选中并拖动。图例是颜色或分组说明。基因标注与显著性括号仍通过代码修改。</p>
      </section></div>
      <p id="figureEditError" role="alert"></p>
      <div class="dialog-actions"><button id="applyFigureEdit" type="submit" class="primary">应用并更新图片</button></div>
    </form>`;
  document.body.append(dialog);
  let edits = {}, sourceRun = null, sourceCode = '', loadTicket=0, initialFonts={};
  const canvas = new FigureCanvas(get('editPreviewStage'),get('figureCanvasTools'),(key,value)=>{
    edits[key]=value;
    if(fontFields[key])get(fontFields[key]).value=value??'';
    const field=textFields.find(([k])=>k===key);if(field){get(field[1]).value=value??'';get(field[1]+'Enabled').checked=value!==null;}
    if(key==='note_position')get('editNote').value=value;
  });
  const textFields = [['title','editTitle'],['x_label','editX'],['y_label','editY']];
  const fontFields = {title_size:'fontTitle',axis_title_size:'fontAxis',tick_size:'fontTicks',legend_size:'fontLegend',note_size:'fontNote'};
  get('resetFonts').onclick = () => { for(const [key,id] of Object.entries(fontFields)){get(id).value='';edits[key]=null;} for(const key of ['title_family','axis_title_family','tick_family','legend_family','note_family','x_label_family','y_label_family','x_label_size','y_label_size'])edits[key]=null;canvas.render();canvas.select(canvas.selected); };
  const clamp = n => Math.max(.02, Math.min(.98, n));
  function updatePositions() {
    let target = get('editTarget').value;
    const active = ['note','legend'].filter(k => edits[k+'_position'] === 'manual');
    get('editPositionFields').hidden = !active.length;
    for (const option of get('editTarget').options) option.disabled = !active.includes(option.value);
    if (!active.includes(target)) get('editTarget').value = target = active[0] || 'note';
    for (const kind of ['note','legend']) {
      const marker = get(kind === 'note' ? 'editNoteMarker' : 'editLegendMarker');
      marker.hidden = !active.includes(kind) || (kind==='note' && canvas.data?.objects.some(o=>o.role==='note'));
      marker.style.left = 100*edits[kind+'_x']+'%';
      marker.style.top = 100*(1-edits[kind+'_y'])+'%';
      marker.classList.toggle('selected', target === kind);
    }
    get('editPosX').value = Math.round(edits[target+'_x']*100);
    get('editPosY').value = Math.round(edits[target+'_y']*100);
  }
  button.onclick = async () => {
    if (S.busy || !S.result) return;
    if (workflowUI.hasPending()) { toast('请先接受或放弃 AI 修改'); return; }
    const ticket=++loadTicket;canvas.clear();
    sourceRun = S.result.id;
    sourceCode = get('codeEditor').value;
    edits = {title:null,x_label:null,y_label:null,legend_position:'keep',legend_x:.8,legend_y:.75,note_position:'keep',note_x:.32,note_y:.8,...S.result.figure_edits};
    for(const [key,id] of Object.entries(fontFields)) get(id).value=edits[key]??'';
    initialFonts=Object.fromEntries(Object.entries(fontFields).map(([key,id])=>[key,get(id).value]));
    for (const [key,id] of textFields) {
      get(id).value = edits[key] ?? S.result.figure_edit_info?.[key] ?? S.result.spec[key] ?? '';
      get(id+'Enabled').checked = edits[key] !== null;
    }
    // Always show the current run, even if the main viewer is comparing its parent.
    get('editPreviewImage').src = '/api/runs/'+sourceRun+'/files/figure.png';
    get('editLegend').value = edits.legend_position;
    get('editNote').value = edits.note_position;
    get('figureEditError').textContent = '';
    updatePositions();
    get('canvasSelected').textContent='正在读取原字体和字号…';
    dialog.showModal();
    try {
      const data=await api('/api/runs/'+sourceRun+'/editable-figure');
      if(ticket!==loadTicket||!dialog.open)return;
      // Use the exported coordinates until the user actually drags; old positioning anchors differ.
      canvas.load(data,edits);
      for(const [role,key]of [['title','title_size'],['x','axis_title_size'],['y','axis_title_size'],['ticks','tick_size'],['note','note_size']]){
        const style=data.styles[role];if(!style)continue;
        const input=get(fontFields[key]);input.value=edits[key]??style.size;input.title='当前导出：'+style.font+' · '+style.size+' pt';
      }
      initialFonts=Object.fromEntries(Object.entries(fontFields).map(([key,id])=>[key,get(id).value]));
      updatePositions();
      if(sourceCode!==S.result.code)get('figureEditError').textContent='画布显示最近导出的图片；未运行的代码修改会在应用时一起执行。';
    } catch(error){if(ticket===loadTicket&&dialog.open){get('canvasSelected').textContent='无法读取图中文字';get('figureEditError').textContent=error.message;}}
  };
  get('closeFigureEdit').onclick = () => dialog.close();
  dialog.addEventListener('close',()=>{loadTicket++;});
  for (const [key,id] of textFields){ get(id).oninput = () => { get(id+'Enabled').checked = true;edits[key]=get(id).value;canvas.render(); };get(id+'Enabled').onchange=()=>{edits[key]=get(id+'Enabled').checked?get(id).value:null;canvas.render();};}
  for(const [key,id]of Object.entries(fontFields))get(id).oninput=()=>{if(get(id).checkValidity()){if(key==='axis_title_size'){edits.x_label_size=null;edits.y_label_size=null;}edits[key]=get(id).value===''?null:Number(get(id).value);canvas.render();canvas.select(canvas.selected);}};
  for (const kind of ['legend','note']) get(kind === 'legend' ? 'editLegend' : 'editNote').onchange = e => {
    edits[kind+'_position'] = e.target.value;
    get('editTarget').value = kind;
    if(kind==='note'){canvas.displayNoteAtOriginal=false;edits.note_hjust=.5;edits.note_vjust=.5;canvas.render();}
    updatePositions();
  };
  get('editTarget').onchange = updatePositions;
  for (const axis of ['X','Y']) get('editPos'+axis).onchange = e => {
    if (!e.target.checkValidity() || e.target.value === '') return;
    edits[get('editTarget').value+'_'+axis.toLowerCase()] = clamp(Number(e.target.value)/100);
    canvas.displayNoteAtOriginal=false;canvas.render();updatePositions();
  };
  const stage = get('editPreviewStage');
  let dragging = false;
  function locate(event) {
    const target = get('editTarget').value;
    if (edits[target+'_position'] !== 'manual') return;
    const box = get('editPreviewImage').getBoundingClientRect();
    if (!box.width || !box.height) return;
    edits[target+'_x'] = clamp((event.clientX-box.left)/box.width);
    edits[target+'_y'] = clamp(1-(event.clientY-box.top)/box.height);
    updatePositions();
  }
  stage.onpointerdown = event => {
    if (event.button !== 0 || (canvas.data && event.target.id!=='editLegendMarker')) return;
    if (event.target.id === 'editLegendMarker') get('editTarget').value = 'legend';
    if (event.target.id === 'editNoteMarker') get('editTarget').value = 'note';
    if (edits[get('editTarget').value+'_position'] !== 'manual') return;
    event.preventDefault(); dragging = true; stage.setPointerCapture(event.pointerId); locate(event);
  };
  stage.onpointermove = event => { if (dragging) locate(event); };
  stage.onpointerup = stage.onpointercancel = () => { dragging = false; };
  for (const [kind,id] of [['legend','editLegendMarker'],['note','editNoteMarker']]) get(id).onkeydown = event => {
    const delta = {ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,1],ArrowDown:[0,-1]}[event.key];
    if (!delta) return;
    event.preventDefault(); get('editTarget').value = kind;
    edits[kind+'_x'] = clamp(edits[kind+'_x']+delta[0]*.01);
    edits[kind+'_y'] = clamp(edits[kind+'_y']+delta[1]*.01);
    updatePositions();
  };
  get('figureEditForm').onsubmit = async event => {
    event.preventDefault();
    if (S.busy || S.result?.id !== sourceRun) return;
    for (const [key,id] of textFields) edits[key] = get(id+'Enabled').checked ? get(id).value : null;
    for(const [key,id] of Object.entries(fontFields)) if(get(id).value!==initialFonts[key])edits[key]=get(id).value===''?null:Number(get(id).value);
    storeDraft(); dialog.close(); busy(true);
    try {
      const job = await api('/api/figure/edit', {parent_run_id:sourceRun, code:sourceCode, edits});
      sessionStorage.setItem('labfigure.job', job.job_id);
      await waitJob(job.job_id);
    } catch (error) {
      get('figureEditError').textContent = error.message;
      dialog.showModal();
    } finally { workflowUI.jobEnd(); busy(false); }
  };
  return {clamp};
})();
