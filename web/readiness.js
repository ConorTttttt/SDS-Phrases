"use strict";
const $=id=>document.getElementById(id);
const node=(tag,cls,value)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(value!==undefined)el.textContent=String(value);return el;};
const add=(p,tag,cls,v)=>{const c=node(tag,cls,v);p.append(c);return c;};
let cfg=null,answer=null;
function today(){const d=new Date();return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,10);}
async function api(url,options){const response=await fetch(url,options);const value=await response.json();if(!response.ok)throw Error(value.error||"Request failed");return value;}
function metric(v,t){const out=node("div","metric");add(out,"b","",v);add(out,"span","",t);return out;}
function promptCard(item){
 const box=node("article","question");box.dataset.id=item.id;
 add(box,"span","tag",item.id+" · SDS "+item.subsection);
 add(box,"h4","",item.topic);add(box,"p","",item.question);
 const status=add(box,"select","");status.dataset.status=item.id;
 for(const [k,v] of [["unknown","Unknown / not assessed"],["available","Information or assessment available"],["not_available","Information unavailable — reason needed"],["not_applicable","Claim not applicable — reason needed"]]){
  const option=node("option","",v);option.value=k;status.append(option);
 }
 const ref=add(box,"textarea","");ref.dataset.reference=item.id;ref.maxLength=1000;
 ref.placeholder="Evidence reference (report, revision, source, approver)…";
 const reason=add(box,"textarea","");reason.dataset.reason=item.id;reason.maxLength=1000;
 reason.placeholder="Reason for unavailability or non-applicability…";
 add(box,"p","note","Illustrative evidence: "+item.potential_evidence);
 const cite=add(box,"p","source",
   "ECHA printed pp. "+item.source.guidance_pages.join("–")+
   " · Guidance ch. "+item.source.guidance_chapter+
   " · REACH Annex II Part A "+item.source.reach_annex2_part_a_clause_for_review+
   " [legal crosswalk pending audit]");
 cite.title="Guidance locator is a source reference, not a legal approval.";
 return box;
}
function createConfig(data){
 cfg=data;const host=$("questions");host.replaceChildren();
 const titles={4:"First aid measures",7:"Handling and storage",8:"Exposure controls/personal protection"};
 for(const section of data.sections){
  const group=node("section","group");group.dataset.section=section;
  add(group,"h3","","Section "+section+" · "+titles[section]);
  for(const item of data.prompts.filter(r=>r.section===section))group.append(promptCard(item));
  host.append(group);
 }
 applyFocus();
}
function profile(){
 const evidence={};
 for(const select of document.querySelectorAll("[data-status]")){
  const id=select.dataset.status;
  const reference=document.querySelector("[data-reference='"+id+"']").value.trim();
  const reason=document.querySelector("[data-reason='"+id+"']").value.trim();
  evidence[id]={status:select.value,reference,reason};
 }
 return {jurisdiction:"EU",as_of:$("asOf").value,evidence};
}
function applyFocus(){
 const selected=$("focus").value;
 for(const block of document.querySelectorAll(".group[data-section]")){
  block.hidden=selected!=="all" && block.dataset.section!==selected;
 }
 for(const block of document.querySelectorAll(".finding-group[data-section]")){
  block.hidden=selected!=="all" && block.dataset.section!==selected;
 }
}
function show(data){
 answer=data;const totals=data.counts;const count=key=>totals[key]||0;
 $("overview").replaceChildren(metric(data.number_of_prompts,"evidence questions"),
   metric(count("evidence_submitted_for_review"),"documented for review"),
   metric(count("missing_data_reason_for_review")+count("non_applicability_claim_for_review"),"reasons/claims for review"),
   metric(count("information_needed"),"evidence gaps"),metric("NO","regulatory approval"));
 const host=$("findings");host.replaceChildren();
 for(const section of data.sections){
  const box=node("section","group finding-group");box.dataset.section=section.section;
  add(box,"h3","","Section "+section.section+" · Evidence status");
  const unresolved=section.prompts.filter(x=>x.finding==="information_needed");
  add(box,"p","status",unresolved.length+" items need assessment or an evidence reference. No part of this result establishes compliance.");
  for(const item of section.prompts){
   const card=node("article","outcome"+(item.finding==="information_needed"?" missing":""));
   add(card,"h4","",item.subsection+" · "+item.topic);
   const labels={evidence_submitted_for_review:"Evidence submitted for expert review",missing_data_reason_for_review:"Data unavailable — reason requires review",non_applicability_claim_for_review:"Not-applicable claim — requires review",information_needed:"Information/evidence needed"};
   add(card,"p","",labels[item.finding]);add(card,"p","",item.question);
   if(item.evidence_reference)add(card,"p","", "Evidence: "+item.evidence_reference);
   if(item.review_reason)add(card,"p","", "Review reason: "+item.review_reason);
   box.append(card);
  }
  host.append(box);
 }
 applyFocus();
}
function clear(){
 $("readinessForm").reset();answer=null;document.querySelectorAll("[data-reference],[data-reason]").forEach(x=>x.value="");
 $("overview").replaceChildren(node("div","empty","Supply evidence and evaluate to see the gaps."));
 $("findings").replaceChildren();
}
function example(){
 clear();
 for(const [section,status,text] of [[4,"available","FICTIONAL first aid source"],[7,"not_available",""],[8,"not_applicable",""]]){
  const items=cfg.prompts.filter(x=>x.section===section).slice(0,section===4?4:1);
  for(const item of items){
   document.querySelector("[data-status='"+item.id+"']").value=status;
   if(status==="available")document.querySelector("[data-reference='"+item.id+"']").value=text;
   else document.querySelector("[data-reason='"+item.id+"']").value="FICTIONAL explanation for demonstration only; not verified";
  }
 }
}
async function evaluate(e){
 e.preventDefault();
 try{
  const result=await api("/api/readiness/evaluate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(profile())});
  show(result);$("assessment").scrollIntoView({behavior:"smooth"});
 }catch(err){$("overview").replaceChildren(node("div","empty",err.message));}
}
async function start(){
 $("asOf").value=today();
 $("focus").addEventListener("change",applyFocus);
 $("readinessForm").addEventListener("submit",evaluate);
 $("reset").addEventListener("click",clear);
 $("example").addEventListener("click",example);
 try{createConfig(await api("/api/readiness/prompts"));}
 catch(err){$("questions").replaceChildren(node("div","empty",err.message));}
}
document.addEventListener("DOMContentLoaded",start);
