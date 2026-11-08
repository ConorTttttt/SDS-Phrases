"use strict";
const $=id=>document.getElementById(id);
const make=(tag,cls,value)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(value!==undefined)n.textContent=String(value);return n;};
const add=(parent,tag,cls,value)=>{const n=make(tag,cls,value);parent.appendChild(n);return n;};
let offset=0,limit=40,total=0;
async function api(url,options){const r=await fetch(url,options);const j=await r.json();if(!r.ok)throw Error(j.error||"Local catalogue request failed");return j;}
function message(value){$("records").replaceChildren(make("div","empty",value));}
function metric(value,title){const n=make("div","metric");add(n,"b","",Number(value||0).toLocaleString());add(n,"span","",title);return n;}
function summary(info){
  $("summary").replaceChildren(
    metric(info.records,"catalogue rows"),metric(info.wording_groups,"wording groups"),
    metric(info.repeated_rows,"rows sharing wording"),metric(info.subsection_mapped,"subsection-mapped rows"),
    metric(info.quality_flag_counts.non_sds_structure,"special structures"));
  for(const s of info.sections){const n=make("option","",s.sds_section+" · "+s.title);n.value=s.sds_section;$("s").appendChild(n);}
}
function metadata(parent,label,value){
  if(value!==null&&value!==undefined&&value!=="")add(parent,"p","meta",label+": "+value);
}
function record(item){
 const card=make("article","record"),top=add(card,"div","rowtop");
 add(top,"strong","tag",(item.sds_subsection||"SECTION "+(item.sds_section??"—"))+" · "+item.category);
 add(top,"span","kind",item.phrase_kind+" · "+item.collection);
 add(card,"p","words",item.english||"[No English wording in catalogue]");
 metadata(card,"Source",item.source_file+" · Excel row "+item.excel_row+" · catalogue "+item.catalogue_version);
 metadata(card,"Structure code",item.structurecode);
 metadata(card,"Original code",item.original_code);
 metadata(card,"Official eSDScom phrase ID (if provided)",item.esdscom_phrase_id);
 metadata(card,"Phrase owner",item.phrase_owner);
 metadata(card,"Region",item.region);
 metadata(card,"Catalogued revision date (not legal effective date)",item.revision_date_iso||item.revision_date_raw);
 metadata(card,"Inferred subsection topic",item.sds_topic);
 const chips=add(card,"div","");
 if(item.duplicate_count>1)add(chips,"span","chip",item.duplicate_count+" matching wordings / "+item.duplicate_contexts+" structure contexts");
 for(const flag of item.quality_flags)add(chips,"span","flag",flag.replaceAll("_"," "));
 if(item.review_stale)add(chips,"span","flag","Prior review stale (source wording changed)");
 if(item.info||item.source||item.qualifier){
   const more=add(card,"details","detail");add(more,"summary","","Additional source metadata");
   metadata(more,"Source reference",item.source);metadata(more,"Information",item.info);metadata(more,"Qualifier",item.qualifier);
 }
 const review=add(card,"div","review"),statusLabel=add(review,"label","","Metadata review");
 const select=add(statusLabel,"select");
 for(const pair of [["unreviewed","Unreviewed"],["metadata_checked","Metadata checked"],["needs_attention","Needs attention"]]){
   const option=make("option","",pair[1]);option.value=pair[0];select.appendChild(option);
 }
 select.value=item.review_status||"unreviewed";
 const noteLabel=add(review,"label","","Local note"),note=add(noteLabel,"input");
 note.maxLength=1000;note.value=item.review_note||"";note.placeholder="Reason or source check…";
 const save=add(review,"button","","Save"),msg=add(card,"div","message");
 save.type="button";
 save.addEventListener("click",async()=>{
  save.disabled=true;msg.textContent="Saving…";
  try {
   const output=await api("/api/catalogue/review",{
     method:"POST",headers:{"Content-Type":"application/json","X-SDS-Local-Review":"1"},
     body:JSON.stringify({entry_key:item.entry_key,wording_hash:item.wording_hash,status:select.value,note:note.value})
   });
   item.review_status=output.review_status;item.review_note=output.review_note;item.review_stale=false;
   msg.textContent="Saved locally. This is not regulatory approval.";
  } catch(error){msg.textContent=error.message;}
  finally{save.disabled=false;}
 });
 return card;
}
async function search(){
 const qs=new URLSearchParams({
   query:$("q").value,jurisdiction:$("j").value,collection:$("c").value,
   section:$("s").value,subsection:$("sub").value,kind:$("kind").value,
   duplicates:$("dupes").value,quality:$("quality").value,limit:String(limit),offset:String(offset)
 });
 message("Searching local catalogue…");
 try{
  const output=await api("/api/catalogue/search?"+qs.toString());
  total=output.total;
  $("resultCount").textContent=total.toLocaleString()+" matching rows · showing "+
    (output.results.length?offset+1:0)+"–"+Math.min(offset+output.results.length,total);
  $("prev").disabled=offset===0;$("next").disabled=offset+limit>=total;
  $("records").replaceChildren(...output.results.map(record));
  if(!output.results.length)message("No matching source entries. Clear filters or choose another structure.");
 }catch(error){message(error.message);}
}
async function start(){
 try{summary(await api("/api/catalogue/summary"));}
 catch(error){$("summary").replaceChildren(make("div","empty",error.message));}
 $("filters").addEventListener("submit",e=>{e.preventDefault();offset=0;search();});
 $("prev").addEventListener("click",()=>{offset=Math.max(0,offset-limit);search();});
 $("next").addEventListener("click",()=>{if(offset+limit<total){offset+=limit;search();}});
 await search();
}
document.addEventListener("DOMContentLoaded",start);
