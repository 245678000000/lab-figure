/* Editor, search, error locations and the image viewer. All dependencies are local. */
const editorUI = (()=>{
  const get=id=>document.getElementById(id), source=get('codeEditor');
  const cm=CodeMirror.fromTextArea(source,{mode:'r',lineNumbers:true,matchBrackets:true,indentUnit:2,tabSize:2,inputStyle:'contenteditable',readOnly:true,viewportMargin:25,lineWrapping:false,gutters:['CodeMirror-linenumbers','error-gutter'],extraKeys:{'Ctrl-Enter':()=>runEditor(),'Cmd-Enter':()=>runEditor(),'Ctrl-F':()=>openSearch(),'Cmd-F':()=>openSearch(),'Ctrl-H':()=>openSearch(),'Cmd-Alt-F':()=>openSearch(),Esc:()=>closeSearch(),Tab:c=>c.somethingSelected()?c.indentSelection('add'):c.replaceSelection('  '),'Shift-Tab':c=>c.indentSelection('subtract')}});
  cm.getInputField().setAttribute('aria-label','作图代码编辑器');
  cm.getInputField().setAttribute('role','textbox');
  cm.getInputField().setAttribute('aria-multiline','true');
  let changeLines=[];let updating=false,marks=[],errorLine=null,errorLocation=null,matches=[];
  function refresh(){requestAnimationFrame(()=>cm.refresh())}
  function clearError(){if(errorLine!==null)cm.removeLineClass(errorLine,'background','code-error-line');errorLine=null;errorLocation=null;cm.clearGutter('error-gutter');get('codeErrorPanel').hidden=true}
  cm.on('change',()=>{if(updating)return;for(const n of changeLines)cm.removeLineClass(n,'background','code-added-line');changeLines=[];source.value=cm.getValue();clearError();storeDraft();if(!get('searchPanel').hidden)highlight()});
  function sync(){const value=source.value;if(cm.getValue()!==value){updating=true;cm.setValue(value);cm.clearHistory();updating=false;clearError()}const mode=typeof S!=='undefined'&&S.result?.spec.engine==='python'?'python':'r';if(cm.getOption('mode')!==mode)cm.setOption('mode',mode);refresh()}
  function openSearch(){get('searchPanel').hidden=false;get('findText').focus();get('findText').select();highlight();refresh()}
  function closeSearch(){get('searchPanel').hidden=true;marks.forEach(m=>m.clear());marks=[];cm.focus();refresh()}
  function highlight(){marks.forEach(m=>m.clear());marks=[];matches=[];const query=get('findText').value;if(query){const cursor=cm.getSearchCursor(query,{line:0,ch:0},!get('matchCase').checked);while(cursor.findNext()){matches.push({from:cursor.from(),to:cursor.to()});if(marks.length<500)marks.push(cm.markText(cursor.from(),cursor.to(),{className:'code-search-match'}))}}get('findCount').textContent=matches.length+' 处';return matches}
  const compare=(a,b)=>a.line-b.line||a.ch-b.ch;
  function find(back=false){if(!highlight().length)return;const pos=cm.getCursor(back?'from':'to');let match=back?[...matches].reverse().find(m=>compare(m.to,pos)<=0):matches.find(m=>compare(m.from,pos)>=0);match ||= back?matches.at(-1):matches[0];cm.setSelection(match.from,match.to);cm.scrollIntoView({from:match.from,to:match.to},70);get('findCount').textContent=(matches.indexOf(match)+1)+' / '+matches.length;cm.focus()}
  function replaceOne(){if(source.disabled)return;const query=get('findText').value,selected=cm.getSelection(),equal=get('matchCase').checked?selected===query:selected.toLocaleLowerCase()===query.toLocaleLowerCase();if(!query)return;if(!equal){find();return}cm.replaceSelection(get('replaceText').value,'end','+input');find()}
  function replaceAll(){if(source.disabled)return;const list=highlight();if(!list.length)return;const replacement=get('replaceText').value;cm.operation(()=>{for(const m of [...list].reverse())cm.replaceRange(replacement,m.from,m.to,'+input')});highlight()}
  get('findCode').onclick=openSearch;get('closeFind').onclick=closeSearch;get('findNext').onclick=()=>find();get('findPrev').onclick=()=>find(true);get('findText').oninput=highlight;get('matchCase').onchange=highlight;get('replaceOne').onclick=replaceOne;get('replaceAll').onclick=replaceAll;
  get('findText').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();find(e.shiftKey)}if(e.key==='Escape')closeSearch()};get('replaceText').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();replaceOne()}if(e.key==='Escape')closeSearch()};
  function jump(){if(!errorLocation)return;const line=Math.min(Math.max(errorLocation.line-1,0),cm.lineCount()-1),ch=Math.min(Math.max((errorLocation.column||1)-1,0),cm.getLine(line).length);cm.setCursor({line,ch});cm.scrollIntoView({line,ch},90);cm.focus()}
  function showError(message,diagnostic){clearError();get('codeError').textContent=message;get('codeErrorPanel').hidden=false;get('errorHint').textContent=diagnostic?.hint||'运行未完成，请展开原始错误检查。上一张成功图片已保留。';const b=get('jumpToError');b.hidden=!diagnostic?.line;if(diagnostic?.line){errorLocation=diagnostic;const line=Math.min(Math.max(diagnostic.line-1,0),cm.lineCount()-1);errorLine=line;cm.addLineClass(line,'background','code-error-line');const marker=document.createElement('span');marker.textContent='●';marker.className='error-marker';marker.title=diagnostic.message||message;cm.setGutterMarker(line,'error-gutter',marker);b.textContent='定位到第 '+diagnostic.line+' 行'+(diagnostic.exact?'':'附近');jump()}}
  get('jumpToError').onclick=jump;
  const resize=new ResizeObserver(refresh);resize.observe(cm.getWrapperElement().parentElement);
  return {applyDraft(code,changes){for(const n of changeLines)cm.removeLineClass(n,'background','code-added-line');changeLines=[];cm.replaceRange(code,{line:0,ch:0},cm.posFromIndex(cm.getValue().length),'+model');for(const change of changes||[])for(let i=0;i<change.added.length;i++){const line=change.new_start-1+i;if(line<cm.lineCount()){cm.addLineClass(line,'background','code-added-line');changeLines.push(line)}}},sync,clearError,showError,refresh,setReadOnly(value){cm.setOption('readOnly',!!value);get('replaceOne').disabled=!!value;get('replaceAll').disabled=!!value},focus:()=>cm.focus()};
})();

