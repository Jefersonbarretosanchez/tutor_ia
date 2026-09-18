(function () {
  "use strict";

  const root = document.getElementById("lti-chat-root");
  const token = JSON.parse(document.getElementById("lti-chat-token").textContent);
  const apiBase = JSON.parse(document.getElementById("lti-chat-api-base").textContent);
  const momento = JSON.parse(document.getElementById("lti-chat-momento").textContent);
  const showUnitTokenCount = JSON.parse(document.getElementById("lti-chat-show-unit-tokens").textContent);
  const showCourseUsage = JSON.parse(document.getElementById("lti-chat-show-course-usage").textContent);
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
    if (!showCourseUsage) return;
    const bar = document.createElement("div");
    bar.className = "lti-chat-usage" + (usage.warning ? " is-warning" : "") + (usage.blocked ? " is-blocked" : "");
    bar.innerHTML = `<span class="lti-chat-usage-label">${usage.tokens_used.toLocaleString("es")} tokens consumidos en este curso</span>`;
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

  function loadingSkeletonHtml() {
    return `
      <div class="lti-chat-skeleton" aria-hidden="true">
        <div class="lti-chat-skeleton-bubble"></div>
        <div class="lti-chat-skeleton-bubble lti-chat-skeleton-bubble--user"></div>
        <div class="lti-chat-skeleton-bubble"></div>
      </div>
    `;
  }

  async function boot() {
    root.innerHTML = `<div class="lti-chat-shell"><div class="lti-chat-body" id="lti-chat-body">${loadingSkeletonHtml()}</div></div>`;
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
      body.innerHTML = "";
      const errorMsg = document.createElement("p");
      errorMsg.className = "lti-chat-error";
      errorMsg.textContent = "No se pudo abrir el chat: " + err.message;
      const retryBtn = document.createElement("button");
      retryBtn.type = "button";
      retryBtn.className = "lti-chat-retry";
      retryBtn.textContent = "Reintentar";
      retryBtn.addEventListener("click", boot);
      body.append(errorMsg, retryBtn);
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

    const logWrap = document.createElement("div");
    logWrap.className = "lti-chat-log-wrap";

    const log = document.createElement("div");
    log.className = "lti-chat-log";
    log.setAttribute("role", "log");
    log.setAttribute("aria-live", "polite");
    log.setAttribute("aria-relevant", "additions");
    log.setAttribute("aria-label", "Historial de la conversación");
    log.setAttribute("tabindex", "0");

    const shadowTop = document.createElement("div");
    shadowTop.className = "lti-chat-scroll-shadow lti-chat-scroll-shadow--top";
    const shadowBottom = document.createElement("div");
    shadowBottom.className = "lti-chat-scroll-shadow lti-chat-scroll-shadow--bottom";

    const jumpBtn = document.createElement("button");
    jumpBtn.type = "button";
    jumpBtn.className = "lti-chat-jump-btn";
    jumpBtn.setAttribute("aria-label", "Ir al final de la conversación");
    jumpBtn.innerHTML = `<span>Ir al final</span><span class="lti-chat-jump-badge" hidden></span>`;
    const jumpBadge = jumpBtn.querySelector(".lti-chat-jump-badge");

    const srStatus = document.createElement("div");
    srStatus.className = "lti-chat-sr-only";
    srStatus.setAttribute("aria-live", "polite");

    logWrap.append(log, shadowTop, shadowBottom, jumpBtn, srStatus);
    body.appendChild(logWrap);

    const form = document.createElement("form");
    form.className = "lti-chat-form";
    form.innerHTML = `
      <div class="lti-chat-input-wrap">
        <textarea class="lti-chat-input" placeholder="Escribe tu respuesta al tutor IA…" aria-label="Mensaje para el tutor IA" rows="1"></textarea>
        <button type="submit" class="lti-chat-send" aria-label="Enviar">${SEND_ICON}</button>
      </div>
    `;
    body.appendChild(form);

    const hint = document.createElement("p");
    hint.className = "lti-chat-hint";
    hint.textContent = "Enter para enviar · Shift + Enter para salto de línea";
    body.appendChild(hint);

    const textarea = form.querySelector("textarea");
    const sendBtn = form.querySelector("button");

    const NEAR_BOTTOM_PX = 96;
    let unreadCount = 0;
    let emptyStateEl = null;

    function isNearBottom() {
      return log.scrollHeight - log.scrollTop - log.clientHeight < NEAR_BOTTOM_PX;
    }

    function scrollLogToBottom(smooth) {
      log.scrollTo({ top: log.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    }

    function updateScrollAffordances() {
      const scrollable = log.scrollHeight > log.clientHeight + 1;
      const nearBottom = isNearBottom();
      shadowTop.classList.toggle("is-visible", scrollable && log.scrollTop > 4);
      shadowBottom.classList.toggle("is-visible", scrollable && !nearBottom);
      jumpBtn.classList.toggle("is-visible", scrollable && !nearBottom);
      if (nearBottom && unreadCount) {
        unreadCount = 0;
        jumpBadge.hidden = true;
      }
    }

    log.addEventListener("scroll", updateScrollAffordances);
    window.addEventListener("resize", updateScrollAffordances);
    jumpBtn.addEventListener("click", () => {
      scrollLogToBottom(true);
      unreadCount = 0;
      jumpBadge.hidden = true;
      jumpBtn.classList.remove("is-visible");
    });

    function showEmptyState() {
      emptyStateEl = document.createElement("div");
      emptyStateEl.className = "lti-chat-empty";
      emptyStateEl.textContent = "Escribe tu primer mensaje para comenzar la conversación con el tutor IA.";
      log.appendChild(emptyStateEl);
    }

    function clearEmptyState() {
      if (emptyStateEl) {
        emptyStateEl.remove();
        emptyStateEl = null;
      }
    }

    function appendBubbleSilent(role, text) {
      const bubble = document.createElement("div");
      bubble.className = "lti-chat-bubble lti-chat-bubble--" + role;
      if (role === "assistant") {
        bubble.innerHTML = formatAssistantText(text);
      } else {
        bubble.textContent = text;
      }
      log.appendChild(bubble);
      return bubble;
    }

    function appendBubble(role, text) {
      clearEmptyState();
      const wasNearBottom = isNearBottom();
      const bubble = appendBubbleSilent(role, text);
      if (wasNearBottom || role === "user") {
        scrollLogToBottom(true);
      } else {
        unreadCount += 1;
        jumpBadge.hidden = false;
        jumpBadge.textContent = String(unreadCount);
      }
      updateScrollAffordances();
      return bubble;
    }

    function appendTypingBubble() {
      const wasNearBottom = isNearBottom();
      const bubble = document.createElement("div");
      bubble.className = "lti-chat-bubble lti-chat-bubble--assistant";
      bubble.setAttribute("aria-hidden", "true");
      bubble.innerHTML = '<span class="lti-chat-typing"><span></span><span></span><span></span></span>';
      log.appendChild(bubble);
      srStatus.textContent = "El tutor está escribiendo…";
      if (wasNearBottom) scrollLogToBottom(true);
      updateScrollAffordances();
      return bubble;
    }

    function appendErrorBubble(message, onRetry) {
      clearEmptyState();
      const wasNearBottom = isNearBottom();
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
        updateScrollAffordances();
        onRetry();
      });
      bubble.appendChild(retryBtn);

      log.appendChild(bubble);
      if (wasNearBottom) scrollLogToBottom(true);
      updateScrollAffordances();
      return bubble;
    }

    function updateSendState() {
      sendBtn.disabled = textarea.disabled || textarea.value.trim().length === 0;
    }

    function lockInput(locked) {
      textarea.disabled = locked;
      updateSendState();
    }

    function updateMomentProgress(pct, tokensUsados, presupuesto) {
      const pctValue = pct || 0;
      progress.classList.toggle("is-near-limit", pctValue >= 75);
      const label =
        showUnitTokenCount && presupuesto
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

    if (moment.messages.length) {
      moment.messages.forEach((msg) => appendBubbleSilent(msg.role, msg.content));
    } else {
      showEmptyState();
    }
    updateMomentProgress(moment.porcentaje_usado, moment.tokens_used, moment.presupuesto);
    updateSendState();

    requestAnimationFrame(() => {
      log.scrollTop = log.scrollHeight;
      updateScrollAffordances();
      if (!textarea.disabled) textarea.focus({ preventScroll: true });
    });

    textarea.addEventListener("input", () => {
      autoResizeTextarea();
      updateSendState();
    });

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
        srStatus.textContent = "";
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
        srStatus.textContent = "";
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
      updateSendState();
      submitToClara(text);
    });
  }

  function refreshUsageBar(container) {
    const old = container.querySelector(".lti-chat-usage");
    if (!showCourseUsage) {
      if (old) old.remove();
      return;
    }
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
