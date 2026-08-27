(function () {
  "use strict";

  const root = document.getElementById("lti-chat-root");
  const token = JSON.parse(document.getElementById("lti-chat-token").textContent);
  const apiBase = JSON.parse(document.getElementById("lti-chat-api-base").textContent);
  const momento = JSON.parse(document.getElementById("lti-chat-momento").textContent);
  const showTokenCount = JSON.parse(document.getElementById("lti-chat-show-tokens").textContent);
  let usage = JSON.parse(document.getElementById("lti-chat-usage").textContent);

  const SEND_ICON = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 11.5L20.5 3.5L13 21L10.5 13.5L3 11.5Z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="currentColor" fill-opacity="0.15"/></svg>`;

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function formatAssistantText(str) {
    return escapeHtml(str)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");
  }

  async function api(path, options) {
    const response = await fetch(apiBase + path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
        ...(options && options.headers),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || "Ocurrió un error inesperado.");
      error.payload = data;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function renderUsageBar(container) {
    const pct = usage.limit ? Math.min(100, Math.round((usage.tokens_used / usage.limit) * 100)) : 0;
    const bar = document.createElement("div");
    bar.className = "lti-chat-usage" + (usage.warning ? " is-warning" : "") + (usage.blocked ? " is-blocked" : "");
    bar.innerHTML = `
      <div class="lti-chat-usage-track"><div class="lti-chat-usage-fill" style="width:${pct}%"></div></div>
      <span class="lti-chat-usage-label">${usage.tokens_used.toLocaleString("es")} / ${usage.limit.toLocaleString("es")} tokens</span>
    `;
    container.appendChild(bar);
  }

  function renderBlockedNotice(container, text) {
    const notice = document.createElement("div");
    notice.className = "lti-chat-notice";
    notice.textContent =
      text || "Alcanzaste el límite de uso del chat para este curso. Contacta a tu docente si necesitas más.";
    container.appendChild(notice);
  }

  function renderCompletedNotice(container, beforeEl) {
    if (container.querySelector(".lti-chat-notice.is-success")) return;
    const notice = document.createElement("div");
    notice.className = "lti-chat-notice is-success";
    notice.textContent = "Completaste esta actividad. Puedes continuar en Canvas.";
    container.insertBefore(notice, beforeEl);
  }

  async function boot() {
    root.innerHTML = `<div class="lti-chat-shell"><div class="lti-chat-body" id="lti-chat-body"><p class="lti-chat-loading">Cargando…</p></div></div>`;
    const body = document.getElementById("lti-chat-body");

    if (usage.blocked) {
      body.innerHTML = "";
      renderUsageBar(body);
      renderBlockedNotice(body);
      return;
    }

    let moment;
    try {
      moment = await api(`clara/moment/?momento=${encodeURIComponent(momento)}`, { method: "GET" });
    } catch (err) {
      body.innerHTML = `<p class="lti-chat-error">No se pudo abrir el chat: ${err.message}</p>`;
      return;
    }

    renderChatUI(moment);
  }

  function renderChatUI(moment) {
    const body = document.getElementById("lti-chat-body");
    body.innerHTML = "";
    renderUsageBar(body);

    const progress = document.createElement("div");
    progress.className = "lti-chat-moment-progress";
    body.appendChild(progress);

    if (moment.puede_avanzar) {
      renderCompletedNotice(body, progress);
    }

    const log = document.createElement("div");
    log.className = "lti-chat-log";
    body.appendChild(log);

    const form = document.createElement("form");
    form.className = "lti-chat-form";
    form.innerHTML = `
      <div class="lti-chat-input-wrap">
        <textarea class="lti-chat-input" placeholder="Escribe tu respuesta al tutor IA…" rows="1"></textarea>
        <button type="submit" class="lti-chat-send" aria-label="Enviar">${SEND_ICON}</button>
      </div>
    `;
    body.appendChild(form);

    const textarea = form.querySelector("textarea");
    const sendBtn = form.querySelector("button");

    function appendBubble(role, text) {
      const bubble = document.createElement("div");
      bubble.className = "lti-chat-bubble lti-chat-bubble--" + role;
      if (role === "assistant") {
        bubble.innerHTML = formatAssistantText(text);
      } else {
        bubble.textContent = text;
      }
      log.appendChild(bubble);
      log.scrollTop = log.scrollHeight;
      return bubble;
    }

    function appendTypingBubble() {
      const bubble = document.createElement("div");
      bubble.className = "lti-chat-bubble lti-chat-bubble--assistant";
      bubble.innerHTML = '<span class="lti-chat-typing"><span></span><span></span><span></span></span>';
      log.appendChild(bubble);
      log.scrollTop = log.scrollHeight;
      return bubble;
    }

    function appendErrorBubble(message, onRetry) {
      const bubble = document.createElement("div");
      bubble.className = "lti-chat-bubble lti-chat-bubble--assistant lti-chat-bubble--error";

      const p = document.createElement("p");
      p.textContent = message;
      bubble.appendChild(p);

      const retryBtn = document.createElement("button");
      retryBtn.type = "button";
      retryBtn.className = "lti-chat-retry";
      retryBtn.textContent = "Reintentar";
      retryBtn.addEventListener("click", () => {
        bubble.remove();
        onRetry();
      });
      bubble.appendChild(retryBtn);

      log.appendChild(bubble);
      log.scrollTop = log.scrollHeight;
      return bubble;
    }

    function lockInput(locked) {
      textarea.disabled = locked;
      sendBtn.disabled = locked;
    }

    function updateMomentProgress(pct, tokensUsados, presupuesto) {
      const pctValue = pct || 0;
      progress.classList.toggle("is-near-limit", pctValue >= 75);
      const label =
        showTokenCount && presupuesto
          ? `${tokensUsados.toLocaleString("es")} / ${presupuesto.toLocaleString("es")} tokens de esta unidad (${pctValue}%)`
          : `Progreso de esta unidad: ${pctValue}%`;
      progress.innerHTML = `
        <div class="lti-chat-moment-progress-track"><div class="lti-chat-moment-progress-fill" style="width:${pctValue}%"></div></div>
        <span class="lti-chat-moment-progress-label">${label}</span>
      `;
    }

    function autoResizeTextarea() {
      textarea.style.height = "auto";
      textarea.style.height = textarea.scrollHeight + "px";
    }

    moment.messages.forEach((msg) => appendBubble(msg.role, msg.content));
    updateMomentProgress(moment.porcentaje_usado, moment.tokens_used, moment.presupuesto);

    textarea.addEventListener("input", autoResizeTextarea);

    textarea.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });

    async function submitToClara(text) {
      lockInput(true);
      const thinking = appendTypingBubble();

      try {
        const data = await api("clara/reply/", {
          method: "POST",
          body: JSON.stringify({ momento, message: text }),
        });
        thinking.remove();
        appendBubble("assistant", data.message.content);
        usage = data.usage;
        refreshUsageBar(body);
        updateMomentProgress(data.porcentaje_usado, data.tokens_used, data.presupuesto);
        if (data.puede_avanzar) {
          renderCompletedNotice(body, progress);
        }
        if (usage.blocked) {
          lockInput(true);
          renderBlockedNotice(body);
        } else if (data.tipo === "limite_alcanzado") {
          lockInput(true);
        } else {
          lockInput(false);
          textarea.focus();
        }
      } catch (err) {
        thinking.remove();
        if (err.status === 403 && err.payload && err.payload.usage) {
          usage = err.payload.usage;
          refreshUsageBar(body);
          renderBlockedNotice(body, err.message);
          lockInput(true);
        } else {
          appendErrorBubble(err.message || "Tuvimos una falla respondiendo. Intenta de nuevo.", () =>
            submitToClara(text)
          );
          lockInput(false);
          textarea.focus();
        }
      }
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const text = textarea.value.trim();
      if (!text) return;

      appendBubble("user", text);
      textarea.value = "";
      autoResizeTextarea();
      submitToClara(text);
    });

    textarea.focus();
  }

  function refreshUsageBar(container) {
    const old = container.querySelector(".lti-chat-usage");
    const wrapper = document.createElement("div");
    renderUsageBar(wrapper);
    const fresh = wrapper.firstChild;
    if (old) {
      old.replaceWith(fresh);
    } else {
      container.insertBefore(fresh, container.firstChild);
    }
  }

  boot();
})();
