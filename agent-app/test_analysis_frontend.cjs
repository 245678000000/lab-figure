const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),{test}=require('node:test');
function harness(){
 class Element{
  constructor(){this.children=[];this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.textContent='';this.files=[];}
  append(...items){this.children.push(...items)}replaceChildren(...items){this.children=[...items]}add(item){this.children.push(item)}
  querySelector(){return this.query??=new Element()}showModal(){this.open=true}close(){this.open=false}
 }
 const nodes={},get=id=>nodes[id]??=new Element(),calls=[],errors=[],adopted=[];
 const data={id:'source',summary:{columns:[{name:'sample',type:'categorical'},{name:'G1',type:'numeric'},{name:'G2',type:'numeric'},{name:'target',type:'numeric'}]},id_columns:['sample'],annotation_columns:['target'],expression_profile:{units:'counts',label:'sample',feature_columns:['G1','G2'],rows_are_samples:true}};
 const ctx={console,document:{getElementById:get,createElement:()=>new Element()},Option:class{constructor(text,value){this.text=text;this.value=value}},S:{dataset:data,datasets:[data],busy:false,spec:{columns:{},exvivo:false}},columnPicker:{bind(select,columns,value){select.value=value||'';return{value:()=>select.value,destroy(){}}}},storeDraft(){},save(){},renderDatasetMenu(){},table:()=>new Element(),busy(value){ctx.S.busy=value},selectDataset(value,preserve,internal){assert.equal(internal,true);adopted.push(value);ctx.S.dataset=value},toast:e=>errors.push(e),restoreRunContext:async()=>{},workflowUI:{jobEnd(){}},waitJob:async()=>{},submit:async()=>{assert.equal(ctx.S.busy,false);calls.push('submit')},api:async(path,body)=>{calls.push({path,body});return []}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('static/analysis.js','utf8')+'\nglobalThis.analysis=analysisUI;',ctx);
 return{ctx,get,calls,errors,adopted};
}
test('changing settings after QC cannot apply a stale preparation',async()=>{
 const {ctx,get,calls,errors,adopted}=harness();
 ctx.api=async(path,body)=>{calls.push({path,body});return {sample_count:4,feature_count:2,zero_variance_count:0,low_expression_count:0,missing:0,nonfinite:0,notes:[]}};
 get('expressionButton').onclick();await get('checkExpression').onclick();assert.equal(get('prepareExpression').disabled,false);
 get('expressionUnits').value='tpm';await get('prepareExpression').onclick();
 assert.equal(calls.filter(c=>c.path?.endsWith('expression-prepare')).length,0);assert.equal(adopted.length,0);assert.match(errors.at(-1),/设置已改变/);
});
test('an asynchronous result cannot save against a newly selected dataset',async()=>{
 const {ctx,get,errors,adopted}=harness();let resolve;
 ctx.api=async()=>new Promise(r=>{resolve=r});get('expressionButton').onclick();const pending=get('checkExpression').onclick();
 ctx.S.dataset={...ctx.S.dataset,id:'other'};resolve({});await pending;
 assert.equal(adopted.length,0);assert.equal(get('prepareExpression').disabled,true);assert.match(errors.at(-1),/当前数据已改变/);
});
test('selected feature creates a frozen dataset and runs one chart after releasing busy state',async()=>{
 const {ctx,get,calls,adopted}=harness();
 ctx.api=async(path,body)=>{calls.push({path,body});if(path.endsWith('/plot'))return {...ctx.S.dataset,id:'frozen',demo_spec:{chart:'scatter'}};if(path.includes('/results'))return {rows:[{feature:'G1',n:4,r:.8,p:.1,q:.2}],columns:['feature','n','r','p','q'],total:1};return []};
 await ctx.analysis.showAnalysis({id:'analysis',settings:{mode:'raw'},feature_count:2,report:{notes:[]}});
 const wrap=get('analysisTable').children[0],table=wrap.children[0],row=table.children[1],button=row.children.at(-1).children[0];
 await button.onclick();assert.equal(adopted[0].id,'frozen');assert.deepEqual(JSON.parse(JSON.stringify(calls.find(c=>c.path?.endsWith('/plot')).body)),{gene:'G1'});assert.ok(calls.includes('submit'));
});

test('metadata preview sends the explicitly suggested text columns',async()=>{
 const {ctx,get,calls}=harness();ctx.FormData=class{append(){}};
 ctx.api=async(path,body)=>{calls.push({path,body});if(path==='/api/datasets')return{id:'annotations',filename:'samples.csv',summary:{columns:[{name:'sample'},{name:'group'},{name:'target'}]}};
 if(path.endsWith('metadata-columns'))return{columns:[{name:'sample',type:'categorical'},{name:'group',type:'categorical'},{name:'target',type:'numeric'}],text_columns:['sample','group']};
 return{valid:true,sample_count:4,matched_count:4,missing_count:0,extra_count:0,issues:[]}};
 get('metadataButton').onclick();get('metadataFile').files=[{}];await get('metadataFile').onchange();get('metadataDirection').checked=true;await get('previewMetadata').onclick();
 const request=calls.find(c=>c.path.endsWith('/metadata-preview')).body;
 assert.deepEqual(Array.from(request.text_columns),['sample','group']);assert.equal(request.metadata_sample_column,'sample');assert.equal(get('applyMetadata').disabled,false);
});
