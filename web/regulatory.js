"use strict";
const $=id=>document.getElementById(id);
function element(tag,className,text){const x=document.createElement(tag);if(className)x.className=className;if(text!==undefined)x.textContent=String(text);return x;}
function append(parent,tag,className,text){const x=element(tag,className,text);parent.appendChild(x);return x;}
function show(parent,message){parent.replaceChildren(element("div","empty",message));}
function metric(number,label){const n=element("div","metric");append(n,"b","",number);append(n,"span","",label);return n;}
function evidence(value){
 const note=$("factEvidence").value.trim();
 return {value,evidence:value==="unknown"?"":note};
}
function profile(){
 const codes=$("hazards").value.toUpperCase().split(/[,;\s]+/).map(x=>x.trim()).filter(Boolean);
 const completeness=$("complete").value;
 const rawForm=$("form").value;
 return {
  jurisdiction:$("jurisdiction").value, as_of:$("asOf").value,
  hazards:codes,
  classification_complete:{value:completeness,evidence:completeness==="unknown"?"":$("completeEvidence").value.trim()},
  facts:{
   skin_contact_possible:evidence($("skin").value),
   eye_contact_possible:evidence($("eye").value),
   storage_information_assessed:evidence($("storage").value)
  },
  attributes:{
   physical_form:{value:rawForm||null,evidence:rawForm?$("factEvidence").value.trim():""}
  }
 };
}
async function api(path,options){const res=await fetch(path,options),data=await res.json();if(!res.ok)throw Error(data.error||"Local evaluation failed");return data;}
function render(result){
 const dec=$("decisions");dec.replaceChildren();
 for(const rule of result.decisions){
  const card=element("article","record");const top=append(card,"div","rowtop");
  append(top,"strong","tag",rule.section+" · "+rule.rule_id);
  append(top,"span","kind",rule.decision.replaceAll("_"," "));
  append(card,"p","words",rule.title);
  append(card,"p","meta",rule.explanation);
  append(card,"p","meta","Jurisdiction: "+rule.jurisdiction+" · Rule reviewed: "+rule.review_status+
   " · Document: "+rule.regulatory_source.instrument+" / "+rule.regulatory_source.document_version);
  append(card,"p","meta","Reference: "+rule.regulatory_source.reference+
   " · Effective: "+rule.effective_from+" to "+(rule.effective_until||"open"));
  if(rule.matched_hazards.length)append(card,"span","chip","Matched: "+rule.matched_hazards.join(", "));
  if(rule.missing_information.length)append(card,"span","flag","Unknown: "+rule.missing_information.join(", "));
  const detail=append(card,"details","detail");append(detail,"summary","","Inspect condition evaluation trace");
  const pre=append(detail,"pre","");pre.style.whiteSpace="pre-wrap";pre.style.wordBreak="break-word";
  pre.textContent=JSON.stringify(rule.trace,null,2);
  dec.appendChild(card);
 }
 if(!result.decisions.length)show(dec,"This pack has no rules. No compliance conclusion can be drawn.");
 const counts={};
 for(const r of result.decisions)counts[r.decision]=(counts[r.decision]||0)+1;
 $("metrics").replaceChildren(
   metric(result.decisions.length,"rules evaluated"),
   metric(counts.candidate_unverified||0,"unverified candidates"),
   metric(counts.information_required||0,"information required"),
   metric(counts.not_triggered_unverified||0,"draft non-triggers"),
   metric("0","legally approved SDS sections")
 );
 const area=$("coverage");area.replaceChildren();
 for(const sec of result.coverage){
   const row=element("div","record");
   const top=append(row,"div","rowtop");
   append(top,"strong","tag","Section "+sec.section);
   append(top,"span","kind",sec.coverage_status.replaceAll("_"," "));
   append(row,"p","meta",sec.rules_in_pack+" scoped rule(s) in demo pack. SDS completeness: NOT ESTABLISHED.");
   area.appendChild(row);
 }
}
function today(){const now=new Date(),d=new Date(now.getTime()-now.getTimezoneOffset()*60000);return d.toISOString().slice(0,10);}
function clear(){
 $("product").reset();$("asOf").value=today();
 show($("decisions"),"Enter product information and evaluate the rules.");
 show($("coverage"),"Coverage shown after evaluation.");
 $("metrics").replaceChildren(element("div","empty","No evaluation yet."));
}
function loadDemo(){
 clear();$("hazards").value="H315, H319";$("complete").value="yes";
 $("completeEvidence").value="Fictional test classification — not for actual SDS use";
 $("skin").value="yes";$("eye").value="yes";$("storage").value="yes";$("form").value="liquid";
 $("factEvidence").value="Synthetic test evidence — not a real product assessment";
}
async function evaluate(event){
 event.preventDefault();show($("decisions"),"Evaluating rules locally…");
 try{
  const answer=await api("/api/regulatory/evaluate",{method:"POST",
     headers:{"Content-Type":"application/json"},body:JSON.stringify(profile())});
  render(answer);
 } catch(error){show($("decisions"),error.message);}
}
document.addEventListener("DOMContentLoaded",()=>{
 $("asOf").value=today();
 $("product").addEventListener("submit",evaluate);
 $("demo").addEventListener("click",loadDemo);
 $("clear").addEventListener("click",clear);
});
