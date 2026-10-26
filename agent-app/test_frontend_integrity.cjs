const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const app=fs.readFileSync('static/app.js','utf8');

test('style summary reports executed font overrides rather than only template defaults',()=>{
 const ctx={};vm.createContext(ctx);vm.runInContext(app.split('\n').find(s=>s.startsWith('function figureStyleSummary(')),ctx);
 const text=ctx.figureStyleSummary({figure_style:{base_size_pt:12,axis_text_pt:9.6,legend_text_pt:9.6,annotation_mm:3},figure_edit_info:{font_sizes:{title_size:18,note_size:8}},figure_edits:{title_size:30}});
 assert.match(text,/主标题 18 pt/);assert.match(text,/统计说明 8 pt/);assert.doesNotMatch(text,/30 pt/);assert.match(text,/模板原样式/);
});

test('late account response cannot replace newly selected platform',async()=>{
 const nodes={};const node=id=>nodes[id]??={value:'',textContent:'',disabled:false};
 const pending={};const ctx={$:node,S:{providers:{openai:{account:'codex'},claude:{account:'claude'}}},api:path=>new Promise(resolve=>pending[path]=resolve)};
 vm.createContext(ctx);
 vm.runInContext('let accountStatusRequest=0;\n'+app.split('\n').find(s=>s.startsWith('async function accountState(')),ctx);
 node('providerSelect').value='openai';const first=ctx.accountState();
 node('providerSelect').value='claude';const second=ctx.accountState();
 pending['/api/accounts/claude/status']({installed:true,message:'Claude current',identity:'new@example.org'});await second;
 pending['/api/accounts/codex/status']({installed:true,message:'Old Codex',identity:'old@example.org'});await first;
 assert.match(node('accountStatus').textContent,/new@example.org/);
 assert.doesNotMatch(node('accountStatus').textContent,/old@example.org/);
});

test('history loading locks navigation until the selected version is restored',async()=>{
 const nodes={};const node=id=>nodes[id]??={value:'',textContent:''};let resolve,calls=0;const shown=[];
 const ctx={$:node,S:{busy:false,result:{id:'previous'}},api:()=>{calls++;return new Promise(r=>resolve=r)},busy:v=>ctx.S.busy=v,storeDraft(){},showResult:async r=>shown.push(r.id),toast(){}};
 vm.createContext(ctx);vm.runInContext(app.split('\n').find(s=>s.startsWith("$('historySelect').onchange=")),ctx);
 node('historySelect').value='chosen';const first=node('historySelect').onchange();
 node('historySelect').value='later';const second=node('historySelect').onchange();
 assert.equal(ctx.S.busy,true);assert.equal(calls,1);
 resolve({id:'chosen'});await Promise.all([first,second]);assert.deepEqual(shown,['chosen']);assert.equal(ctx.S.busy,false);
});

