/* Select actual PDF text; presentation changes still run through the source script. */
class FigureCanvas {
  constructor(stage, toolbar, change) {
    this.stage=stage; this.toolbar=toolbar; this.change=change;
    this.labels={title:'主标题',x:'横轴名称',y:'纵轴名称',note:'底部统计说明（r、P 值等）'};
    this.prefix={title:'title',x:'x_label',y:'y_label',note:'note'};
    toolbar.innerHTML=`<strong id="canvasSelected">点击图中文字</strong><span id="canvasOriginal" class="hint"></span>
      <div class="canvas-tools"><label>字体<select id="canvasFont"></select></label><label>字号（pt）<input id="canvasSize" type="number" min="5" max="48" step="any"></label></div>
      <label id="canvasTextLabel" hidden>文字<input id="canvasText" maxlength="120"></label><p class="hint">点击标题、坐标名称或统计说明。拖动统计说明可移动位置；方向键微调，Shift + 方向键快速移动。预览供排版，应用后检查最终导出。</p>`;
    this.font=toolbar.querySelector('#canvasFont'); this.size=toolbar.querySelector('#canvasSize');
    this.text=toolbar.querySelector('#canvasText');
    this.font.onchange=()=>this.setStyle('family',this.font.value||null);
    this.size.oninput=()=>{if(this.size.value && this.size.checkValidity())this.setStyle('size',Number(this.size.value));};
    this.text.oninput=()=>{if(!this.selected||this.selected.role==='note')return; const key={title:'title',x:'x_label',y:'y_label'}[this.selected.role];this.change(key,this.text.value);this.render();};
  }
  family(font) {
    const f=font.replace(/^[A-Z]{6}\+/,'');
    if(/Arial|Helvetica/i.test(f))return 'Arial';
    if(/Times|NimbusRoman/i.test(f))return 'Times New Roman';
    if(/MicrosoftYaHei/i.test(f))return 'Microsoft YaHei';
    if(/SimSun/i.test(f))return 'SimSun';
    return f.replace(/MT$/,'');
  }
  load(data, edits) {
    this.data=data; this.edits=edits; this.selected=null; this.displayNoteAtOriginal=true;
    this.stage.querySelector('img').src=data.background;
    this.svg?.remove();
    this.svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    this.svg.id='figureTextCanvas'; this.svg.setAttribute('viewBox',`0 0 ${data.width} ${data.height}`);
    this.stage.append(this.svg); this.render();
    this.select(data.objects.find(o=>o.role==='note')||data.objects[0]);
  }
  setStyle(kind,value) {
    if(!this.selected)return;
    this.change(this.prefix[this.selected.role]+'_'+kind,value);this.render();
  }
  select(object) {
    if(!object)return;
    this.selected=object;
    const prefix=this.prefix[object.role];
    this.toolbar.querySelector('#canvasSelected').textContent=this.labels[object.role];
    this.toolbar.querySelector('#canvasOriginal').textContent=`当前导出：${object.font} · ${object.size} pt`;
    this.font.replaceChildren();
    for(const [value,label] of [['',`保持 ${object.font}`],...['Arial','Times New Roman','Calibri','Cambria','Consolas','Microsoft YaHei','SimSun'].map(f=>[f,f])]) {
      const option=document.createElement('option');option.value=value;option.textContent=label;this.font.append(option);
    }
    this.font.value=this.style(object,'family')||'';
    this.size.value=this.style(object,'size')??object.size;
    this.toolbar.querySelector('#canvasTextLabel').hidden=object.role==='note';
    const key={title:'title',x:'x_label',y:'y_label'}[object.role];
    this.text.value=this.edits[key]??object.text;
    this.render();
  }
  render() {
    if(!this.data)return;
    const ns='http://www.w3.org/2000/svg',make=(tag,attrs)=>{const n=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
    this.svg.replaceChildren();
    for(const object of this.data.objects) {
      const group=make('g',{'data-role':object.role,tabindex:0,role:'button','aria-label':this.labels[object.role]});
      const [x0,y0,x1,y1]=object.bbox,cx=(x0+x1)/2,cy=(y0+y1)/2;
      const size=this.style(object,'size')??object.size,family=this.style(object,'family');
      const moved=object.role==='note'&&this.edits.note_position==='manual'&&!this.displayNoteAtOriginal;
      let dx=moved?this.edits.note_x*this.data.width-cx:0,dy=moved?(1-this.edits.note_y)*this.data.height-cy:0;
      group.setAttribute('transform',`translate(${dx} ${dy})`);
      const key={title:'title',x:'x_label',y:'y_label'}[object.role],replacement=this.edits[key];
      for(const line of object.lines) {
        for(const [index,span] of line.spans.entries()) {
          if(replacement!=null&&index>0)continue;
          const ratio=size/object.size,x=cx+(span.origin[0]-cx)*ratio,y=cy+(span.origin[1]-cy)*ratio;
          const text=make('text',{x,y,'font-family':family||this.family(span.font),'font-size':span.size*ratio,'font-weight':/Bold/i.test(span.font)?'bold':'normal','font-style':/Italic|Oblique/i.test(span.font)?'italic':'normal','fill':'#'+span.color.toString(16).padStart(6,'0')});
          if(line.vertical)text.setAttribute('transform',`rotate(-90 ${x} ${y})`);
          text.textContent=replacement??span.text;
          group.append(text);
        }
      }
      this.svg.append(group);
      const b=group.getBBox();
      if(moved){dx=this.edits.note_x*this.data.width-b.x-b.width/2;dy=(1-this.edits.note_y)*this.data.height-b.y-b.height/2;group.setAttribute('transform',`translate(${dx} ${dy})`);}
      const rect=make('rect',{x:b.width?b.x-2:x0-2,y:b.height?b.y-2:y0-2,width:Math.max(b.width,x1-x0)+4,height:Math.max(b.height,y1-y0)+4,fill:'transparent',stroke:this.selected===object?'#2582ec':'transparent','stroke-width':.7});
      group.append(rect);group.style.cursor=object.role==='note'?'move':'pointer';
      group.onpointerdown=event=>{
        if(event.button!==0)return;event.stopPropagation();event.preventDefault();this.select(object);
        this.svg.querySelector('[data-role="'+object.role+'"]').focus({preventScroll:true});
        if(object.role!=='note')return;
        const start=this.point(event),initial=[b.x+b.width/2+dx,b.y+b.height/2+dy];
        this.svg.setPointerCapture(event.pointerId);
        this.svg.onpointermove=e=>{const p=this.point(e);this.move(initial[0]+p.x-start.x,initial[1]+p.y-start.y);};
        this.svg.onpointerup=this.svg.onpointercancel=()=>{this.svg.onpointermove=null;this.svg.querySelector('[data-role="note"]').focus({preventScroll:true});};
      };
      group.onkeydown=event=>{
        if(event.key==='Enter'||event.key===' '){event.preventDefault();this.select(object);return;}
        const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
        if(!delta||object.role!=='note')return;
        event.preventDefault();this.select(object);const step=event.shiftKey?5:1;
        this.move(b.x+b.width/2+dx+delta[0]*step,b.y+b.height/2+dy+delta[1]*step);this.svg.querySelector('[data-role="note"]').focus();
      };
    }
  }
  point(event) {const p=new DOMPoint(event.clientX,event.clientY);return p.matrixTransform(this.svg.getScreenCTM().inverse());}
  style(object,kind) {return this.edits[this.prefix[object.role]+'_'+kind]??(['x','y'].includes(object.role)?this.edits['axis_title_'+kind]:null);}
  move(x,y) {
    this.displayNoteAtOriginal=false;
    const box=this.svg.querySelector('[data-role="note"]').getBBox();
    x=Math.max(box.width/2+2,Math.min(this.data.width-box.width/2-2,x));
    y=Math.max(box.height/2+2,Math.min(this.data.height-box.height/2-2,y));
    const clamp=n=>Math.max(.02,Math.min(.98,n));
    this.change('note_position','manual');this.change('note_hjust',.5);this.change('note_vjust',.5);
    this.change('note_x',clamp(x/this.data.width));this.change('note_y',clamp(1-y/this.data.height));this.render();
  }
  clear() {this.data=null;this.svg?.remove();this.selected=null;}
}