const figureViewer=(()=>{
  const get=id=>document.getElementById(id),viewport=get('imageViewport'),stage=get('imageStage'),image=get('figureImage'),result=get('figureResult');
  let mode='fit',scale=1,drag=null;
  function fitScale(){return Math.min(1,Math.max(20,viewport.clientWidth-24)/Math.max(1,image.naturalWidth),Math.max(20,viewport.clientHeight-24)/Math.max(1,image.naturalHeight))}
  function draw(){if(!image.naturalWidth)return;if(mode==='fit')scale=fitScale();image.style.width=Math.round(image.naturalWidth*scale)+'px';image.style.height=Math.round(image.naturalHeight*scale)+'px';get('zoomLevel').textContent=Math.round(scale*100)+'%';get('zoomLevel').title='当前缩放比例；点击切换到 100% 原始像素';viewport.classList.toggle('can-pan',image.naturalWidth*scale>viewport.clientWidth||image.naturalHeight*scale>viewport.clientHeight)}
  function setScale(value){mode='manual';const old=scale,x=(viewport.scrollLeft+viewport.clientWidth/2)/Math.max(old,.001),y=(viewport.scrollTop+viewport.clientHeight/2)/Math.max(old,.001);scale=Math.max(.05,Math.min(4,value));draw();viewport.scrollLeft=x*scale-viewport.clientWidth/2;viewport.scrollTop=y*scale-viewport.clientHeight/2}
  function fit(){mode='fit';draw();viewport.scrollTo(0,0)}
  function loaded(){fit();for(const id of ['zoomOut','zoomLevel','zoomIn','zoomFit','imageFullscreen'])get(id).disabled=false}
  image.addEventListener('load',loaded);if(image.complete&&image.naturalWidth)loaded();
  get('zoomOut').onclick=()=>setScale(scale/1.25);get('zoomIn').onclick=()=>setScale(scale*1.25);get('zoomLevel').onclick=()=>setScale(1);get('zoomFit').onclick=fit;
  get('imageFullscreen').onclick=async()=>{try{if(document.fullscreenElement===result)await document.exitFullscreen();else await result.requestFullscreen()}catch{result.classList.toggle('viewer-expanded');get('imageFullscreen').textContent=result.classList.contains('viewer-expanded')?'退出全屏':'全屏';requestAnimationFrame(draw)}};
  document.addEventListener('fullscreenchange',()=>{get('imageFullscreen').textContent=document.fullscreenElement===result?'退出全屏':'全屏';requestAnimationFrame(draw)});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&result.classList.contains('viewer-expanded')){result.classList.remove('viewer-expanded');get('imageFullscreen').textContent='全屏';draw()}});
  viewport.addEventListener('pointerdown',e=>{if(e.button!==0||!viewport.classList.contains('can-pan'))return;drag={x:e.clientX,y:e.clientY,left:viewport.scrollLeft,top:viewport.scrollTop};viewport.setPointerCapture(e.pointerId);viewport.classList.add('panning');e.preventDefault()});
  viewport.addEventListener('pointermove',e=>{if(!drag)return;viewport.scrollLeft=drag.left+drag.x-e.clientX;viewport.scrollTop=drag.top+drag.y-e.clientY});
  function endDrag(){drag=null;viewport.classList.remove('panning')}viewport.addEventListener('pointerup',endDrag);viewport.addEventListener('pointercancel',endDrag);viewport.addEventListener('lostpointercapture',endDrag);
  viewport.addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey){e.preventDefault();setScale(scale*(e.deltaY<0?1.1:1/1.1))}},{passive:false});
  viewport.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){e.preventDefault();setScale(scale*1.25)}else if(e.key==='-'){e.preventDefault();setScale(scale/1.25)}else if(e.key==='0'){e.preventDefault();fit()}});
  new ResizeObserver(()=>draw()).observe(viewport);
  for(const id of ['zoomOut','zoomLevel','zoomIn','zoomFit','imageFullscreen'])get(id).disabled=true;
  return {fit};
})();

