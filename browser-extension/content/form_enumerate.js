// browser-extension/content/form_enumerate.js
// Read-only enumeration of a live application form. No writing, no network, no
// focus/mutation. enumerateForm()/labelFor() join the shared page-context global
// scope (no module system in MV3 content scripts), same convention as
// linkedin.js/indeed.js.
function enumerateForm() {
  const form = document.querySelector("form") || document.body;
  const controls = [...form.querySelectorAll("input, select, textarea")];
  const out = [];
  const seenGroups = new Set();
  for (const el of controls) {
    const domType = (el.type || el.tagName).toLowerCase();
    if (["hidden", "submit", "button", "search"].includes(domType)) continue;

    if (_isComboPartner(el)) continue;

    if (domType === "radio" || (domType === "checkbox" && el.name && _groupOf(form, el).length > 1)) {
      const members = _groupOf(form, el);
      const key = el.name || (el.closest("fieldset") && el.closest("fieldset").id) || "";
      if (!key || seenGroups.has(key)) continue;
      seenGroups.add(key);
      const rawLabel = _groupLabel(el);
      out.push({
        field_id: el.name || key,
        label: _cleanLabel(rawLabel),
        input_type: domType === "radio" ? "radio_group" : "checkbox_group",
        options: members.map((m) => _cleanLabel(labelFor(m))),
        required: members.some((m) => _isRequired(m, _groupLabel(m))),
      });
      continue;
    }

    const id = el.name || el.id || (el.getAttribute("aria-label") || "").slice(0, 60);
    if (!id) {
      console.debug("[job-scraper][enumerate] skipped anonymous control", el.tagName, domType);
      continue;
    }

    const rawLabel = labelFor(el);
    out.push({
      field_id: id,
      label: _cleanLabel(rawLabel),
      input_type: _logicalType(el, domType),
      options: el.tagName === "SELECT" ? [...el.options].map((o) => o.textContent.trim()) : [],
      required: _isRequired(el, rawLabel),
    });
  }
  return out;
}

// Logical (not raw-DOM) field type. Greenhouse/Ashby render single- and
// multi-selects as role="combobox" text inputs, so el.type alone reports "text".
function _logicalType(el, domType) {
  const role = (el.getAttribute("role") || "").toLowerCase();
  const isCombo = role === "combobox" || el.hasAttribute("aria-autocomplete");
  const multi =
    el.getAttribute("aria-multiselectable") === "true" || (el.tagName === "SELECT" && el.multiple);
  if (isCombo) return multi ? "multiselect" : "combobox";
  if (el.tagName === "SELECT") return multi ? "multiselect" : "select";
  return domType;
}

// Requiredness lives in ARIA or the label '*' on modern ATS DOM, not el.required.
function _isRequired(el, rawLabel) {
  return (
    el.required ||
    el.getAttribute("aria-required") === "true" ||
    /\*\s*$/.test(rawLabel || "")
  );
}

// Strip a single trailing required-marker '*' and collapse whitespace so the
// marker drives `required` instead of polluting the question text.
function _cleanLabel(raw) {
  return (raw || "").replace(/\s*\*\s*$/, "").replace(/\s+/g, " ").trim();
}

// A combobox renders a second input in its container with no real identity.
// Skip it explicitly (rather than relying on the empty-id guard) so a genuinely
// anonymous field elsewhere is still logged, not silently swallowed.
function _isComboPartner(el) {
  const idish = el.name || el.id || (el.getAttribute("aria-label") || "").trim();
  if (idish) return false;
  const container = el.closest("div, fieldset, label") || el.parentElement;
  return !!(container && container.querySelector('[role="combobox"]'));
}

// All same-name radio/checkbox controls within the form (a logical group).
function _groupOf(form, el) {
  if (!el.name) return [el];
  return [...form.querySelectorAll(`input[name="${CSS.escape(el.name)}"]`)];
}

// The group's question: <legend>, then a labelled radiogroup/group container,
// falling back to the first member's own label so the field is never dropped.
function _groupLabel(el) {
  const fs = el.closest("fieldset");
  const legend = fs && fs.querySelector("legend");
  if (legend) return legend.textContent.trim();
  const grp = el.closest('[role="radiogroup"], [role="group"]');
  if (grp && grp.getAttribute("aria-label")) return grp.getAttribute("aria-label");
  return labelFor(el);
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
