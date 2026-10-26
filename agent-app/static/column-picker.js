/* Keep wide-table menus bounded without discarding selections outside a search. */
const columnPicker=(()=>{
  function mergeSelection(previous,visible,chosen){const next=new Set(previous);for(const name of visible)next.delete(name);for(const name of chosen)next.add(name);return [...next]}
  function bind(select,columns,value,onChange){
    let selected=select.multiple?[...(value||[])]:value||'';
    const host=select.parentElement,search=document.createElement('input'),note=document.createElement('small');
    search.type='search';search.placeholder='搜索列名';search.setAttribute('aria-label','搜索'+(select.getAttribute('aria-label')||'列名'));
    search.hidden=columns.length<=100;note.className='hint';select.dataset.managed='true';
    host.insertBefore(search,select);host.append(note);
    function paint(){
      const q=search.value.toLocaleLowerCase(),matches=columns.filter(c=>c.name.toLocaleLowerCase().includes(q));
      let visible=matches.slice(0,100);
      if(!select.multiple&&selected&&!visible.some(c=>c.name===selected)){const current=columns.find(c=>c.name===selected);if(current)visible=[current,...visible.slice(0,99)]}
      select.replaceChildren();if(!select.multiple)select.add(new Option('不指定 / 请选择',''));
      const chosen=new Set(select.multiple?selected:[selected]);
      for(const c of visible){const option=new Option(c.name+(c.type==='numeric'?'（数值）':''),c.name);option.selected=chosen.has(c.name);select.add(option)}
      if(!select.multiple)select.value=selected;
      note.textContent=(select.multiple?'已选 '+selected.length+' 列；':'')+(columns.length>100?'共 '+columns.length+' 列，显示最多 100 个匹配项；搜索不会清空其他选择。':'');
      note.hidden=!note.textContent;
    }
    select.onchange=()=>{selected=select.multiple?mergeSelection(selected,[...select.options].map(o=>o.value),[...select.selectedOptions].map(o=>o.value)):select.value;onChange(selected);paint()};
    search.oninput=paint;paint();
    return {value:()=>select.multiple?[...selected]:selected,set(value){selected=select.multiple?[...value]:value;paint()},destroy(){search.remove();note.remove()}};
  }
  return {bind,mergeSelection};
})();
