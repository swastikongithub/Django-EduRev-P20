// LPU Reserve — configuration console behaviour (CSP-safe: data-* hooks only, no inline JS).
// Every screen works without it; this only adds conveniences.
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  // ── Print (door QR) ──────────────────────────────────────────────────
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-print]")) { e.preventDefault(); window.print(); }
  });

  // ── Sheets that should open on load (edit links, forms with errors) ──
  function autoopen() {
    const dlg = $("dialog[data-autoopen]");
    if (dlg && dlg.showModal && !dlg.open) {
      dlg.showModal();
      const bad = $("[aria-invalid='true']", dlg);
      (bad || $("input:not([type=hidden]), select, textarea", dlg))?.focus();
    }
  }

  // ── Conditional fields: [data-show-when="field=a,b"] inside form[data-switches] ──
  function fieldValue(form, name) {
    const els = $$(`[name="${name}"]`, form);
    if (!els.length) return "";
    const el = els[0];
    if (el.type === "radio") { const on = els.find((x) => x.checked); return on ? on.value : ""; }
    if (el.type === "checkbox") return el.checked ? "on" : "off";
    return el.value;
  }
  function applySwitches(form) {
    $$("[data-show-when]", form).forEach((box) => {
      const [name, values] = box.dataset.showWhen.split("=");
      box.hidden = !values.split(",").includes(fieldValue(form, name));
    });
  }
  function initSwitches(root = document) {
    $$("form[data-switches]", root).forEach(applySwitches);
  }
  document.addEventListener("change", (e) => {
    const form = e.target.closest("form[data-switches]");
    if (form) applySwitches(form);
    const role = e.target.closest("[data-step-role]");
    if (role) toggleStepUser(role.closest("[data-row]"));
  });

  // ── Prefill a sheet's form from the button that opened it ────────────
  function setField(form, name, value) {
    $$(`[name="${name}"]`, form).forEach((el) => {
      if (el.type === "radio" || el.type === "checkbox") el.checked = el.value === String(value);
      else el.value = value;
    });
  }
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-open][data-prefill], [data-open][data-prefill-scope]");
    if (!btn) return;
    const form = $("form", document.getElementById(btn.dataset.open) || document.createElement("div"));
    if (!form) return;
    let values = {};
    if (btn.dataset.prefill) {
      try { values = JSON.parse(btn.dataset.prefill); } catch (err) { values = {}; }
    } else {
      const scope = btn.dataset.prefillScope;
      values.scope = scope;
      if (scope === "type") values.resource_type = btn.dataset.prefillTarget;
      if (scope === "resource") values.resource = btn.dataset.prefillTarget;
    }
    Object.entries(values).forEach(([k, v]) => setField(form, k, v));
    applySwitches(form);
  });

  // ── Repeating rows (resource details, workflow steps) ────────────────
  function renumber(list) {
    $$("[data-row]", list).forEach((row, i) => {
      const n = $("[data-step-n]", row);
      if (n) n.textContent = String(i + 1);
    });
  }
  function toggleStepUser(row) {
    if (!row) return;
    const role = $("[data-step-role]", row);
    const user = $("[data-step-user]", row);
    if (role && user) user.hidden = role.value !== "user";
  }
  document.addEventListener("click", (e) => {
    const add = e.target.closest("[data-add-row]");
    if (add) {
      const name = add.dataset.addRow;
      const list = $(`[data-rows="${name}"]`);
      const tpl = $(`template[data-row-template="${name}"]`);
      if (!list || !tpl) return;
      const max = parseInt(add.dataset.max || "0", 10);
      if (max && $$("[data-row]", list).length >= max) {
        window.toast && window.toast(`Keep it to ${max} steps or fewer.`, "warning");
        return;
      }
      list.appendChild(tpl.content.cloneNode(true));
      const row = $$("[data-row]", list).pop();
      renumber(list);
      toggleStepUser(row);
      $("input, select", row)?.focus();
      return;
    }
    const remove = e.target.closest("[data-remove-row]");
    if (remove) {
      const row = remove.closest("[data-row]");
      const list = row?.parentElement;
      if (!row || !list) return;
      if ($$("[data-row]", list).length === 1) {
        $$("input, select", row).forEach((el) => { if (el.type !== "number") el.value = ""; });
      } else {
        row.remove();
      }
      renumber(list);
      return;
    }
    const move = e.target.closest("[data-move]");
    if (move) {
      const row = move.closest("[data-row]");
      const list = row?.parentElement;
      if (!row || !list) return;
      if (move.dataset.move === "-1" && row.previousElementSibling) list.insertBefore(row, row.previousElementSibling);
      if (move.dataset.move === "1" && row.nextElementSibling) list.insertBefore(row.nextElementSibling, row);
      renumber(list);
      move.focus();
    }
  });

  // ── Selects that submit their form (role changes); undo if the confirm is declined ──
  document.addEventListener("change", (e) => {
    const sel = e.target.closest("select[data-submit-on-change]");
    if (sel && sel.form) sel.form.requestSubmit();
  });
  const confirmDlg = $("#confirm-dialog");
  if (confirmDlg) {
    confirmDlg.addEventListener("close", () => {
      $$("select[data-submit-on-change]").forEach((sel) => {
        if (sel.form && sel.form.dataset.confirmed) return;
        const def = Array.from(sel.options).find((o) => o.defaultSelected);
        if (def) sel.value = def.value;
      });
    });
  }

  // ── Init ─────────────────────────────────────────────────────────────
  initSwitches();
  $$("[data-rows]").forEach((list) => { $$("[data-row]", list).forEach(toggleStepUser); renumber(list); });
  autoopen();
  document.addEventListener("htmx:afterSwap", (e) => initSwitches(e.target));
})();
