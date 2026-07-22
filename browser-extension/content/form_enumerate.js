// browser-extension/content/form_enumerate.js
// Read-only enumeration of a live application form. No writing (sub-project 3).
// Loaded as a plain content script alongside injector.js — enumerateForm()/labelFor()
// become part of the shared page-context global scope (no module system in MV3
// content scripts here), same convention as linkedin.js/indeed.js.
function enumerateForm() {
  const form = document.querySelector("form") || document.body;
  const controls = form.querySelectorAll("input, select, textarea");
  const out = [];
  for (const el of controls) {
    const type = (el.type || el.tagName).toLowerCase();
    if (["hidden", "submit", "button", "search"].includes(type)) continue;
    const id = el.name || el.id || (el.getAttribute("aria-label") || "").slice(0, 60);
    if (!id) continue;
    out.push({
      field_id: id,
      label: labelFor(el),
      input_type: type,
      options: el.tagName === "SELECT" ? [...el.options].map((o) => o.textContent.trim()) : [],
      required: !!el.required,
    });
  }
  return out;
}

function labelFor(el) {
  if (el.id) {
    const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (lab) return lab.textContent.trim();
  }
  const wrap = el.closest("label");
  if (wrap) return wrap.textContent.trim();
  return el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || "";
}
