"use strict";
const $=id=>document.getElementById(id);
const el=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=String(txt);return n;};
const add=(p,tag,cls,text)=>{const n=el(tag,cls,text);p.appendChild(n);return n;};
let page=0,limit=25,total=0;
function show(message){$("results").replaceChildren(el("div","empty",message));}
async function api(url){const res=await fetch(url),data=await res.json();if(!res.ok)throw Error(data.error||"Local source unavailable");return data;}
function metric(value,title){const n=el("div","metric");add(n,"b","",value);add(n,"span","",title);return n;}
function present(item){
 const row=el("article","record"),top=add(row,"div","rowtop");
 add(top,"strong","tag","SDS "+item.source_key+" · ECHA printed page "+item.source_page);
 add(top,"span","kind","2020 historical guidance");
 add(row,"p","words",item.title);
 const details=add(row,"details","detail");
 add(details,"summary","","Read source excerpt (Markdown)");
 const text=add(details,"pre","");
 text.style.whiteSpace="pre-wrap";text.style.overflowWrap="anywhere";
 text.style.fontFamily="inherit";text.textContent=item.text_preview;
 add(row,"p","meta","Source: "+item.reference+" · ECHA SDS guidance v4.0 (2020). Original PDF not supplied. No legal status verified.");
 return row;
}
async function search(){
 const params=new URLSearchParams({query:$("query").value,section:$("section").value,limit:String(limit),offset:String(page)});
 show("Searching locally imported guidance…");
 try{
  const response=await api("/api/guidance/search?"+params.toString());total=response.total;
  $("count").textContent=total.toLocaleString()+" matching source passages · showing "+(response.results.length?page+1:0)+"–"+Math.min(page+response.results.length,total);
  $("previous").disabled=page===0;$("next").disabled=page+limit>=total;
  $("results").replaceChildren(...response.results.map(present));
  if(!response.results.length)show("No passages matched. A missing result does not mean a legal requirement is absent.");
 }catch(error){show(error.message);}
}
async function start(){
 try {
  const data=await api("/api/guidance/summary");
  $("source").replaceChildren(metric(data.section_count,"SDS sections"),metric(data.passage_count,"indexed guidance passages"),
    metric(data.metadata.source_version,"historical edition"),metric("NO","PDF verified"),metric("NO","legal rules imported"));
  for(const entry of data.sections){
   const n=el("option","",entry.section+" — "+entry.title.replace(/^3\.\d+\s+SDS\s+SECTION\s+\d+\s+[—:-]?\s*/i,""));
   n.value=entry.section;$("section").appendChild(n);
  }
 } catch(error){$("source").replaceChildren(el("div","empty",error.message));}
 $("searchForm").addEventListener("submit",event=>{event.preventDefault();page=0;search();});
 $("previous").addEventListener("click",()=>{page=Math.max(0,page-limit);search();});
 $("next").addEventListener("click",()=>{if(page+limit<total){page+=limit;search();}});
 await search();
}
document.addEventListener("DOMContentLoaded",start);
