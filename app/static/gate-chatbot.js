(function () {
  const SESSION_KEY = "gate_chatbot_session_id";
  const getSession = () => {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = "web-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  };

  const el = (tag, attrs = {}, text) => {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (key === "class") node.className = value;
      else if (key === "dataset") Object.assign(node.dataset, value);
      else node.setAttribute(key, value);
    });
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const launcher = el("button", { class: "gate-chatbot-launcher", type: "button" }, "Ask about this page");
  const panel = el("section", { class: "gate-chatbot-panel", "aria-label": "Gate page chatbot" });
  panel.innerHTML = [
    '<div class="gate-chatbot-head">',
    '  <div><h2 class="gate-chatbot-title">Gate page chatbot</h2><p class="gate-chatbot-subtitle">Gateway-routed tenant, budget capped, audited live.</p></div>',
    '  <button class="gate-chatbot-close" type="button" aria-label="Close">x</button>',
    '</div>',
    '<div class="gate-chatbot-stats" aria-live="polite">',
    '  <div class="gate-chatbot-stat"><span>Calls 24h</span><strong data-stat="calls">0</strong></div>',
    '  <div class="gate-chatbot-stat"><span>Budget used</span><strong data-stat="budget">0%</strong></div>',
    '  <div class="gate-chatbot-stat"><span>Last route</span><strong data-stat="model">No calls yet</strong></div>',
    '</div>',
    '<div class="gate-chatbot-log"></div>',
    '<div class="gate-chatbot-suggestions"></div>',
    '<form class="gate-chatbot-form">',
    '  <input class="gate-chatbot-input" name="question" maxlength="1200" autocomplete="off" placeholder="Ask what any term or section means..." />',
    '  <button class="gate-chatbot-submit" type="submit">Send</button>',
    '</form>'
  ].join("");

  document.body.append(panel, launcher);

  const log = panel.querySelector(".gate-chatbot-log");
  const form = panel.querySelector("form");
  const input = panel.querySelector("input");
  const submit = panel.querySelector(".gate-chatbot-submit");
  const suggestions = panel.querySelector(".gate-chatbot-suggestions");

  const addMessage = (role, text) => {
    const msg = el("div", { class: "gate-chatbot-message", dataset: { role } }, text);
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;
    return msg;
  };

  const setStat = (name, value) => {
    const node = panel.querySelector('[data-stat="' + name + '"]');
    if (node) node.textContent = value == null || value === "" ? "n/a" : String(value);
  };

  const formatPct = value => value == null ? "0%" : value + "%";

  async function refreshStats() {
    try {
      const res = await fetch("/v1/stats/chatbot", { headers: { "Accept": "application/json" } });
      if (!res.ok) return;
      const data = await res.json();
      if (!data.configured) return;
      setStat("calls", data.totals_7d.calls_24h);
      setStat("budget", formatPct(data.budget.used_pct));
      const latest = data.recent && data.recent[0];
      setStat("model", latest ? (latest.model || latest.status) : "No calls yet");
    } catch (_) {
      /* Stats are useful, not critical. */
    }
  }

  async function ask(question) {
    addMessage("user", question);
    submit.disabled = true;
    const pending = addMessage("assistant", "Routing through the gate-chatbot tenant...");
    try {
      const res = await fetch("/v1/landing-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ question, session_id: getSession() })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = data.detail || "The chatbot request failed.";
        pending.textContent = res.status === 402
          ? "The chatbot monthly budget is exhausted, so the gateway refused the provider call."
          : detail;
        await refreshStats();
        return;
      }
      pending.textContent = data.answer || "No answer returned.";
      addMessage("meta", "Audit: " + (data.routed_model || "model unknown") + " | cache " + (data.cache || "n/a") + " | budget " + (data.budget_used_pct || "0") + "% | request " + (data.request_id || "n/a"));
      await refreshStats();
    } catch (_) {
      pending.textContent = "The page could not reach the chatbot endpoint.";
    } finally {
      submit.disabled = false;
      input.focus();
    }
  }

  [
    "What is this gateway?",
    "Define tenant, policy, budget and fallback.",
    "Why is the chatbot not calling /v1/chat directly?",
    "What will the live dashboard show after this call?"
  ].forEach(text => {
    const button = el("button", { type: "button" }, text);
    button.addEventListener("click", () => ask(text));
    suggestions.appendChild(button);
  });

  launcher.addEventListener("click", () => {
    const open = panel.dataset.open === "true";
    panel.dataset.open = open ? "false" : "true";
    if (!open && log.childElementCount === 0) {
      addMessage("assistant", "Ask me to explain any section, control, acronym, or word on this gateway page. I only answer from the approved page facts.");
      refreshStats();
      input.focus();
    }
  });

  panel.querySelector(".gate-chatbot-close").addEventListener("click", () => {
    panel.dataset.open = "false";
  });

  form.addEventListener("submit", event => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    ask(question);
  });

  refreshStats();
  setInterval(refreshStats, 15000);
})();
