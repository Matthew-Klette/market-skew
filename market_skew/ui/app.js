// Sorting, filters, watchlist stars, the run button, the theme switch and the page chat. No libraries.
(() => {
  const token = document.querySelector('meta[name="skew-token"]').content;
  const post = (path, body) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Skew-Token": token }, body: JSON.stringify(body || {}) }).then((r) => r.json());

  // Sortable tables: numbers sort on data-v, text on its content.
  document.querySelectorAll("table.sortable").forEach((table) => {
    const heads = [...table.querySelectorAll("th")];
    heads.forEach((th, col) => {
      if (!th.dataset.sort) return;
      th.tabIndex = 0;
      const sort = () => {
        const down = th.getAttribute("aria-sort") !== "descending";
        heads.forEach((h) => h.removeAttribute("aria-sort"));
        th.setAttribute("aria-sort", down ? "descending" : "ascending");
        const body = table.tBodies[0];
        const key = (row) => {
          const cell = row.cells[col];
          return th.dataset.sort === "num" ? parseFloat(cell.dataset.v ?? "0") : cell.textContent.trim().toLowerCase();
        };
        const rows = [...body.rows].sort((a, b) => {
          const x = key(a), y = key(b);
          const order = typeof x === "number" ? x - y : x.localeCompare(y);
          return down ? -order : order;
        });
        rows.forEach((row) => body.appendChild(row));
      };
      th.addEventListener("click", sort);
      th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
    });
  });

  // Stocks: bucket chips and ticker search.
  const chips = [...document.querySelectorAll("[data-filter]")];
  const search = document.querySelector("[data-search]");
  const sectorPick = document.querySelector("[data-sector]");
  const applyFilter = () => {
    const active = chips.find((c) => c.getAttribute("aria-pressed") === "true")?.dataset.filter || "all";
    const text = (search?.value || "").trim().toUpperCase();
    document.querySelectorAll("table.stocks tbody tr").forEach((row) => {
      const inBucket = active === "all" || (active === "watch" ? row.dataset.watch === "1" : row.dataset.bucket === active);
      const inSector = !sectorPick?.value || row.dataset.sector === sectorPick.value;
      const matches = !text || row.dataset.symbol.startsWith(text) || (row.dataset.name || "").includes(text);
      row.hidden = !(inBucket && inSector && matches);
    });
  };
  chips.forEach((chip) => chip.addEventListener("click", () => {
    chips.forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
    applyFilter();
  }));
  search?.addEventListener("input", applyFilter);
  sectorPick?.addEventListener("change", applyFilter);

  document.querySelectorAll("[data-star]").forEach((star) => star.addEventListener("click", async () => {
    const result = await post("/watch", { symbol: star.dataset.star });
    if (result.error) return;
    star.setAttribute("aria-pressed", String(result.on));
    star.closest("tr").dataset.watch = result.on ? "1" : "0";
  }));

  document.querySelectorAll("[data-exclude]").forEach((btn) => btn.addEventListener("click", async () => {
    btn.disabled = true;
    const result = await post("/exclude", { symbol: btn.dataset.exclude });
    if (result.error) { btn.disabled = false; return; }
    btn.closest(".pick").remove();
  }));

  // Recommended / My way / His way: saved for this month, then the page redraws with the plan and sections to match.
  const lensButtons = [...document.querySelectorAll("[data-lens]")];
  lensButtons.forEach((btn) => btn.addEventListener("click", async () => {
    if (btn.getAttribute("aria-pressed") === "true") return;
    lensButtons.forEach((b) => { b.disabled = true; });
    const result = await post("/lens", { lens: btn.dataset.lens }).catch(() => ({ error: true }));
    if (result.error) { lensButtons.forEach((b) => { b.disabled = false; }); return; }
    location.reload();
  }));

  // Monthly amounts on Picks: the plan updates as you type and is remembered for this month.
  const planEl = document.querySelector("[data-plan]");
  if (planEl) {
    const cfg = JSON.parse(planEl.dataset.planConfig);
    const rand = (v) => "R" + Math.round(v).toLocaleString("en-ZA").replace(/\u00a0/g, " ");
    const tfsaFee = cfg.tfsaFee;
    const inputs = [...planEl.querySelectorAll("[data-amount]")];
    let planSeq = 0, planTimer;
    const draw = (name, amount) => {
      if (name === "usd") { // the server re-splits the money so rounding and tilts stay exact; wait for typing to pause
        clearTimeout(planTimer);
        planTimer = setTimeout(() => {
          const seq = ++planSeq;
          post("/plan", { usd: amount }).then((r) => {
            const body = planEl.querySelector('table[data-block="usd"] tbody');
            if (r.rows && body && seq === planSeq) body.innerHTML = r.rows; // an older answer never overwrites a newer one
          }).catch(() => {});
        }, 400);
        return;
      }
      planEl.querySelectorAll(`table[data-block="${name}"] tbody tr`).forEach((row) => {
        const gross = amount * Number(row.dataset.w);
        const fee = gross * tfsaFee;
        const put = (cell, text) => { const c = row.querySelector(`[data-cell="${cell}"]`); if (c) c.textContent = text; };
        put("rand", rand(gross));
        put("usd", cfg.rate ? "$" + Math.round(gross / cfg.rate).toLocaleString("en-US") : "–");
        put("fee", rand(fee));
        put("net", rand(gross - fee));
      });
    };
    let saveTimer;
    inputs.forEach((input) => input.addEventListener("input", () => {
      draw(input.dataset.amount, Math.max(0, Number(input.value) || 0));
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        const body = {};
        inputs.forEach((i) => { body[i.dataset.amount] = Math.max(0, Number(i.value) || 0); });
        post("/amounts", body);
      }, 600);
    }));
  }

  // First run on Picks: save the two monthly amounts, then reload so the plan appears.
  const firstRun = document.querySelector("[data-first-run-form]");
  if (firstRun) firstRun.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = {};
    firstRun.querySelectorAll("[data-first-amount]").forEach((i) => { body[i.dataset.firstAmount] = Math.max(0, Number(i.value) || 0); });
    const status = firstRun.querySelector("[data-first-run-status]");
    if (!body.tfsa && !body.usd) { if (status) status.textContent = "Enter at least one amount."; return; }
    const result = await post("/amounts", body).catch(() => ({ error: true }));
    if (result.error) { if (status) status.textContent = "Could not save; try again."; return; }
    location.reload();
  });

  // Money tab: holdings editor, money inputs and sleeve targets. Each saves with its own button, then reloads.
  const say = (el, text) => { if (el) el.textContent = text; };
  const holdingsEl = document.querySelector("[data-holdings]");
  if (holdingsEl) {
    const body = holdingsEl.querySelector("[data-rows]");
    const status = holdingsEl.querySelector("[data-holdings-status]");
    holdingsEl.querySelector("[data-add-row]").addEventListener("click", () => {
      body.appendChild(holdingsEl.querySelector("[data-row-template]").content.cloneNode(true));
    });
    body.addEventListener("click", (ev) => { const b = ev.target.closest("[data-remove-row]"); if (b) b.closest("tr").remove(); });
    holdingsEl.querySelector("[data-save-holdings]").addEventListener("click", async () => {
      const rows = [...body.querySelectorAll("tr[data-holding]")].map((tr) => {
        const get = (f) => tr.querySelector(`[data-f="${f}"]`);
        return { symbol: get("symbol").value.trim().toUpperCase(), account: get("account").value, units: get("units").value,
                 avg_price: get("avg_price").value, last_buy: get("last_buy").value, new_money: get("new_money").checked };
      }).filter((r) => r.symbol);
      const out = await post("/holdings", { holdings: rows }).catch(() => ({ error: "The app did not answer." }));
      if (out.error) return say(status, out.error);
      say(status, "Saved."); location.reload();
    });
  }
  const milestonesEl = document.querySelector("[data-milestones]");
  if (milestonesEl) {
    const body = milestonesEl.querySelector("[data-rows]");
    milestonesEl.querySelector("[data-add-row]").addEventListener("click", () => {
      body.appendChild(milestonesEl.querySelector("[data-row-template]").content.cloneNode(true));
    });
    body.addEventListener("click", (ev) => { const b = ev.target.closest("[data-remove-row]"); if (b) b.closest("tr").remove(); });
    milestonesEl.querySelector("[data-save-milestones]").addEventListener("click", async () => {
      const items = [...body.querySelectorAll("tr[data-milestone]")].map((tr) => {
        const get = (f) => tr.querySelector(`[data-f="${f}"]`);
        return { label: get("label").value.trim(), kind: get("kind").value, value: get("value").value };
      }).filter((m) => m.label || m.value);
      const status = milestonesEl.querySelector("[data-milestones-status]");
      const out = await post("/milestones", { milestones: items }).catch(() => ({ error: "The app did not answer." }));
      if (out.error) return say(status, out.error);
      say(status, "Saved."); location.reload();
    });
  }
  const formValues = (form) => Object.fromEntries([...form.querySelectorAll("input[name]")].map((i) => [i.name, i.value]));
  document.querySelector("[data-money-form]")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const note = ev.currentTarget.querySelector("[data-money-status]");
    const out = await post("/money", { money: formValues(ev.currentTarget) }).catch(() => ({ error: "The app did not answer." }));
    if (out.error) return say(note, out.error);
    say(note, "Saved."); location.reload();
  });
  document.querySelector("[data-goal-form]")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const note = ev.currentTarget.querySelector("[data-goal-status]");
    const goal = { ...formValues(ev.currentTarget), actual: ev.currentTarget.elements.actual.checked };
    const out = await post("/goal", { goal }).catch(() => ({ error: "The app did not answer." }));
    if (out.error) return say(note, out.error);
    say(note, "Saved."); location.reload();
  });
  document.querySelector("[data-targets-form]")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const note = ev.currentTarget.querySelector("[data-targets-status]");
    const out = await post("/targets", { targets: formValues(ev.currentTarget) }).catch(() => ({ error: "The app did not answer." }));
    if (out.error) return say(note, out.error);
    say(note, "Saved."); location.reload();
  });

  // One-time "not financial advice" screen.
  document.querySelector("[data-accept]")?.addEventListener("click", async () => {
    const result = await post("/accept").catch(() => ({ error: "The app did not answer." }));
    if (!result.error) location.reload();
  });

  // Theme: saved by the app, so it survives a restart.
  document.querySelector("[data-theme-next]")?.addEventListener("click", async (e) => {
    const current = document.documentElement.dataset.theme;
    const showingDark = current === "dark" || (current === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
    const next = showingDark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    e.currentTarget.textContent = next === "dark" ? "Light" : "Dark";
    if (token) post("/theme", { theme: next });
  });

  // Settings: the SEC contact email.
  document.querySelector("[data-settings]")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const note = document.querySelector("[data-settings-status]");
    const out = await post("/settings", { sec_contact: e.currentTarget.sec_contact.value });
    note.textContent = out.error || "Saved.";
  });

  // Run now, then follow progress until the report is ready.
  const runButton = document.querySelector("[data-run]");
  const runStatus = document.querySelector("[data-run-status]");
  const panel = document.querySelector("[data-progress]");
  const stages = { 1: "Step 1 of 3 · Prices", 2: "Step 2 of 3 · Option bets", 3: "Step 3 of 3 · Retries" };
  const etaText = (sec) => !sec ? "Working out time left…" : sec < 60 ? "Less than a minute left" : `About ${Math.round(sec / 60)} min left`;
  let etaAt = null; // count down smoothly between status updates
  const paint = (s) => {
    if (!panel) return;
    panel.hidden = false;
    panel.querySelector("[data-p-stage]").textContent = (s.step || "").startsWith("Google") ? "Step 3 of 3 · Google's prediction" : stages[s.stage] || "Starting";
    const bar = panel.querySelector("[data-p-bar]");
    const share = s.total ? s.done / s.total : 0;
    bar.classList.toggle("indeterminate", !s.total);
    bar.setAttribute("aria-valuenow", String(Math.round(share * 100)));
    bar.querySelector(".progress-fill").style.width = `${(share * 100).toFixed(1)}%`;
    panel.querySelector("[data-p-note]").textContent = s.total ? `${s.step} · ${s.done.toLocaleString()} of ${s.total.toLocaleString()}` : s.step || "";
    if (s.eta) etaAt = Date.now() + s.eta * 1000;
  };
  setInterval(() => { if (etaAt && panel && !panel.hidden) panel.querySelector("[data-p-eta]").textContent = etaText(Math.max(0, (etaAt - Date.now()) / 1000)); }, 1000);
  const follow = () => {
    const tick = async () => {
      const s = await fetch("/status").then((r) => r.json()).catch(() => ({}));
      if (s.state === "running") {
        runButton.disabled = true; runButton.textContent = "Scanning…";
        runStatus.textContent = s.eta ? etaText(s.eta) : "Working";
        paint(s);
        setTimeout(tick, 2000);
      } else if (s.state === "done" && runButton.disabled) {
        location.reload();
      } else if (s.state === "failed") {
        runButton.disabled = false; runButton.textContent = "Run now";
        runStatus.textContent = `Last run failed: ${s.step}`;
      }
    };
    tick();
  };
  runButton?.addEventListener("click", async () => {
    runButton.disabled = true;
    const result = await post("/run").catch(() => ({ error: "The app did not answer." }));
    if (result.error) { runButton.disabled = false; runStatus.textContent = result.error; return; }
    follow();
  });
  if (runButton?.disabled) follow();

  // Ask about this page.
  const chat = document.querySelector(".chat");
  const opener = document.querySelector("[data-chat-open]");
  const log = chat.querySelector(".chat-log");
  const form = chat.querySelector("[data-chat-form]");
  const box = form.querySelector("textarea");
  let turns = [];
  const line = (text, kind) => { const p = document.createElement("p"); p.className = `ask-line ${kind}`; p.textContent = text; log.appendChild(p); log.scrollTop = log.scrollHeight; return p; };
  const open = (on) => { chat.hidden = !on; opener.hidden = on; document.body.classList.toggle("chat-on", on); if (on) box.focus(); };
  opener.addEventListener("click", () => open(true));
  chat.querySelector("[data-chat-close]").addEventListener("click", () => open(false));
  chat.querySelector("[data-chat-clear]").addEventListener("click", () => { turns = []; log.replaceChildren(); });
  let busy = false;
  const ask = async (question) => {
    if (!question.trim() || busy) return;
    busy = true;
    line(question, "question");
    const waiting = line("Thinking…", "thinking");
    box.value = ""; form.querySelector("button").disabled = true;
    const result = await post("/ask", { question, turns, view: document.body.dataset.view, date: document.body.dataset.date }).catch(() => ({ error: "The app did not answer." }));
    waiting.remove(); form.querySelector("button").disabled = false; busy = false;
    if (result.error) { line(result.error, "problem"); return; }
    line(result.answer, "answer");
    turns = [...turns, [question, result.answer]].slice(-6);
  };
  form.addEventListener("submit", (e) => { e.preventDefault(); ask(box.value); });
  box.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(box.value); } });
  chat.querySelectorAll("[data-suggest]").forEach((b) => b.addEventListener("click", () => ask(b.textContent)));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !chat.hidden) open(false); });
})();
