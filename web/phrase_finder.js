"use strict";
/* Original local wording retrieval. No LLM phrase creation or legal inference. */
const $=id=>document.getElementById(id);
const make=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(txt!==undefined)e.textContent=String(txt);return e;};
const add=(parent,tag,cls,txt)=>{const e=make(tag,cls,txt);parent.append(e);return e;};
const STORAGE="sds_phrase_finder_draft_v1";
let sections=[],currentSection=4,offset=0,total=0,latest=[],draft=[],busy=false;
const phraseKey=r=>r.entry_key;
function message(id,text){$(id).replaceChildren(make("div","empty",text));}
function setCount(text){$("count").textContent=text;}
async function api(path,options){
 const res=await fetch(path,options);
 let payload;
 try{payload=await res.json();}catch{throw Error("Local server returned an unexpected response.");}
 if(!res.ok)throw Error(payload.error||"Request failed");
 return payload;
}
function fromStorage(){
 try{
  const saved=JSON.parse(localStorage.getItem(STORAGE)||"[]");
  if(!Array.isArray(saved))return [];
  const seen=new Set();
  return saved.filter(x=>{
   if(!x || typeof x!=="object" || typeof x.entry_key!=="string" ||
      seen.has(x.entry_key) || typeof x.english!=="string" ||
      !Number.isInteger(x.sds_section) || x.sds_section<1 || x.sds_section>16 ||
      typeof x.text_sha256!=="string" || !/^[0-9a-f]{64}$/.test(x.text_sha256) ||
      typeof x.wording_hash!=="string" || !/^[0-9a-f]{64}$/.test(x.wording_hash) ||
      typeof x.structurecode!=="string" || x.catalogue_version!=="5.5")return false;
   seen.add(x.entry_key);return true;
  }).slice(0,200);
 }catch{return [];}
}
function persist(){
 try{localStorage.setItem(STORAGE,JSON.stringify(draft));}
 catch(err){alert("Browser storage is unavailable. This draft may be lost on refresh: "+err.message);}
}
function sourceName(n){return sections.find(s=>s.section===n)?.title||"Other information";}
function subsectionFor(r){return r.curated_subsection_hint||r.sds_subsection||"";}
function renderSections(){
 const host=$("sectionPills");host.replaceChildren();
 for(const section of sections){
  const b=add(host,"button","section-pill");
  b.type="button";b.dataset.section=String(section.section);
  add(b,"strong","",section.section);
  add(b,"small","",section.curated_candidate_codes+" curated");
  b.title=section.title+" — "+section.total_source_phrases+" EU Core entries";
  b.setAttribute("aria-label","Section "+section.section+": "+section.title);
  b.addEventListener("click",()=>selectSection(section.section));
 }
 markSelected();
}
function markSelected(){
 document.querySelectorAll("[data-section]").forEach(b=>{
  const selected=Number(b.dataset.section)===currentSection;
  b.classList.toggle("active",selected);
  b.setAttribute("aria-pressed",String(selected));
 });
 const section=sections.find(s=>s.section===currentSection);
 $("subsection").replaceChildren();
 const all=make("option","","Entire Section "+currentSection+" — "+(section?.title||""));
 all.value="";$("subsection").append(all);
 for(const sub of section?.subsections||[]){
  const option=make("option","",sub.code+" — "+sub.title);option.value=sub.code;
  $("subsection").append(option);
 }
}
function selectSection(number){
 if(!sections.some(s=>s.section===number))return;
 currentSection=number;offset=0;
 markSelected();search();
}
function params(){
 return new URLSearchParams({
  jurisdiction:$("jurisdiction").value,section:String(currentSection),
  subsection:$("subsection").value,mode:$("mode").value,kind:$("kind").value,
  query:$("query").value,include_flagged:$("flagged").checked?"1":"0",
  limit:"30",offset:String(offset)
 });
}
function sourceRecord(r){
 const box=make("article","record "+(r.curated_rule_id?"curated":"")+
   (r.source_integrity==="blocked_source_mismatch"?" blocked":""));
 const top=add(box,"div","rowtop");
 add(top,"strong","tag",(subsectionFor(r)?subsectionFor(r)+" · ":"")+"Section "+r.sds_section);
 add(top,"span","search-tag",r.curated_rule_id?"Curated source entry":"Catalogue entry");
 add(box,"p","source-wording",r.english);
 if(r.is_fragment)add(box,"p","sentence-note","This is a "+r.phrase_kind+" fragment, not complete SDS narrative.");
 if(r.source_flags.length){
  const flags=add(box,"div","flags");
  for(const f of r.source_flags)add(flags,"span","flag",f.replaceAll("_"," "));
 }
 add(box,"p","meta",r.source_check_explanation);
 if(r.curated_review_note)add(box,"p","meta","Review note: "+r.curated_review_note);
 const actions=add(box,"div","source-actions");
 const selected=draft.some(x=>phraseKey(x)===phraseKey(r));
 const choose=add(actions,"button","add",selected?"Already in draft":"Add exact wording to draft");
 choose.type="button";choose.disabled=selected||!r.selectable_for_draft;
 choose.addEventListener("click",()=>{choosePhrase(r);});
 if(!r.selectable_for_draft)add(box,"p","message","This source cannot be added from this view because integrity or source structure checks failed.");
 const source=add(box,"details","source-detail");
 add(source,"summary","","Full catalogue provenance");
 add(source,"p","meta","Source code: "+r.structurecode+" · catalogue "+r.catalogue_version+
   " · "+r.collection+" · "+r.source_file+" · Excel row "+r.excel_row);
 add(source,"p","meta","Original phrase ID: "+(r.esdscom_phrase_id||"not populated")+
   " · Kind: "+r.grammar+" · Region: "+(r.region||"unspecified"));
 add(source,"p","meta","Entry key: "+r.entry_key+" · SHA-256: "+r.text_sha256+
   " · exact source snapshot index hash: "+r.wording_hash);
 add(source,"p","meta","Source note: "+(r.source||"(none)")+
   " · Info: "+(r.info||"(none)"));
 return box;
}
async function search(){
 if(busy)return;
 busy=true;message("results","Searching original local wording…");
 try{
  const data=await api("/api/phrase-finder/search?"+params().toString());
  latest=data.results;total=data.total;
  setCount(total.toLocaleString()+" matching source entries · showing "+
    (latest.length?offset+1:0)+"–"+Math.min(offset+latest.length,total));
  $("prev").disabled=offset===0;$("next").disabled=offset+30>=total;
  $("resultHelp").textContent=data.warning;
  const host=$("results");host.replaceChildren();
  if(!latest.length)message("results","No source phrases match these filters. Try the full Core library, include flagged records, or change subsection/search terms.");
  else for(const record of latest)host.append(sourceRecord(record));
 }catch(err){latest=[];total=0;setCount("Catalogue unavailable");message("results",err.message);}
 finally{busy=false;}
}
function choosePhrase(r){
 if(draft.length>=200){alert("A maximum of 200 source entries can be saved in this draft.");return;}
 if(draft.some(x=>x.entry_key===r.entry_key))return;
 if(!r.selectable_for_draft)return;
 if(r.requires_manual_completion || r.source_flags.length){
  if(!confirm("This source text is a fragment, contains parameters or has quality flags. It cannot be pasted into a final SDS without manual completion and review. Add it to the draft anyway?"))return;
 }
 draft.push({
  entry_key:r.entry_key,english:r.english,structurecode:r.structurecode,
  sds_section:r.sds_section,subsection:subsectionFor(r),
  source_file:r.source_file,excel_row:r.excel_row,catalogue_version:r.catalogue_version,
  wording_hash:r.wording_hash,text_sha256:r.text_sha256,
  source_integrity:r.source_integrity,grammar:r.grammar,
  requires_manual_completion:r.requires_manual_completion,
  captured_at:new Date().toISOString(),current_source:null,review_status:"unreviewed"
 });
 persist();renderDraft();search();
}
function renderDraft(){
 const host=$("draft");host.replaceChildren();
 $("draftCount").textContent=draft.length+" PHRASES";
 for(const id of ["copyDraft","exportDraft","clearDraft"])$(id).disabled=!draft.length;
 if(!draft.length){message("draft","Click “Add to draft” next to an original phrase.");return;}
 const sorted=[...draft].sort((a,b)=>a.sds_section-b.sds_section||a.entry_key.localeCompare(b.entry_key));
 for(const r of sorted){
  const box=add(host,"article","draft-item");
  const top=add(box,"div","rowtop");
  add(top,"span","draft-title","Section "+r.sds_section+
    (r.subsection?" · "+r.subsection:"")+" · "+sourceName(r.sds_section));
  const remove=add(top,"button","","Remove");remove.type="button";
  remove.addEventListener("click",()=>{draft=draft.filter(x=>x.entry_key!==r.entry_key);persist();renderDraft();if(latest.length)search();});
  add(box,"p","words",r.english);
  add(box,"p","meta","Code: "+r.structurecode+" · "+r.catalogue_version);
  if(r.current_source===false)add(box,"p","message","Source changed or missing: REMOVE / RESELECT before export.");
  else if(r.current_source===null)add(box,"p","meta","Source snapshot not yet rechecked this session.");
  if(r.requires_manual_completion)add(box,"p","sentence-note","Fragment or parameter: must be completed before use.");
 }
}
function draftInputs(){
 return draft.map(x=>({
  entry_key:x.entry_key,structurecode:x.structurecode,sds_section:x.sds_section,
  wording_hash:x.wording_hash,text_sha256:x.text_sha256,
  catalogue_version:x.catalogue_version
 }));
}
async function validateBeforeUse(){
 if(!draft.length)return false;
 try{
  const result=await api("/api/phrase-finder/validate-draft",{
   method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify(draftInputs())
  });
  const checks=new Map(result.results.map(x=>[x.entry_key,x.status==="source_unchanged"]));
  for(const entry of draft)entry.current_source=checks.get(entry.entry_key)===true;
  renderDraft();
  if(!result.all_current){alert("One or more source entries have changed or disappeared. Remove and reselect them before exporting.");return false;}
  return true;
 }catch(err){alert("Cannot verify current source entries: "+err.message);return false;}
}
function draftText(){
 const out=["DRAFT SDS PHRASE SELECTION — UNREVIEWED",
 "Source: original locally imported eSDScom 5.5 Core catalogue.",
 "NOT a legally compliant or complete SDS. Verify each phrase, placeholders and relevant legislative requirements.",
 ""];
 const sectionsSorted=[...new Set(draft.map(x=>x.sds_section))].sort((a,b)=>a-b);
 for(const sec of sectionsSorted){
  out.push("SECTION "+sec+" — "+sourceName(sec));
  for(const record of draft.filter(x=>x.sds_section===sec)){
   out.push("["+record.subsection+" / "+record.structurecode+" / "+record.entry_key+"]");
   out.push(record.english);
   if(record.requires_manual_completion)out.push("[FRAGMENT/PARAMETER REQUIRES COMPLETION]");
   out.push("");
  }
 }
 out.push("END OF UNREVIEWED DRAFT — NO LEGAL APPLICABILITY OR COMPLETENESS APPROVED");
 return out.join("\n");
}
async function copyDraft(){
 if(!await validateBeforeUse())return;
 try{await navigator.clipboard.writeText(draftText());$("copyDraft").textContent="Copied";setTimeout(()=>$("copyDraft").textContent="Copy draft text",2000);}
 catch{alert("Clipboard unavailable; use Export .txt instead.");}
}
async function exportDraft(){
 if(!await validateBeforeUse())return;
 const blob=new Blob([draftText()],{type:"text/plain;charset=utf-8"});
 const u=URL.createObjectURL(blob);
 const a=make("a");a.href=u;a.download="sds-phrase-selection-unreviewed.txt";
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1500);
}
async function refreshDraft(){
 if(!draft.length)return;
 try{
  const result=await api("/api/phrase-finder/validate-draft",{
   method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(draftInputs())
  });
  const checks=new Map(result.results.map(x=>[x.entry_key,x.status==="source_unchanged"]));
  for(const x of draft)x.current_source=checks.get(x.entry_key)===true;
  renderDraft();
 }catch{for(const x of draft)x.current_source=null;renderDraft();}
}
async function start(){
 draft=fromStorage();renderDraft();
 $("finderForm").addEventListener("submit",e=>{e.preventDefault();offset=0;search();});
 for(const id of ["subsection","jurisdiction","mode","kind","flagged"]){
  $(id).addEventListener("change",()=>{
   if(id==="jurisdiction"&&$("jurisdiction").value!=="EU")$("mode").value="catalogue";
   if(id==="mode"&&$("mode").value==="curated")$("jurisdiction").value="EU";
   offset=0;search();
  });
 }
 $("prev").addEventListener("click",()=>{offset=Math.max(0,offset-30);search();});
 $("next").addEventListener("click",()=>{if(offset+30<total){offset+=30;search();}});
 $("copyDraft").addEventListener("click",copyDraft);
 $("exportDraft").addEventListener("click",exportDraft);
 $("clearDraft").addEventListener("click",()=>{
  if(confirm("Clear every phrase from this browser's draft selection?")){draft=[];persist();renderDraft();if(latest.length)search();}
 });
 try{
  const data=await api("/api/phrase-finder/sections");sections=data.sections;
  renderSections();
  const wanted=Number(new URLSearchParams(location.search).get("section"));
  if(Number.isInteger(wanted)&&wanted>=1&&wanted<=16)currentSection=wanted;
  markSelected();await search();
  await refreshDraft();
 }catch(err){message("sectionPills",err.message);message("results","Import or index the local catalogue and reload this page.");}
}
document.addEventListener("DOMContentLoaded",start);
