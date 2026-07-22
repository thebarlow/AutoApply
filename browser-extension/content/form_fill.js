// browser-extension/content/form_fill.js
// Writes an application plan's resolved values into the live form. Loaded as a
// plain content script alongside injector.js/form_enumerate.js on ATS apply
// pages (no module system — fillForm() joins the shared page-context globals).
function fillForm(plannedFields) {
  if (!Array.isArray(plannedFields)) return { filled: 0 };
  let filled = 0;
  for (const f of plannedFields) {
    if (!f || (f.status !== "filled" && f.status !== "drafted")) continue;
    if (f.value == null || f.value === "") continue;
    const el = _findControl(f.field_id);
    if (el && _writeValue(el, f.value)) filled++;
  }
  return { filled };
}

function _findControl(fieldId) {
  return (
    document.querySelector(`[name="${CSS.escape(fieldId)}"]`) ||
    document.getElementById(fieldId) ||
    document.querySelector(`[aria-label="${CSS.escape(fieldId)}"]`)
  );
}

function _writeValue(el, value) {
  const tag = el.tagName.toLowerCase();
  const type = (el.type || "").toLowerCase();
  if (tag === "select") {
    const opt = [...el.options].find(
      (o) => o.value === value || o.textContent.trim() === value
    );
    if (!opt) return false;
    el.value = opt.value;
    _fire(el);
    return true;
  }
  if (type === "checkbox" || type === "radio") {
    if (el.value === value || value === "true") {
      el.checked = true;
      _fire(el);
      return true;
    }
    return false;
  }
  _setNativeValue(el, value);
  _fire(el);
  return true;
}

// React (and other controlled inputs) ignore a plain .value assignment because
// they track the native setter; call the prototype setter so the framework sees
// the change on the following input event.
function _setNativeValue(el, value) {
  const proto =
    el.tagName === "TEXTAREA"
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
  setter.call(el, value);
}

function _fire(el) {
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}
