"use strict";
const $=id=>document.getElementById(id);
const elem=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=String(text);return el;};
const add=(el,tag,cls,text)=>{const child=elem(tag,cls,text);el.append(child);return child;};
const FACT_LABELS={"professional_use_confirmed":"The product is confirmed for professional use","eu_clp_hazardous_mixture_confirmed":"Mixture is confirmed hazardous under EU CLP","classification_assessment_approved":"A competent person has approved the CLP classification","ionic_mixture_identity_confirmed":"The product is specifically an ionic mixture","soap_water_skin_first_aid_assessed":"Soap-and-water skin first aid has been assessed","eye_rinsing_first_aid_assessed":"Immediate eye rinsing has been assessed","fresh_air_first_aid_assessed":"Fresh-air first aid has been assessed for inhalation","dry_powder_confirmed_suitable":"Dry extinguishing powder is suitable","scba_for_firefighters_assessed":"SCBA is appropriate for firefighters","dust_generation_during_spill_confirmed":"Dust generation is possible during spill cleanup","spill_containers_verified_suitable":"Closed spill collection containers are compatible","tightly_closed_storage_confirmed_safe":"Tightly closed storage is safe and appropriate","chemical_glove_requirements_assessed":"Chemical protective glove needs have been assessed","colour_colourless_observed":"Product colour has been verified as colourless","heat_and_sunlight_to_avoid_confirmed":"Heat and direct sunlight must be avoided","no_whole_mixture_toxicology_data_verified":"No toxicology data exist for the mixture as a whole (verified)","no_whole_mixture_ecology_data_verified":"No ecology data exist for the mixture as a whole (verified)","packaging_cannot_be_cleaned_confirmed":"Contaminated packaging cannot be properly cleaned","not_dg_all_relevant_modes_verified":"Independent transport review finds product non-DG for all relevant modes","substance_csa_performed_verified":"Supplier conducted a CSA for this substance","substance_csa_not_performed_verified":"Supplier did not conduct a CSA for this substance","revised_sds_changes_marked_with_asterisk":"Revised SDS actually uses * to mark changed data"};
let cfg=null,latestResult=null;
const getFacts=cond=>{
 const [key,value]=Object.entries(cond)[0];
 if(key==="fact_equals")return [value.key];
 if(key==="all"||key==="any")return value.flatMap(getFacts);
 if(key==="not")return getFacts(value);
 return [];
};
function metric(num,name){const el=elem("div","metric");add(el,"b","",num);add(el,"span","",name);return el;}
function notice(id,msg){$(id).replaceChildren(elem("div","empty",msg));}
function today(){const d=new Date();return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,10);}
function sourceLink(section){
 const a=elem("a","","Explore catalogue ↗");a.href="/catalogue.html?jurisdiction=EU&section="+section;return a;
}
function buildFacts(pack){
 const groups=new Map();
 for(const rule of pack.rules){
  if(!groups.has(rule.section))groups.set(rule.section,[]);
  for(const key of getFacts(rule.when)){
   if(!groups.get(rule.section).includes(key))groups.get(rule.section).push(key);
  }
 }
 const host=$("factGroups");host.replaceChildren();
 for(const section of pack.sections){
  const factList=groups.get(section.section)||[];
  if(!factList.length)continue;
  const group=elem("details","fact-group");
  group.dataset.section=String(section.section);
  group.open=section.section===4;
  add(group,"summary","fact-title","Section "+section.section+" — "+section.heading+" · "+factList.length+" checks");
  for(const key of factList){
   const line=elem("div","fact-row");
   add(line,"label","fact-label",FACT_LABELS[key]||key.replaceAll("_"," "));
   const select=add(line,"select");select.dataset.fact=key;
   for(const [v,label] of [["unknown","Unknown"],["yes","Yes"],["no","No"]]){
    const opt=elem("option","",label);opt.value=v;select.append(opt);
   }
   const note=add(line,"input");note.dataset.evidence=key;note.maxLength=1000;
   note.placeholder="Evidence reference or reason…";
   add(line,"span","fact-hint","Selecting Yes/No without a supporting evidence reference remains unknown.");
   group.append(line);
  }
  host.append(group);
 }
}
function evidence(value,text){return {value,evidence:value==="unknown"?"":text.trim()};}
function getProfile(){
 const hazards=$("hazards").value.toUpperCase().split(/[,;\s]+/).filter(Boolean);
 const facts={};
 for(const control of document.querySelectorAll("[data-fact]")){
  const key=control.dataset.fact;
  const note=document.querySelector("[data-evidence='"+key+"']");
  facts[key]=evidence(control.value,note.value);
 }
 return {
  jurisdiction:$("jurisdiction").value,as_of:$("asOf").value,hazards,
  classification_complete:evidence($("complete").value,$("completeEvidence").value),
  attributes:{
    product_type:{value:$("type").value||null,evidence:$("typeEvidence").value.trim()},
    physical_form:{value:$("physicalForm").value||null,evidence:$("physicalEvidence").value.trim()}
  },
  facts
 };
}
function readStatus(status){
 return ({
  draft_candidate:"Draft candidate — review required",
  evidence_required:"Evidence required",
  not_triggered:"Condition not triggered",
  blocked_catalogue_mismatch:"Blocked — catalogue mismatch",
  blocked_conflicting_evidence:"Blocked — conflicting facts",
  outside_jurisdiction:"Outside this EU pilot"
 })[status]||status;
}
function renderSuggestion(rule){
 const klass=rule.decision==="draft_candidate"?"suggestion":
  rule.decision==="evidence_required"?"suggestion pending":
  rule.decision.startsWith("blocked")?"suggestion blocked":"suggestion not-triggered";
 const card=elem("div",klass);
 const top=add(card,"div","rowtop");
 add(top,"strong","tag",(rule.subsection_hint?rule.subsection_hint+" · ":"")+rule.topic);
 add(top,"span","status-badge",readStatus(rule.decision));
 if(rule.phrase){
  add(card,"p","words",rule.phrase);
  const isFragment=rule.source.grammar!=="Sentence";
  if(isFragment)add(card,"p","source-fragment","Table heading/list fragment — requires a complete subsection context before use.");
  const button=add(card,"button","copy",isFragment?"Copy source fragment":"Copy source wording");button.type="button";
  button.addEventListener("click",async()=>{
   try{await navigator.clipboard.writeText(rule.phrase);button.textContent="Copied";}catch{button.textContent="Copy unavailable";}
  });
  add(card,"p","meta source-line","Source code: "+rule.source.structurecode+
   " · "+rule.source.source_file+" · row "+rule.source.excel_row+
   " · catalogue "+rule.source.catalogue_version);
  add(card,"p","meta","Original phrase ID: "+(rule.source.esdscom_phrase_id||"not populated in Core source"));
 }
 add(card,"p","meta",rule.explanation);
 if(rule.missing_information.length)add(card,"p","message","Missing evidence: "+rule.missing_information.join(", "));
 if(rule.matched_hazards.length)add(card,"p","meta","Matched H statements: "+rule.matched_hazards.join(", "));
 add(card,"p","meta",rule.review_note);
 const details=add(card,"details","detail");
 add(details,"summary","","Selection trace / reference");
 const pre=add(details,"pre","");pre.textContent=JSON.stringify({
   authoring_rule:rule.rule_id,source:rule.source_context,
   condition_trace:rule.trace,
   approved_for_sds:rule.approved_for_sds,
   legally_required:rule.legally_required},null,2);
 pre.style.whiteSpace="pre-wrap";pre.style.overflowWrap="anywhere";
 return card;
}
function showResult(data){
 latestResult=data;
 const focus=$("focusSection").value;
 const statusFilter=$("resultFilter").value;
 $("status").replaceChildren(
  metric(data.counts.draft_candidate,"draft candidates"),
  metric(data.counts.evidence_required,"evidence checks"),
  metric(data.counts.not_triggered,"untriggered"),
  metric(data.counts.blocked_catalogue_mismatch+data.counts.blocked_conflicting_evidence,"blocked mappings"),
  metric("0","approved SDS phrases"));
 const host=$("sections");host.replaceChildren();
 for(const section of data.sections){
  if(focus!=="all" && focus!==String(section.section))continue;
  const card=elem("details","section-card");card.open=section.counts.draft_candidate>0;
  const head=add(card,"summary","section-head");
  add(head,"h3","","Section "+section.section+" · "+section.heading);
  add(head,"span","section-badge",section.counts.draft_candidate+" drafts · "+section.counts.evidence_required+" evidence checks");
  const body=add(card,"div","section-body");
  body.append(sourceLink(section.section));
  add(body,"p","scope-warning",section.counts.draft_candidate+" draft suggestions · "+
    section.counts.evidence_required+" evidence gaps · "+section.counts.blocked_catalogue_mismatch+" catalogue blocks. Not a completeness result.");
  const sorted=[...section.recommendations].sort((a,b)=>(
   ["draft_candidate","blocked_conflicting_evidence","blocked_catalogue_mismatch","evidence_required","not_triggered","outside_jurisdiction"]
    .indexOf(a.decision)-["draft_candidate","blocked_conflicting_evidence","blocked_catalogue_mismatch","evidence_required","not_triggered","outside_jurisdiction"]
    .indexOf(b.decision)
  ));
  let visible=0;
  for(const rule of sorted){
   if(statusFilter==="blocked" && !rule.decision.startsWith("blocked"))continue;
   if(statusFilter!=="all" && statusFilter!=="blocked" && rule.decision!==statusFilter)continue;
   body.append(renderSuggestion(rule));visible++;
  }
  if(!visible)add(body,"p","empty-state","No matching decisions in this section. This is not a completeness finding.");
  host.append(card);
 }
}
async function api(url,opts){
 const response=await fetch(url,opts),data=await response.json();
 if(!response.ok)throw Error(data.error||"Recommendation service unavailable");
 return data;
}
async function evaluate(event){
 event.preventDefault();notice("sections","Evaluating evidence and checking exact source wording…");
 try{
  const data=await api("/api/section-recommendations/evaluate",{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(getProfile())});
  showResult(data);
  $("resultsPanel").scrollIntoView({behavior:"smooth",block:"start"});
 }catch(error){notice("sections",error.message);}
}
function clear(){
 $("form").reset();$("asOf").value=today();
 $("resultFilter").value="all";$("focusSection").value="all";
 document.querySelectorAll(".fact-group").forEach(group=>{group.hidden=false;group.open=group.dataset.section==="4";});
 latestResult=null;
 document.querySelectorAll("[data-fact]").forEach(x=>x.value="unknown");
 document.querySelectorAll("[data-evidence]").forEach(x=>x.value="");
 notice("sections","Enter product facts and evaluate to see results for each SDS section.");
}
function demo(){
 clear();$("hazards").value="H315, H319";$("type").value="mixture";
 $("physicalForm").value="liquid";$("physicalEvidence").value="FICTIONAL property source";
 $("typeEvidence").value="FICTIONAL formulation profile";
 $("complete").value="yes";$("completeEvidence").value="FICTIONAL reviewed classification";
 for(const key of [
  "professional_use_confirmed","eu_clp_hazardous_mixture_confirmed",
  "classification_assessment_approved","soap_water_skin_first_aid_assessed",
  "eye_rinsing_first_aid_assessed","dry_powder_confirmed_suitable",
  "spill_containers_verified_suitable","tightly_closed_storage_confirmed_safe",
  "chemical_glove_requirements_assessed","colour_colourless_observed",
  "heat_and_sunlight_to_avoid_confirmed","packaging_cannot_be_cleaned_confirmed",
  "revised_sds_changes_marked_with_asterisk",
  "physical_state_liquid_verified","drain_covering_in_spill_plan_confirmed",
  "chemical_splash_goggles_assessed","storage_area_ventilation_verified",
  "h315_label_wording_confirmed","h319_label_wording_confirmed"
 ]){
  const input=document.querySelector("[data-fact='"+key+"']");
  const note=document.querySelector("[data-evidence='"+key+"']");
  if(input&&note){input.value="yes";note.value="FICTIONAL assessment — demonstration only";}
 }
}
async function start(){
 $("asOf").value=today();
 $("form").addEventListener("submit",evaluate);
 $("clear").addEventListener("click",clear);
 $("demo").addEventListener("click",demo);
 try{
  cfg=await api("/api/section-recommendations/config");
  buildFacts(cfg);
  for(const section of cfg.sections){
   const option=elem("option","",section.section+" — "+section.heading);
   option.value=String(section.section);$("focusSection").append(option);
  }
  $("focusSection").addEventListener("change",()=>{
   const focus=$("focusSection").value;
   document.querySelectorAll(".fact-group").forEach(group=>{
     const match=focus==="all"||group.dataset.section===focus;
     group.hidden=!match;if(focus!=="all"&&match)group.open=true;
   });
   if(latestResult)showResult(latestResult);
  });
  $("resultFilter").addEventListener("change",()=>{if(latestResult)showResult(latestResult);});
 }catch(error){notice("factGroups",error.message);}
}
document.addEventListener("DOMContentLoaded",start);
