"use strict";
const $=id=>document.getElementById(id);
const parse=id=>JSON.parse($(id).value);
const show=(id,x)=>$(id).textContent=typeof x==="string"?x:JSON.stringify(x,null,2);
let report=null, schema=null;
const api=async(action,p={})=>{
 const res=await fetch("/api/authoring/"+action,{method:"POST",headers:{"Content-Type":"application/json","X-SDS-Local-Review":"1"},body:JSON.stringify(p)});
 const obj=await res.json(); if(!res.ok)throw Error(obj.error); return obj;
};
const bind=(id,fn)=>$(id).onclick=async()=>{try{await fn()}catch(e){show("status",e.message)}};
const split=id=>$(id).value.split(",").map(x=>x.trim()).filter(Boolean);
function options(id,arr){$(id).replaceChildren(...arr.map(([v,t])=>{const o=document.createElement("option");o.value=v;o.textContent=t;return o}))}
function render(){
 if(!report)return;
 const p=report.products.find(p=>p.product===$("product").value);
 const r=p?.rows.find(r=>r.code===$("section").value);
 $("view").replaceChildren();
 if(!r)return;
 for(const [title,value] of [["Applicable requirements / assessment findings",r.requirements],["Required product information",r.required_domains],["Available evidence",r.evidence],["Approved phrases",r.approved_candidates],["Unapproved recommendation candidates",r.candidates],["Missing evidence",r.missing_domains],["Draft blocks",r.draft],["Adequacy / coverage", [r.adequacy,r.coverage,r.invalid_blocks,p.conflicts,p.errors]]]){
   const d=document.createElement("details");d.open=true;const s=document.createElement("summary");s.textContent=title;const pre=document.createElement("pre");pre.textContent=JSON.stringify(value,null,2);d.append(s,pre);$("view").append(d);
 }
 for(const b of r.draft){const btn=document.createElement("button");btn.textContent="Edit "+b.id;btn.onclick=()=>{for(const [id,value] of Object.entries({blockid:b.id,kind:b.kind,targets:b.products.join(","),wording:b.wording,aid:b.approval_id||"",av:b.approval_version||"",legal:b.legal_code||"",domains:(b.domains||[]).join(","),reviewer:b.reviewer||"",reason:b.reason||""}))$(id).value=value};$("view").append(btn)}
}
async function revalidate(){
 const product=$("product").value,code=$("section").value;
 report=await api("evaluate",{dossier:parse("dossier")});
 options("product",report.products.map(p=>[p.product,p.product]));
 if(report.products.some(p=>p.product===product))$("product").value=product;
 options("section",Object.entries(schema.headings));
 if(code)$("section").value=code;
 render();show("status",{fingerprint:report.fingerprint,grouping:report.grouping});
}
$("product").onchange=render;$("section").onchange=render;
bind("evaluate",revalidate);
for(const status of ["pending","approved","rejected"])bind(status,async()=>{
 const d=parse("dossier"),id=$("blockid").value||crypto.randomUUID();
 const b={id,code:$("section").value,products:split("targets"),wording:$("wording").value,kind:$("kind").value,status,
 approval_id:$("aid").value,approval_version:Number($("av").value),legal_code:$("legal").value,domains:split("domains"),reviewer:$("reviewer").value,reason:$("reason").value};
 d.content=(d.content||[]).filter(x=>x.id!==id);d.content.push(b);$("dossier").value=JSON.stringify(d,null,2);await revalidate();
});
const caseId=()=>$("case").value, version=()=>Number($("version").value);
bind("save",async()=>{const r=await api("save",{case_id:caseId(),expected_version:version(),dossier:parse("dossier"),reviews:parse("reviews")});$("version").value=r.version;show("status",{revision:r.version,status:r.status,blockers:r.blockers})});
bind("history",async()=>{const h=await api("history",{case_id:caseId()});if(h.length){const r=h.at(-1);$("dossier").value=JSON.stringify(r.dossier,null,2);$("reviews").value=JSON.stringify(r.reviews,null,2);$("version").value=r.version;await revalidate()}show("status",h.map(r=>({version:r.version,saved_at:r.saved_at,status:r.status})))});
bind("compare",async()=>show("status",(await api("compare",{case_id:caseId(),left:Number($("left").value),right:Number($("right").value)})).diff));
bind("search",async()=>show("results",await api("catalogue",{query:$("query").value,section:$("section").value.split(".")[0]})));
bind("approve",async()=>{show("results",await api("approve-phrase",{phrase:parse("phrase")}));await revalidate()});
bind("list",async()=>show("results",await api("phrases")));
bind("export",async()=>{const r=await api("export",{case_id:caseId(),version:version(),format:$("fmt").value});const bytes=Uint8Array.from(atob(r.base64),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes]));const a=document.createElement("a");a.href=url;a.download="SDS-DRAFT."+r.format;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
(async()=>{try{schema=await api("schema");$("dossier").value=JSON.stringify({products:[{id:"product-1",kind:"unknown",jurisdiction:"EU",language:"en",as_of:new Date().toISOString().slice(0,10),sources:{},data:{},profile:{},regulatory_input:{},readiness:{}}],content:[]},null,2);options("section",Object.entries(schema.headings));$("phrase").value=JSON.stringify({kind:"catalogue",entry_key:"",wording:"",subsection:"7.1",status:"pending",jurisdiction:"EU",language:"en",conditions:{},reviewer:"",reason:""},null,2);await revalidate()}catch(e){show("status",e.message)}})();