test('old login URL cannot appear under another provider',async()=>{
 const nodes={};const node=id=>nodes[id]??={value:'',textContent:'',open:true,hidden:true};let resolve;
 const ctx={$:node,S:{providers:{openai:{account:'codex'},claude:{account:'claude'}}},api:()=>new Promise(r=>resolve=r)};
 vm.createContext(ctx);vm.runInContext('let loginRequest=0,accountStatusRequest=0;\n'+app.split('\n').find(s=>s.startsWith("$('loginButton').onclick=")),ctx);
 node('providerSelect').value='openai';const request=node('loginButton').onclick();
 node('providerSelect').value='claude';node('accountStatus').textContent='Claude current';
 resolve({id:'old',status:'waiting',url:'https://example.org/old',message:'Old login'});await request;
 assert.equal(node('loginInfo').hidden,true);assert.equal(node('accountStatus').textContent,'Claude current');
});
function harness(){
 const nodes={};const node=id=>nodes[id]??={hidden:false,value:'',textContent:'',classList:{toggle(){},remove(){},add(){}},append(){},replaceChildren(){},setAttribute(){}};
 const ctx={structuredClone,console,S:{datasets:[{id:'A',summary:{rows:4,columns:[]}},{id:'B',summary:{rows:4,columns:[]}}],dataset:{id:'A'},busy:true,spec:{chart:'pca'},result:null,catalog:{pca:{name:'PCA'}},settings:{enabled:true}},DEFAULT:{},workflowUI:{showResult(){},jobStart(){}},$:node,el:()=>node(Math.random()),renderParameters(){},link(){},table(){},loadEditor(){},renderHistory(){},renderDatasetMenu(){},renderData(){},renderMessages(){},tab(){},save(){},storeDraft(){},message(){}};
 vm.createContext(ctx);return {ctx,node};
}
test('showResult aligns selected dataset even during job recovery',async()=>{
 const {ctx}=harness();
 for(const name of ['selectDataset','restoreRunContext','showResult']){const line=app.split('\n').find(s=>s.startsWith('function '+name+'(')||s.startsWith('async function '+name+'('));if(line)vm.runInContext(line,ctx)}
 ctx.clearResult=()=>{};ctx.guessColumns=()=>({});
 await ctx.showResult({id:'runB',dataset_id:'B',spec:{chart:'pca',engine:'r'},runtime_seconds:1,code:'x',qa:[],report:{notes:[],analyzed_rows:4,input_rows:4,excluded_rows:0,missing_rows:0}});
 assert.equal(ctx.S.dataset.id,'B');assert.equal(ctx.S.result.dataset_id,'B');
});
test('visual editing exits old-image comparison before submitting current version',async()=>{
 const {ctx,node}=harness();ctx.S.busy=false;ctx.document={getElementById:node};ctx.S.result={id:'new',parent_run_id:'old'};ctx.sessionStorage={getItem(){return null}};
 node('visualDialog').showModal=()=>{};node('visualRequest').focus=()=>{};
 vm.runInContext(fs.readFileSync('static/workflows.js','utf8')+'\nworkflowUI.showResult(S.result,null);',ctx);
 node('comparePrevious').onclick();assert.match(node('figureImage').src,/old/);
 node('visualEdit').onclick();assert.equal(node('figureImage').src,'/api/runs/new/files/figure.png');assert.equal(node('comparisonNotice').hidden,true);
});
const pickerContext={};vm.createContext(pickerContext);vm.runInContext(fs.readFileSync('static/column-picker.js','utf8')+'\nglobalThis.mergeSelection=columnPicker.mergeSelection;',pickerContext);
test('filtered multi-select preserves hidden choices and removes visible deselections',()=>{
 const before=Array.from({length:20000},(_,i)=>'G'+i);
 const after=pickerContext.mergeSelection(before,['G19998','G19999'],['G19999','NEW']);
 assert.equal(after.length,20000);assert.ok(after.includes('G1'));assert.ok(!after.includes('G19998'));assert.ok(after.includes('NEW'));
});
test('transport failure retains job id for completed-result recovery after refresh',async()=>{
 const {ctx}=harness(),saved=new Map();ctx.S.busy=false;ctx.S.result={id:'parent'};
 ctx.sessionStorage={setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)};
 ctx.workflowUI={hasPending:()=>false,jobEnd(){}};ctx.editorUI={clearError(){},showError(){}};
 ctx.busy=()=>{};ctx.toast=()=>{};ctx.showRunError=()=>{};ctx.$('codeEditor').value='plot(1)';
 ctx.api=async()=>({job_id:'job123'});ctx.waitJob=async()=>{throw Error('network disconnected')};
 vm.runInContext(app.split('\n').find(s=>s.startsWith('async function runEditor(')),ctx);
 await ctx.runEditor();assert.equal(saved.get('labfigure.job'),'job123');
});

test('adopted job survives a transport failure before first poll',async()=>{
 const {ctx}=harness(),saved=new Map();
 ctx.sessionStorage={setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)};
 ctx.api=async()=>{throw Error('network disconnected')};
 vm.runInContext(app.split('\n').find(s=>s.startsWith('async function waitJob(')),ctx);
 await assert.rejects(ctx.waitJob('other-tab-job'),/network disconnected/);
 assert.equal(saved.get('labfigure.job'),'other-tab-job');
});

test('wide column menu searches all columns while rendering at most 100 matches',()=>{
 class Element{
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.value='';this.attributes={};this.multiple=false;}
  append(child){this.children.push(child);child.parentElement=this;}
  insertBefore(child,reference){this.children.splice(this.children.indexOf(reference),0,child);child.parentElement=this;}
  setAttribute(k,v){this.attributes[k]=v;}getAttribute(k){return this.attributes[k]||null;}
  replaceChildren(){this.children=[];}add(option){this.children.push(option);}
  get options(){return this.children;}get selectedOptions(){return this.children.filter(o=>o.selected);}
  remove(){this.parentElement.children=this.parentElement.children.filter(x=>x!==this);}
 }
 const context={document:{createElement:tag=>new Element(tag)},Option:class{constructor(text,value){this.text=text;this.value=value;this.selected=false;}}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/column-picker.js','utf8')+'\nglobalThis.bind=columnPicker.bind;',context);
 const host=new Element('label'),select=new Element('select');select.multiple=true;host.append(select);
 let actual;const columns=Array.from({length:50000},(_,i)=>({name:'GENE_'+i,type:'numeric'}));
 const picker=context.bind(select,columns,['GENE_0','GENE_49999'],value=>actual=value);
 assert.equal(select.options.length,100);
 const search=host.children.find(c=>c.type==='search');search.value='GENE_49999';search.oninput();
 assert.equal(select.options.length,1);assert.equal(select.options[0].selected,true);
 select.options[0].selected=false;select.onchange();
 assert.deepEqual(Array.from(actual),['GENE_0']);assert.deepEqual(Array.from(picker.value()),['GENE_0']);
});
