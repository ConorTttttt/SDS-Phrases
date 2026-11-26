import {evaluate} from "./section9-rules.js";
const form=document.querySelector("#profile"), results=document.querySelector("#results"), status=document.querySelector("#status");
form.addEventListener("submit",e=>{
 e.preventDefault(); results.replaceChildren();
 const input=Object.fromEntries(new FormData(form));
 if(!input.state||!input.kind||!input.aerosol){status.textContent="Insufficient evidence: explicit state, product type and aerosol status required.";return;}
 input.aerosol=input.aerosol==="yes";
 status.textContent="Applicability review only; independent regulatory validation pending.";
 for(const r of evaluate(input)){
  const item=document.createElement("article"), title=document.createElement("h3"), p=document.createElement("p");
  title.textContent=r.basis+" — "+r.name+" — "+r.status;
  p.textContent=r.reason+" "+r.guidance; item.append(title,p);results.append(item);
 }
});