(()=>{
  const host=document.getElementById('figureTab'),bar=document.getElementById('splitter');let dragging=false,percent=50;
  function set(value){percent=Math.max(25,Math.min(75,value));host.style.setProperty('--code-width',percent+'%');bar.setAttribute('aria-valuenow',Math.round(percent));try{localStorage.setItem('labfigure.split',String(percent))}catch{}editorUI.refresh()}
  try{const prior=Number(localStorage.getItem('labfigure.split'));if(prior>=25&&prior<=75)set(prior)}catch{}
  bar.addEventListener('pointerdown',e=>{if(e.button!==0)return;dragging=true;bar.setPointerCapture(e.pointerId);document.body.classList.add('resizing-split');e.preventDefault()});
  bar.addEventListener('pointermove',e=>{if(!dragging)return;const r=host.getBoundingClientRect();set((e.clientX-r.left)/r.width*100)});
  function stop(){dragging=false;document.body.classList.remove('resizing-split')}bar.addEventListener('pointerup',stop);bar.addEventListener('pointercancel',stop);bar.addEventListener('lostpointercapture',stop);
  bar.addEventListener('dblclick',()=>set(50));bar.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();set(percent+(e.key==='ArrowLeft'?-2:2))}else if(e.key==='Home'){e.preventDefault();set(50)}});
})();
