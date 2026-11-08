"use strict";
const $=id=>document.getElementById(id);
const make=(tag,cls,value)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(value!==undefined)x.textContent=String(value);return x;};
const add=(p,tag,cls,value)=>{const x=make(tag,cls,value);p.appendChild(x);return x;};
function msg(id,value){$(id).replaceChildren(make("div","empty",value));}
let currentStructure=null;
async function fetchJson(url,opts){const r=await fetch(url,opts),data=await r.json();if(!r.ok)throw Error(data.error||"Request failed");return data;}
function today(){const d=new Date();return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,10);}
function metric(value,label){const n=make("div","metric");add(n,"b","",value);add(n,"span","",label);return n;}
function headingInput(node){
 const label=make("label","",node.code+" "+node.heading);
 label.style.display="block";label.style.padding="5px 0";label.style.cursor="pointer";label.style.color="#d4e2f2";
 const input=make("input");input.type="checkbox";input.dataset.heading=node.code;
 input.style.width="17px";input.style.height="17px";input.style.marginRight="9px";
 label.prepend(input);return label;
}
function showStructure(structure){
 currentStructure=structure;const headings=$("headings");headings.replaceChildren();
 let count=0;
 for(const sec of structure.sections){
  const card=make("article","record");
  const title=add(card,"h3","",sec.code+" — "+sec.heading);
  title.style.fontSize="15px";title.style.margin="0 0 7px";
  card.append(headingInput(sec));count++;
  for(const sub of sec.subsections){card.append(headingInput(sub));count++;}
  headings.append(card);
 }
 $("stats").replaceChildren(metric(structure.sections.length,"SDS sections"),
  metric(count-structure.sections.length,"prescribed subsection names"),
  metric("2026-06-22","consolidation date"),metric("28","draft content records"),metric("NO","SDS approval"));
}
function showRequirements(pack){
 const panel=$("requirements");panel.replaceChildren();
 for(const rule of pack.items){
  const card=make("article","record"),top=add(card,"div","rowtop");
  add(top,"strong","tag",rule.id+" · "+rule.source_location);
  add(top,"span","kind",rule.modality_category_for_review.replaceAll("_"," "));
  add(card,"p","words",rule.summary_for_review);
  add(card,"p","meta","Printed page(s): "+rule.printed_pages+" · Status: NOT independently verified; not executable");
  const details=add(card,"details","detail");add(details,"summary","","Evidence and limitations");
  add(details,"p","meta","Information needed: "+rule.information_needed);
  add(details,"p","meta","Important qualification: "+rule.exception_or_qualification_warning);
  panel.append(card);
 }
}
function profile(){
 const headings=[...document.querySelectorAll("[data-heading]:checked")].map(x=>x.dataset.heading);
 const blanks=$("blanks").value.split(/[,\s;]+/).map(x=>x.trim()).filter(Boolean);
 return {jurisdiction:"EU",as_of:$("asOf").value,headings,
   product_type:{value:$("productType").value,evidence:$("productEvidence").value.trim()},
   inventory_complete:{value:$("complete").value,evidence:$("inventoryEvidence").value.trim()},
   blank_subsections:blanks};
}
function renderAudit(result){
 const panel=$("auditResults");panel.replaceChildren();
 const totals=make("article","record");
 add(totals,"h3","","Audit summary — NOT a compliance finding");
 const labels=Object.entries(result.counts).map(([k,v])=>k.replaceAll("_"," ")+": "+v).join(" · ");
 add(totals,"p","meta",labels);
 add(totals,"p","meta",result.warning);
 if(result.source_edition_warning)add(totals,"p","message",result.source_edition_warning);
 if(result.unrecognised_heading_codes.length)add(totals,"p","message","Unrecognised: "+result.unrecognised_heading_codes.join(", "));
 panel.append(totals);
 for(const r of result.outcomes){
  if(r.decision==="reported_present"||r.decision==="not_expected_for_product_type")continue;
  const box=make("article","record"),head=add(box,"div","rowtop");
  add(head,"strong","tag",r.code+" — "+r.heading);
  const state=add(head,"span",r.decision==="reported_missing"||r.decision==="reported_blank"?"flag":"chip",r.decision.replaceAll("_"," "));
  add(box,"p","meta",r.explanation+" · Source: "+r.source_location+" (printed p. "+r.printed_source_page+")");
  panel.append(box);
 }
}
function fictional(){
 for(const input of document.querySelectorAll("[data-heading]"))input.checked=input.dataset.heading!=="3.1";
 $("asOf").value=today();$("productType").value="mixture";$("complete").value="yes";
 $("productEvidence").value="FICTIONAL product identity only";
 $("inventoryEvidence").value="FICTIONAL complete heading inventory only";
 $("blanks").value="";
}
function clear(){
 $("auditForm").reset();$("asOf").value=today();
 for(const input of document.querySelectorAll("[data-heading]"))input.checked=false;
 msg("auditResults","Enter or import an SDS heading inventory to begin.");
}
async function submitAudit(event){
 event.preventDefault();msg("auditResults","Checking supplied headings…");
 try {
  const data=await fetchJson("/api/reach/audit",{
   method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify(profile())
  });
  renderAudit(data);
 }catch(error){msg("auditResults",error.message);}
}
async function searchSource(event){
 if(event)event.preventDefault();msg("sourceResults","Searching local PDF pages…");
 const q=new URLSearchParams({query:$("query").value,page:$("page").value,limit:"12"});
 try{
  const r=await fetchJson("/api/reach/source/search?"+q.toString());
  $("sourceResults").replaceChildren();
  if(!r.results.length)return msg("sourceResults","No source pages matched this query.");
  for(const item of r.results){
   const card=make("article","record"),top=add(card,"div","rowtop");
   add(top,"strong","tag","PDF page "+item.pdf_page+" · printed page "+item.printed_page);
   add(top,"span","kind","PDF text / source-only");
   const details=add(card,"details","detail");add(details,"summary","","Read text preview (includes header extraction artefacts)");
   const pre=add(details,"pre","");pre.textContent=item.text_preview;pre.style.whiteSpace="pre-wrap";pre.style.overflowWrap="anywhere";
   add(card,"p","meta",r.notice);$("sourceResults").append(card);
  }
 }catch(error){msg("sourceResults",error.message);}
}
async function start(){
 $("asOf").value=today();
 $("auditForm").addEventListener("submit",submitAudit);
 $("fictional").addEventListener("click",fictional);
 $("clear").addEventListener("click",clear);
 $("sourceSearch").addEventListener("submit",searchSource);
 try {showStructure(await fetchJson("/api/reach/structure"));}
 catch(error){msg("headings",error.message);}
 try{showRequirements(await fetchJson("/api/reach/content-inventory"));}
 catch(error){msg("requirements",error.message);}
 try{
  const info=await fetchJson("/api/reach/source/summary");
  $("sourceInfo").textContent="Local PDF indexed: "+info.page_count+
    " pages · SHA-256 "+info.metadata.source_sha256+". "+
    info.metadata.warning;
 } catch(error){
  $("sourceInfo").textContent="Original PDF not yet imported locally. Run python3 src/reach_annex2_source.py ~/Downloads/'Full REACH_removed.pdf' — "+error.message;
 }
}
document.addEventListener("DOMContentLoaded",start);
