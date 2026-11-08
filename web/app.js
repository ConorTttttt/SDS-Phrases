"use strict";

const FACT_LABELS = {
  inhalation_first_aid_reviewed: "Inhalation first-aid instructions have been medically assessed for this formulation",
  eye_first_aid_reviewed: "Eye-contact first aid has been confirmed as appropriate for this product",
  skin_first_aid_reviewed: "Soap and water are appropriate for the skin-exposure scenario",
  drain_protection_verified: "Release to drains and surface water must be prevented",
  sealed_storage_verified: "Tightly closed containers are safe and appropriate for storage",
  glove_requirements_reviewed: "Chemical-resistant glove selection has been assessed",
  ignition_controls_reviewed: "Ignition source prevention is required and the wording is appropriate"
};
const $ = (id) => document.getElementById(id);
const node = (tag, cls, value) => {
  const element = document.createElement(tag);
  if (cls) element.className = cls;
  if (value !== undefined) element.textContent = value;
  return element;
};
const add = (parent, tag, cls, value) => {
  const child = node(tag, cls, value);
  parent.appendChild(child);
  return child;
};
async function api(url, init) {
  const response = await fetch(url, init);
  let value;
  try { value = await response.json(); }
  catch { throw new Error("Invalid response from the local engine."); }
  if (!response.ok) throw new Error(value.error || "Unable to complete request.");
  return value;
}
function showMessage(target, message) {
  target.replaceChildren(node("div", "empty", message));
}
function initialiseFacts() {
  for (const [id, label] of Object.entries(FACT_LABELS)) {
    const wrapper = node("label", "fact");
    const input = node("input");
    input.type = "checkbox";
    input.dataset.fact = id;
    const caption = node("span", "", label);
    wrapper.append(input, caption);
    $("factList").appendChild(wrapper);
  }
  for (let section = 1; section <= 16; section++) {
    const option = node("option", "", "Section " + section);
    option.value = section;
    $("searchSection").appendChild(option);
  }
}
function phraseCard(record) {
  const item = node("article", "phrase-card");
  const top = add(item, "div", "phrase-top");
  add(top, "strong", "", "SECTION " + (record.sds_section ?? "—") + " · " + record.collection);
  const copy = add(top, "button", "copy", "Copy wording");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(record.english);
      copy.textContent = "Copied";
    } catch { copy.textContent = "Copy unavailable"; }
  });
  add(item, "p", "phrase-text", record.english);
  add(item, "p", "meta", "Structure: " + record.structurecode +
      (record.original_code ? " · Original code: " + record.original_code : "") +
      (record.esdscom_phrase_id ? " · Official phrase ID: " + record.esdscom_phrase_id : "") +
      " · Entry: " + record.entry_key);
  return item;
}
function renderEvaluation(data) {
  const dest = $("evaluationResults");
  const stat = $("evaluationStats");
  dest.replaceChildren();
  stat.replaceChildren();
  const fields = [
    [data.selected.length, "candidate phrases"],
    [data.pending_evidence.length, "evidence checks pending"],
    [data.blocked_matches.length, "blocked mappings"]
  ];
  fields.forEach(([value, title]) => add(stat, "span", "stat", value + " " + title));
  if (!data.selected.length && !data.pending_evidence.length && !data.blocked_matches.length) {
    showMessage(dest, "No pilot rules fired. This does not imply the product has no SDS requirements.");
  }
  for (const match of data.selected) {
    const record = { ...match.catalogue, sds_section: match.section };
    const card = phraseCard(record);
    add(card, "p", "review", "DRAFT — human approval required");
    add(card, "p", "rationale", "Rule " + match.rule_id + " · " + match.rationale);
    add(card, "p", "meta", "Confirmed facts: " + match.verified_facts.join(", ") +
      " · Matched hazards: " + (match.matched_hazards.join(", ") || "fact-driven") +
      " · " + match.rule_reference);
    dest.appendChild(card);
  }
  for (const match of data.pending_evidence) {
    const card = node("article", "phrase-card pending");
    add(card, "strong", "", "SECTION " + match.section + " · " + match.rule_id);
    add(card, "p", "phrase-text", "Requires verified facts: " + match.missing_facts.map(f => FACT_LABELS[f] || f).join("; "));
    add(card, "p", "meta", "Matching classifications: " + match.matched_hazards.join(", ") + ". No phrase has been selected.");
    dest.appendChild(card);
  }
  for (const match of data.blocked_matches) {
    const card = node("article", "phrase-card pending");
    add(card, "strong", "", "BLOCKED · " + match.rule_id);
    add(card, "p", "phrase-text", match.reason);
    add(card, "p", "meta", "Expected structure code: " + match.expected_structurecode);
    dest.appendChild(card);
  }
}
async function runEvaluation(event) {
  event.preventDefault();
  const hazards = $("hazards").value.toUpperCase().split(/[\s,;]+/).map(x => x.trim()).filter(Boolean);
  const facts = {};
  for (const input of document.querySelectorAll("[data-fact]")) facts[input.dataset.fact] = input.checked;
  showMessage($("evaluationResults"), "Evaluating the local rules…");
  try {
    const result = await api("/api/evaluate", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({jurisdiction: $("jurisdiction").value, hazards, facts})
    });
    renderEvaluation(result);
  } catch (error) { showMessage($("evaluationResults"), error.message); }
}
async function runSearch(event) {
  if (event) event.preventDefault();
  const params = new URLSearchParams({
    query: $("searchQuery").value,
    jurisdiction: $("searchJurisdiction").value,
    section: $("searchSection").value,
    collection: $("searchCollection").value,
    limit: "40"
  });
  showMessage($("searchResults"), "Searching the local phrase catalogue…");
  try {
    const data = await api("/api/search?" + params.toString());
    $("searchResults").replaceChildren();
    if (!data.results.length) showMessage($("searchResults"), "No matching catalogue entries. Try a different search or regulatory structure.");
    for (const record of data.results) $("searchResults").appendChild(phraseCard(record));
  } catch (error) { showMessage($("searchResults"), error.message); }
}
function setupTabs() {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".tab")) other.classList.toggle("active", other === tab);
      for (const view of document.querySelectorAll(".view")) view.classList.toggle("active", view.id === tab.dataset.target);
      if (tab.dataset.target === "library" && !$("searchResults").children.length) runSearch();
    });
  }
}
async function start() {
  initialiseFacts();
  setupTabs();
  $("selectionForm").addEventListener("submit", runEvaluation);
  $("searchForm").addEventListener("submit", runSearch);
  $("clearInputs").addEventListener("click", () => {
    $("selectionForm").reset();
    $("evaluationStats").replaceChildren(node("span", "", "Inputs cleared."));
    showMessage($("evaluationResults"), "No phrases selected. Confirm product facts before evaluation.");
  });
  try {
    const info = await api("/api/info");
    $("databaseStatus").textContent = info.catalogue_installed ?
      info.english_entries.toLocaleString() + " local English entries" : "Catalogue not installed";
    if (!info.catalogue_installed) $("databaseStatus").classList.add("error");
  } catch {
    $("databaseStatus").textContent = "Service unavailable";
    $("databaseStatus").classList.add("error");
  }
}
document.addEventListener("DOMContentLoaded", start);
