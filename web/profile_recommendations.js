"use strict";
/* Profile-driven retrieval of unchanged, locally licensed original phrase text. */
const $=id=>document.getElementById(id);
const elem=(tag,cls,value)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(value!==undefined)e.textContent=String(value);return e;};
const add=(parent,tag,cls,value)=>{const e=elem(tag,cls,value);parent.append(e);return e;};
const DRAFT_KEY="sds_phrase_finder_draft_v1";
const CLASS_TEXT={
 reported_property:"Reported property (value fragment)",
 profile_match:"Profile-driven candidate",
 classification_related:"Classification-linked candidate",
 property_related:"Physical-property candidate",
 conditional_safety:"Safety instruction — confirm before use",
 layout_fragment:"Table heading / layout candidate"
};
let latest=null;
function localDay(){
 const d=new Date();return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,10);
}
function getDate(){return $("asOf").value;}
function parseHazards(){
 const list=$("hazards").value.toUpperCase().split(/[\s,;]+/).filter(Boolean);
 const invalid=list.filter(c=>!/^(?:H[2-4][0-9]{2}|EUH[0-9]{3})$/.test(c));
 if(invalid.length)throw Error("Check hazard codes: "+invalid.slice(0,6).join(", ")+". Use Hnnn or EUHnnn.");
 return [...new Set(list)];
}
function optionalNumber(id){
 const input=$(id).value.trim();
 if(!input)return null;
 const value=Number(input);
 if(!Number.isFinite(value))throw Error("Invalid number for "+id);
 return value;
}
function profile(){
 return {
  jurisdiction:"EU",as_of:getDate(),hazards:parseHazards(),
  classification_reference:$("classificationRef").value.trim(),
  product_type:$("productType").value,
  physical_state:$("physicalState").value,
  physical_form:$("physicalForm").value,
  colour:$("colour").value,
  ph:optionalNumber("ph"),flash_point_c:optionalNumber("flashPoint"),
  dust_generating:$("dustGenerating").value,
  volatile:$("volatile").value,
  heat_sensitive:$("heatSensitive").value,
  sunlight_sensitive:$("sunlightSensitive").value,
  heat_pressure_risk:$("heatPressure").value,
  professional_use:$("professionalUse").value,
 };
}
async function api(path,opts){
 const res=await fetch(path,opts);
 const data=await res.json();
 if(!res.ok)throw Error(data.error||"Unable to evaluate the local product profile.");
 return data;
}
function metric(n,title){const e=elem("div","metric");add(e,"b","",n);add(e,"span","",title);return e;}
function setMessage(target,text){$(target).replaceChildren(elem("div","empty",text));}
function appendDraft(item){
 let saved;
 try{saved=JSON.parse(localStorage.getItem(DRAFT_KEY)||"[]");}
 catch{saved=[];}
 if(!Array.isArray(saved))saved=[];
 if(saved.some(x=>x.entry_key===item.source.entry_key)){
  alert("This original phrase is already in your draft. Open the phrase finder to review it.");
  return false;
 }
 if(saved.length>=200){alert("Your current draft already contains 200 phrases.");return false;}
 const ok=confirm(
  "Add the ORIGINAL source wording to your UNREVIEWED draft?\n\n"+
  item.topic+"\n\n"+
  "You must verify product suitability, any fragment/placeholder, and the current SDS requirements before publication."
 );
 if(!ok)return false;
 const r=item.source;
 saved.push({
  entry_key:r.entry_key,english:item.phrase,structurecode:r.structurecode,
  sds_section:item.section,subsection:item.subsection||"",
  source_file:r.source_file,excel_row:r.excel_row,
  catalogue_version:r.catalogue_version,wording_hash:r.wording_hash,
  text_sha256:item.text_sha256,source_integrity:item.source_integrity,
  grammar:r.grammar,requires_manual_completion:item.is_fragment,
  captured_at:new Date().toISOString(),current_source:null,
  review_status:"unreviewed"
 });
 try{localStorage.setItem(DRAFT_KEY,JSON.stringify(saved));}
 catch(err){alert("Browser draft could not be saved: "+err.message);return false;}
 updateDraftLink(saved.length);
 return true;
}
function updateDraftLink(count){
 const label=$("draftLink");
 if(label)label.textContent="Open your draft ("+count+" saved phrases) ↗";
}
function draftCount(){
 try{
  const d=JSON.parse(localStorage.getItem(DRAFT_KEY)||"[]");
  return Array.isArray(d)?d.length:0;
 }catch{return 0;}
}
function card(item){
 const root=elem("article","source-card"+(item.phrase?"":" blocked"));
 const header=add(root,"div","rowtop");
 add(header,"strong","tag",(item.subsection?item.subsection+" · ":"")+item.topic);
 const status=add(header,"span","badge "+(item.kind==="reported_property"?"property":item.kind==="conditional_safety"?"safety":""),CLASS_TEXT[item.kind]||item.kind);
 if(item.phrase){
  add(root,"p","wording",item.phrase);
  if(item.is_fragment)add(root,"p","fragment","SOURCE FRAGMENT — table/list context needed; not a complete SDS sentence.");
 }else{
  add(root,"p","review-note","Source could not be matched exactly in your local catalogue. This phrase has been blocked.");
 }
 add(root,"p","reason","Why shown: "+item.reason);
 add(root,"p","reason","Matched inputs: "+item.matched_inputs.join(" · "));
 if(item.confirmation_required.length){
  const details=add(root,"details","review-requirements");
  add(details,"summary","review-note","Before inserting this phrase:");
  const list=add(details,"ul","review-list");
  for(const text of item.confirmation_required)add(list,"li","",text);
 }
 const actions=add(root,"div","source-actions");
 const button=add(actions,"button","add","Add to draft · review needed");
 button.type="button";button.disabled=!item.phrase;
 button.addEventListener("click",()=>{
  if(appendDraft(item)){button.disabled=true;button.textContent="Saved to draft";}
 });
 const finder=add(actions,"a","","Browse more in Section "+item.section+" ↗");
 finder.href="/phrase_finder.html?section="+item.section;
 const audit=add(root,"details","audit");
 add(audit,"summary","","Original phrase provenance");
 if(item.source){
  add(audit,"p","","eSDScom "+item.source.catalogue_version+" · Core · code "+item.source.structurecode);
  add(audit,"p","","Source file "+item.source.source_file+" · row "+item.source.excel_row+" · "+item.source.entry_key);
  add(audit,"p","","Exact English SHA-256: "+item.text_sha256);
 }
 add(audit,"p","","Legal applicability verified: NO · Phrase approved for SDS: NO · Review status: unreviewed");
 return root;
}
function show(data){
 latest=data;
 const sectionsMatched=data.sections.filter(s=>s.source_matches>0).length;
 const statuses=$("status");
 statuses.replaceChildren(
  metric(data.total_recommended_source_phrases,"matching original phrases"),
  metric(sectionsMatched+"/16","sections with candidates"),
  metric(data.total_blocked_source_mappings,"source mapping blocks"),
  metric("0","legally approved"),
  metric(draftCount(),"phrases in your draft")
 );
 const warning=$("conflicts");warning.replaceChildren();
 if(data.profile_conflicts.length){
  const c=add(warning,"div","warnings");
  add(c,"strong","","Conflicting product information — phrase recommendations blocked");
  for(const msg of data.profile_conflicts)add(c,"p","",msg);
  add(c,"p","","Correct the profile and evaluate again.");
 }
 const host=$("sections");host.replaceChildren();
 if(!data.blocked_due_to_profile_conflict){
  const bar=add(host,"div","draft-nav");
  const link=add(bar,"a","draft-link","");
  link.id="draftLink";link.href="/phrase_finder.html";
  updateDraftLink(draftCount());
 }
 for(const group of data.sections){
  const section=add(host,"details","section-card");
  section.open=group.candidates.length>0&&!data.blocked_due_to_profile_conflict;
  const head=add(section,"summary","section-head");
  add(head,"h3","","Section "+group.section+" — "+group.title);
  add(head,"span","counter",group.source_matches+" phrases");
  const body=add(section,"div","section-body");
  if(!group.candidates.length){
   add(body,"p","section-note","No safe profile-based phrase mapping was triggered for this section. This does not mean the SDS subsection is complete or not applicable.");
  }
  for(const item of group.candidates)body.append(card(item));
  const link=add(body,"a","draft-link","Explore entire Section "+group.section+" library ↗");
  link.href="/phrase_finder.html?section="+group.section;
 }
}
function quickAdd(code){
 const existing=new Set($("hazards").value.toUpperCase().split(/[\s,;]+/).filter(Boolean));
 existing.add(code);$("hazards").value=[...existing].join(", ");
}
function demo(){
 $("profileForm").reset();
 $("asOf").value=localDay();$("hazards").value="H315, H319";
 $("productType").value="mixture";$("physicalState").value="liquid";
 $("colour").value="colourless";$("ph").value="5.2";
 $("classificationRef").value="FICTIONAL demonstration classification only";
 $("volatile").value="unknown";
 setMessage("sections","Fictional example loaded. Click Get recommended SDS phrases.");
}
function reset(){
 $("profileForm").reset();$("asOf").value=localDay();latest=null;
 setMessage("status","Enter a profile above to see suggested original phrases.");
 setMessage("sections","Recommendations will be grouped across all 16 sections.");
 $("conflicts").replaceChildren();
}
async function evaluate(e){
 e.preventDefault();setMessage("sections","Matching your profile to exact local eSDScom source wording…");
 try{
  const data=await api("/api/profile-recommendations/evaluate",{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(profile())
  });
  show(data);$("resultsPanel").scrollIntoView({behavior:"smooth",block:"start"});
 }catch(err){setMessage("sections",err.message);}
}
function main(){
 $("asOf").value=localDay();$("profileForm").addEventListener("submit",evaluate);
 $("demo").addEventListener("click",demo);
 $("reset").addEventListener("click",reset);
 document.querySelectorAll("[data-h]").forEach(b=>b.addEventListener("click",()=>quickAdd(b.dataset.h)));
}
document.addEventListener("DOMContentLoaded",main);
