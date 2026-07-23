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
    try {
      const el = _findControl(f.field_id);
      if (el && _writeValue(el, f.value)) filled++;
    } catch (_) {
      // One bad control (e.g. a file input throwing on programmatic .value
      // assignment) shouldn't strand every remaining field.
    }
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
    // "true" only means "check this box" for boolean-style controls (empty/
    // "on"/"true" own-value); an arbitrary radio option must match by value.
    if (
      el.value === value ||
      (value === "true" && ["", "on", "true"].includes(el.value))
    ) {
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

// Normalize option/value text for matching + commit verification: trim,
// collapse internal whitespace, case-fold. Equality on this (not "non-empty")
// keeps a pre-existing selection from being misread as our commit.
function _normText(s) {
  return (s || "").replace(/\s+/g, " ").trim().toLowerCase();
}

// Commit a plan value into a react-select-style combobox (Greenhouse). Types
// the value to open/filter the menu, polls for a matching [role="option"],
// commits on mousedown, and verifies the rendered single-value equals the
// option. Resolves true only on a verified commit; otherwise clears the field
// and resolves false. Anchors on the stable ARIA contract, not emotion hashes.
async function _commitCombobox(el, value) {
  const want = _normText(value);
  if (!want) return false;
  el.focus();
  _setNativeValue(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));

  const deadline = Date.now() + 1500;
  let target = null;
  while (Date.now() < deadline) {
    const opts = [...document.querySelectorAll('[role="option"]')];
    const exact = opts.find((o) => _normText(o.textContent) === want);
    if (exact) { target = exact; break; }
    const starts = opts.filter((o) => _normText(o.textContent).startsWith(want));
    if (starts.length === 1) { target = starts[0]; break; }
    await new Promise((r) => setTimeout(r, 60));
  }
  if (!target) { _clearCombobox(el); return false; }

  const committed = _normText(target.textContent);
  for (const type of ["mousedown", "mouseup", "click"]) {
    target.dispatchEvent(new MouseEvent(type, { bubbles: true }));
  }

  const container = el.closest('[class*="control"], [class*="select"]') || el.parentElement;
  const sv =
    (container && container.querySelector('[class*="singleValue"], [class*="single-value"]')) || null;
  if (sv && _normText(sv.textContent) === committed) return true;
  _clearCombobox(el);
  return false;
}

// Reset a combobox to empty so nothing looks half-filled: Escape (close menu),
// wipe the input via the native setter + input, blur. react-select discards
// unselected text on blur; the explicit reset guarantees it across variants.
function _clearCombobox(el) {
  el.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  el.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", bubbles: true }));
  _setNativeValue(el, "");
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.blur();
}
