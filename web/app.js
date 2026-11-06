const $ = (id) => document.getElementById(id);
const activeStates = new Set(["CREATED", "INTAKE_RUNNING", "VERIFY_RUNNING", "AWAITING_APPROVAL", "ACTION_RUNNING"]);
let currentCase = null;
let polling = false;
let busy = false;
let toastTimer;

function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = String(text);
  if (className) el.className = className;
  return el;
}
function clear(el) { el.replaceChildren(); }
function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.style.display = "none"; }, 4000);
}
function setBusy(value) {
  busy = value;
  $("run-case").disabled = value;
  $("approve").disabled = value || !$("reviewed").checked;
  $("reject").disabled = value;
}
async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let data;
  try { data = await response.json(); } catch { throw new Error("Réponse serveur illisible"); }
  if (!response.ok) throw new Error(data.error || `Erreur HTTP ${response.status}`);
  return data;
}
function activeCase(caseData) {
  currentCase = caseData.case_id;
  renderCase(caseData);
  if (activeStates.has(caseData.state) && !polling) pollCase(caseData.case_id);
}
async function pollCase(id, stopAtApproval = false) {
  if (polling) return;
  polling = true;
  let resumeAfterApproval = false;
  try {
    while (currentCase === id) {
      const data = await request(`/api/cases/${encodeURIComponent(id)}`);
      renderCase(data);
      if (data.state === "AWAITING_APPROVAL" && stopAtApproval) {
        resumeAfterApproval = true;
        break;
      }
      if (!activeStates.has(data.state)) break;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } catch (error) {
    toast(error.message);
  } finally {
    polling = false;
    if (resumeAfterApproval && currentCase === id) setTimeout(() => pollCase(id), 1000);
  }
}
function renderProgress(state) {
  const steps = [
    ["Intake", ["CREATED", "INTAKE_RUNNING"], ["VERIFY_RUNNING", "AWAITING_APPROVAL", "ACTION_RUNNING", "DONE", "REJECTED"]],
    ["Verify", ["VERIFY_RUNNING"], ["AWAITING_APPROVAL", "ACTION_RUNNING", "DONE", "REJECTED"]],
    ["Approve", ["AWAITING_APPROVAL"], ["ACTION_RUNNING", "DONE"]],
    ["Action", ["ACTION_RUNNING"], ["DONE"]],
  ];
  clear($("progress"));
  for (const [originalLabel, active, complete] of steps) {
    const label = state === "REJECTED" && originalLabel === "Approve" ? "Rejected" : originalLabel;
    const li = node("li");
    const status = complete.includes(state) ? "complete" : active.includes(state) ? "active" : "";
    if (status) li.classList.add(status);
    if (state === "REJECTED" && originalLabel === "Approve") li.classList.add("failed");
    const icon = status === "complete" ? "✓" : status === "active" ? "●" : "○";
    li.append(node("span", icon, "step-icon"), node("span", label));
    $("progress").append(li);
  }
}
function renderFindings(findings) {
  const root = $("findings");
  clear(root);
  if (!findings || !findings.findings.length) {
    root.append(node("p", "No issues found", "muted"));
    return;
  }
  const rank = { error: 0, warning: 1, info: 2 };
  const icons = { error: "✖", warning: "⚠", info: "ℹ" };
  for (const item of [...findings.findings].sort((a, b) => rank[a.severity] - rank[b.severity])) {
    const card = node("article", undefined, `finding ${item.severity}`);
    card.append(node("h3", `${icons[item.severity]} ${item.severity.toUpperCase()} · ${item.rule} — ${item.message}`, "severity"));
    for (const evidence of item.evidence || []) {
      card.append(node("p", `${evidence.doc_id} · ${evidence.field} · ${evidence.value ?? "—"} · “${evidence.quote}”`));
    }
    if (item.suggested_action) card.append(node("p", `Action suggérée : ${item.suggested_action}`));
    root.append(card);
  }
}
function renderDrafts(artifacts) {
  const root = $("results");
  clear(root);
  if (!artifacts) {
    root.append(node("p", "Aucun brouillon pour le moment.", "muted"));
    return;
  }
  const email = node("article", undefined, "draft");
  const head = node("div", undefined, "draft-head");
  head.append(node("span", "EMAIL · DRAFT", "draft-label"));
  const copy = node("button", "Copy", "secondary");
  copy.type = "button";
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(`${artifacts.email.subject}\n\n${artifacts.email.body_fr}`);
      toast("Brouillon copié");
    } catch (error) { toast(`Copie impossible : ${error.message}`); }
  });
  head.append(copy);
  email.append(head, node("h3", artifacts.email.subject), node("p", artifacts.email.body_fr));
  root.append(email);
  const form = node("article", undefined, "draft");
  form.append(node("span", "FORMULAIRE · DRAFT", "draft-label"));
  const table = node("table");
  const body = node("tbody");
  for (const [key, value] of Object.entries(artifacts.form || {})) {
    const row = node("tr");
    row.append(node("th", key), node("td", typeof value === "object" ? JSON.stringify(value) : value ?? "—"));
    body.append(row);
  }
  table.append(body);
  form.append(table);
  root.append(form);
  const notes = node("article", undefined, "draft");
  notes.append(node("span", "NOTES AU PERSONNEL · DRAFT", "draft-label"));
  const list = node("ul");
  for (const note of artifacts.notes_for_staff || []) list.append(node("li", note));
  notes.append(list);
  root.append(notes);
}
function renderCase(data) {
  $("case-state").textContent = data.state;
  renderProgress(data.state);
  renderFindings(data.findings);
  renderDrafts(data.artifacts);
  $("approval").classList.toggle("hidden", data.state !== "AWAITING_APPROVAL");
  if (data.state === "REJECTED") {
    const message = node("p", "Rejected by reviewer. No action taken.");
    $("results").prepend(message);
  }
  if (data.state === "FAILED") {
    const error = node("p", data.error || "Pipeline failed.", "error-box");
    $("results").prepend(error);
  }
}
async function refreshAudit() {
  const data = await request("/api/audit");
  $("audit-summary").textContent = `Runs used ${data.summary.runs_used} of ${data.summary.runs_cap}, cache hits ${data.summary.cache_hits}`;
  const body = $("audit-body");
  clear(body);
  for (const event of [...data.events].reverse()) {
    const row = node("tr");
    const details = Object.entries(event).filter(([key]) => !["timestamp", "type", "case_id"].includes(key))
      .map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join(" · ");
    row.append(node("td", new Date(event.timestamp).toLocaleTimeString()),
      node("td", event.type), node("td", event.case_id || "—"), node("td", details));
    body.append(row);
  }
}
async function refreshEval() {
  const data = await request("/api/eval/latest");
  const root = $("eval-content");
  clear(root);
  if (data.status === "idle") {
    $("eval-disclaimer").textContent = "No evaluation has been run yet.";
    return;
  }
  $("eval-disclaimer").textContent = `Measured on ${data.n_cases} synthetic cases, indicative only`;
  const table = node("table");
  const head = node("thead");
  const header = node("tr");
  for (const label of ["Variant", "Field accuracy", "Recall", "False positives", "Runs", "Avg latency"]) header.append(node("th", label));
  head.append(header);
  const body = node("tbody");
  for (const item of data.variants || []) {
    const row = node("tr");
    for (const value of [item.variant, `${(item.field_accuracy * 100).toFixed(1)}%`,
      `${(item.recall * 100).toFixed(1)}%`, item.false_positives, item.runs,
      `${Number(item.avg_latency_s).toFixed(2)}s`]) row.append(node("td", value));
    body.append(row);
  }
  table.append(head, body);
  root.append(table);
}
async function init() {
  try {
    const data = await request("/api/demo-cases");
    const select = $("demo-case");
    for (const id of data.demo_cases) {
      const option = node("option", id);
      option.value = id;
      select.append(option);
    }
    $("run-case").disabled = data.demo_cases.length === 0;
    await Promise.all([refreshAudit(), refreshEval()]);
  } catch (error) { toast(error.message); }
}
$("run-case").addEventListener("click", async () => {
  $("reviewed").checked = false;
  setBusy(true);
  try {
    const data = await request("/api/cases", {
      method: "POST", body: JSON.stringify({ demo_case_id: $("demo-case").value }),
    });
    currentCase = data.case_id;
    await pollCase(data.case_id, true);
  } catch (error) { toast(error.message); }
  finally { setBusy(false); }
});
$("reviewed").addEventListener("change", () => { $("approve").disabled = busy || !$("reviewed").checked; });
$("approve").addEventListener("click", async () => {
  if (!currentCase) return;
  setBusy(true);
  try {
    await request(`/api/cases/${encodeURIComponent(currentCase)}/approve`, {
      method: "POST", body: JSON.stringify({ reviewed: true }),
    });
    $("reviewed").checked = false;
    await pollCase(currentCase);
  } catch (error) { toast(error.message); }
  finally { setBusy(false); }
});
$("reject").addEventListener("click", async () => {
  if (!currentCase) return;
  setBusy(true);
  try {
    await request(`/api/cases/${encodeURIComponent(currentCase)}/reject`, { method: "POST" });
    await pollCase(currentCase);
  } catch (error) { toast(error.message); }
  finally { setBusy(false); }
});
setInterval(() => {
  refreshAudit().catch((error) => toast(error.message));
  refreshEval().catch((error) => toast(error.message));
}, 5000);
init();
