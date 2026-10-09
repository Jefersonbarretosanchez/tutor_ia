/* Interacciones del portal: menú colapsable, modales HTMX, paleta Ctrl+K, confirmaciones y avisos. */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const root = document.documentElement;
  const isMobile = () => window.matchMedia("(max-width: 900px)").matches;

  // ---- Menú: colapsable en escritorio (se recuerda), panel deslizable en móvil ----
  const side = $("#side");
  const menuBtn = $("#menu-btn");
  if (side && menuBtn) {
    const scrim = document.createElement("div");
    scrim.className = "scrim";
    scrim.hidden = true;
    document.body.appendChild(scrim);

    const setDrawer = (open) => {
      side.classList.toggle("open", open);
      scrim.hidden = !open;
      document.body.classList.toggle("nav-open", open);
      menuBtn.setAttribute("aria-expanded", String(open));
    };
    const setCollapsed = (collapsed) => {
      root.dataset.nav = collapsed ? "collapsed" : "";
      menuBtn.setAttribute("aria-expanded", String(!collapsed));
      try { localStorage.setItem("portal-nav", collapsed ? "collapsed" : "open"); } catch (e) { /* sin almacenamiento */ }
    };

    menuBtn.setAttribute("aria-expanded", String(isMobile() ? false : root.dataset.nav !== "collapsed"));
    menuBtn.addEventListener("click", () => {
      if (isMobile()) setDrawer(!side.classList.contains("open"));
      else setCollapsed(root.dataset.nav !== "collapsed");
    });
    scrim.addEventListener("click", () => setDrawer(false));
    side.addEventListener("click", (e) => e.target.closest("a") && isMobile() && setDrawer(false));
    document.addEventListener("keydown", (e) => e.key === "Escape" && setDrawer(false));
    window.matchMedia("(min-width: 901px)").addEventListener("change", (m) => m.matches && setDrawer(false));
  }

  // ---- Avisos ----
  const toasts = $(".toasts");
  const bindToast = (t) => {
    setTimeout(() => t.remove(), 6000);
    const x = $("button", t);
    if (x) x.addEventListener("click", () => t.remove());
  };
  document.querySelectorAll(".toast").forEach(bindToast);
  const toast = (text, kind) => {
    if (!toasts) return;
    const t = document.createElement("div");
    t.className = "toast " + (kind || "");
    t.innerHTML = "<span></span><button aria-label='Cerrar aviso'>×</button>";
    t.firstChild.textContent = text;
    toasts.appendChild(t);
    bindToast(t);
  };

  // ---- Modal genérico (contenido cargado con HTMX en #modal-content) ----
  const modal = $("#modal");
  const content = $("#modal-content");
  if (modal && content) {
    document.body.addEventListener("htmx:afterSwap", (e) => {
      if (e.detail.target !== content) return;
      const menu = $(".menu[open]");
      if (menu) menu.removeAttribute("open");
      if (!modal.open) modal.showModal();
      const first = content.querySelector("input:not([type=hidden]):not([type=checkbox]),select,textarea");
      if (first) first.focus();
    });
    document.body.addEventListener("close-modal", () => modal.open && modal.close());
    modal.addEventListener("close", () => { content.innerHTML = ""; });
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.close(); });
    document.addEventListener("click", (e) => {
      if (e.target.closest("[data-close]") && modal.open) modal.close();
    });
    // Matriz de permisos: marcar/desmarcar una fila completa
    content.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-toggle-row]");
      if (!btn) return;
      const boxes = Array.from(btn.closest("tr").querySelectorAll("input[type=checkbox]:not(:disabled)"));
      const all = boxes.every((b) => b.checked);
      boxes.forEach((b) => (b.checked = !all));
    });
  }
  document.body.addEventListener("htmx:responseError", (e) => {
    const code = e.detail.xhr ? e.detail.xhr.status : 0;
    toast(code === 403 ? "No tienes permiso para esta acción." : "No se pudo completar la acción. Inténtalo de nuevo.", "error");
  });
  document.body.addEventListener("htmx:sendError", () => toast("Sin conexión con el servidor.", "error"));

  // ---- Confirmación propia para formularios con data-confirm ----
  const dlg = $("#confirm-dialog");
  if (dlg) {
    let pending = null;
    document.addEventListener("submit", (e) => {
      const form = e.target;
      const msg = form.dataset && form.dataset.confirm;
      if (!msg || form._confirmed) return;
      e.preventDefault();
      pending = form;
      $("#confirm-text", dlg).textContent = msg;
      dlg.showModal();
    });
    $("#confirm-ok", dlg).addEventListener("click", () => {
      dlg.close();
      if (pending) { pending._confirmed = true; pending.requestSubmit(); }
    });
    $("#confirm-cancel", dlg).addEventListener("click", () => dlg.close());
  }

  // ---- Paleta de comandos / búsqueda global ----
  const pal = $("#palette");
  if (pal) {
    const input = $("input", pal);
    const list = $("#palette-pages");
    const results = $("#palette-results");
    let idx = -1;

    const open = () => {
      pal.showModal();
      input.value = "";
      input.dispatchEvent(new Event("input"));
      input.focus();
    };
    document.querySelectorAll("[data-open-palette]").forEach((b) => b.addEventListener("click", open));
    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        pal.open ? pal.close() : open();
      }
    });
    pal.addEventListener("click", (e) => { if (e.target === pal) pal.close(); });

    const visible = () => Array.from(pal.querySelectorAll("li:not([hidden]) a"));
    const select = (n) => {
      const items = visible();
      if (!items.length) return;
      idx = (n + items.length) % items.length;
      items.forEach((a, i) => a.classList.toggle("sel", i === idx));
      items[idx].scrollIntoView({ block: "nearest" });
    };
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      list.querySelectorAll("li:not(.ttl)").forEach((li) => (li.hidden = q && !li.textContent.toLowerCase().includes(q)));
      idx = -1;
      select(0);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); select(idx + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); select(idx - 1); }
      else if (e.key === "Enter") { const a = visible()[idx]; if (a) a.click(); }
    });
    results.addEventListener("htmx:afterSwap", () => select(0));
  }
})();
