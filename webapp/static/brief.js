// Morning brief page. Talks to the routes in webapp/brief_routes.py.
(function () {
  const $ = (id) => document.getElementById(id);

  function esc(value) {
    return String(value == null ? "" : value).replace(
      /[&<>"']/g,
      (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
    );
  }

  // Only http(s) links are ever put in an href.
  function safeUrl(url) {
    return /^https?:\/\//i.test(url || "") ? url : "";
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }).then((r) => r.json().then((data) => ({ ok: r.ok, data })));
  }

  function empty(text) {
    return `<p class="muted">${esc(text)}</p>`;
  }

  // The lead being messaged, so "Log as sent" can mark it contacted.
  let activeLeadId = "";

  function startMessage(company, person, leadId, kind) {
    activeLeadId = leadId || "";
    $("o-company").value = company || "";
    $("o-person").value = person || "";
    loadDraft(kind || "first");
    $("o-company").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function loadDraft(kind) {
    const params = new URLSearchParams({
      company: $("o-company").value,
      person: $("o-person").value,
      kind: kind || "first",
    });
    fetch("/api/outreach/draft?" + params)
      .then((r) => r.json())
      .then((d) => {
        $("o-draft").value = d.text || "";
        $("o-hint").textContent =
          "Fill the [bracketed] parts before sending — they are left blank on purpose.";
      });
  }

  function renderFollowUps(items) {
    $("followups-count").textContent = `(${items.length})`;
    $("followups").innerHTML = items.length
      ? items
          .map(
            (i) => `
        <div class="brief-row due">
          <div class="main">
            <div class="title">${esc(i.person ? i.person + " @ " : "")}${esc(i.company)}</div>
            <div class="sub">Sent ${esc(i.sent_on)} via ${esc(i.channel)}${
              safeUrl(i.link)
                ? ` · <a href="${esc(safeUrl(i.link))}" target="_blank" rel="noopener">open</a>`
                : ""
            }</div>
          </div>
          <div class="actions">
            <button class="btn btn-outline btn-small" data-followup-draft="${esc(i.id)}">Draft follow-up</button>
            <button class="btn btn-primary btn-small" data-status="followed_up" data-id="${esc(i.id)}">Followed up</button>
            <button class="btn btn-outline btn-small" data-status="replied" data-id="${esc(i.id)}">They replied</button>
          </div>
        </div>`,
          )
          .join("")
      : empty("Nothing due today.");

    document.querySelectorAll("[data-followup-draft]").forEach((btn) => {
      const item = items.find((i) => i.id === btn.dataset.followupDraft);
      btn.addEventListener("click", () =>
        startMessage(item.company, item.person, "", "followup"),
      );
    });
  }

  function renderRoles(roles, total) {
    $("roles-count").textContent = `(${total})`;
    $("roles").innerHTML = roles.length
      ? roles
          .map((r) => {
            const href = r.job_key
              ? "/job/" + encodeURIComponent(r.job_key)
              : safeUrl(r.url);
            return `
        <div class="brief-row">
          <div class="main">
            <div class="title">${esc(r.role)}
              ${r.from_watchlist ? '<span class="tag watch">watchlist</span>' : ""}
              <span class="tag">${esc(r.recommendation)}</span>
            </div>
            <div class="sub">${esc(r.company)} · ${esc(r.location || "—")} · via ${esc(r.source)}</div>
          </div>
          <span class="score">${esc(r.score)}</span>
          <div class="actions">
            ${href ? `<a class="btn btn-primary btn-small" href="${esc(href)}" ${r.job_key ? "" : 'target="_blank" rel="noopener"'}>${r.job_key ? (r.has_kit ? "Open kit" : "Open") : "Posting"}</a>` : ""}
            <button class="btn btn-outline btn-small" data-msg-company="${esc(r.company)}">Message someone there</button>
          </div>
        </div>`;
          })
          .join("")
      : empty(
          "No new roles since yesterday. Run the daily pipeline, or spend today on outreach.",
        );

    document.querySelectorAll("[data-msg-company]").forEach((btn) =>
      btn.addEventListener("click", () => startMessage(btn.dataset.msgCompany)),
    );
  }

  function renderLeads(leads, total) {
    $("leads-count").textContent = `(${total} waiting)`;
    $("leads").innerHTML = leads.length
      ? leads
          .map((l) => {
            const people =
              "https://www.linkedin.com/search/results/people/?keywords=" +
              encodeURIComponent(l.name + " engineer");
            return `
        <div class="brief-row">
          <div class="main">
            <div class="title">${esc(l.name)}
              <span class="tag ${l.kind === "funding" ? "funding" : ""}">${l.kind === "funding" ? "just funded" : "YC · hiring"}</span>
            </div>
            <div class="sub">${esc(l.detail)}${l.about ? " · " + esc(l.about) : ""}</div>
          </div>
          <div class="actions">
            ${safeUrl(l.url) ? `<a class="btn btn-outline btn-small" href="${esc(safeUrl(l.url))}" target="_blank" rel="noopener">${l.kind === "funding" ? "Article" : "YC page"}</a>` : ""}
            ${safeUrl(l.website) ? `<a class="btn btn-outline btn-small" href="${esc(safeUrl(l.website))}" target="_blank" rel="noopener">Website</a>` : ""}
            <a class="btn btn-outline btn-small" href="${esc(people)}" target="_blank" rel="noopener">Find people</a>
            <button class="btn btn-primary btn-small" data-lead-msg="${esc(l.id)}">Message</button>
            <button class="btn btn-outline btn-small" data-lead-dismiss="${esc(l.id)}">Not for me</button>
          </div>
        </div>`;
          })
          .join("")
      : empty("No leads yet — press “Refresh leads”.");

    document.querySelectorAll("[data-lead-msg]").forEach((btn) => {
      const lead = leads.find((l) => l.id === btn.dataset.leadMsg);
      btn.addEventListener("click", () => startMessage(lead.name, "", lead.id));
    });
    document.querySelectorAll("[data-lead-dismiss]").forEach((btn) =>
      btn.addEventListener("click", () =>
        post("/api/leads/status", {
          id: btn.dataset.leadDismiss,
          status: "dismissed",
        }).then(load),
      ),
    );
  }

  function renderOpen(items) {
    $("open-count").textContent = `(${items.length})`;
    $("open-outreach").innerHTML = items.length
      ? items
          .map(
            (i) => `
        <div class="brief-row">
          <div class="main">
            <div class="title">${esc(i.person ? i.person + " @ " : "")}${esc(i.company)}</div>
            <div class="sub">Sent ${esc(i.sent_on)} · ${
              i.status === "followed_up"
                ? "followed up " + esc(i.followed_up_on || "")
                : "follow-up due " + esc(i.follow_up_on)
            }</div>
          </div>
          <div class="actions">
            <button class="btn btn-outline btn-small" data-status="replied" data-id="${esc(i.id)}">They replied</button>
            <button class="btn btn-outline btn-small" data-status="closed" data-id="${esc(i.id)}">Close</button>
          </div>
        </div>`,
          )
          .join("")
      : empty("Nothing logged yet. Every message you log comes back here.");
  }

  function wireStatusButtons() {
    document.querySelectorAll("[data-status]").forEach((btn) =>
      btn.addEventListener("click", () =>
        post("/api/outreach/status", {
          id: btn.dataset.id,
          status: btn.dataset.status,
        }).then(load),
      ),
    );
  }

  function load() {
    fetch("/api/brief")
      .then((r) => r.json())
      .then((d) => {
        $("brief-date").textContent = d.date;
        $("week-sent").textContent = d.week.sent;
        $("week-target").textContent = d.week.target;
        renderFollowUps(d.follow_ups);
        renderRoles(d.roles, d.roles_total);
        renderLeads(d.leads, d.leads_total);
        renderOpen(d.open_outreach);
        wireStatusButtons();

        $("linkedin").innerHTML = d.linkedin
          .map(
            (l) =>
              `<a class="chip" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`,
          )
          .join("");

        $("watch-count").textContent = `(${d.watchlist.length})`;
        $("watchlist").innerHTML = d.watchlist
          .map((w) => `<span class="chip">${esc(w.company)} · ${esc(w.ats)}</span>`)
          .join("");
      })
      .catch(() => {
        $("roles").innerHTML = empty("Couldn't load the brief.");
      });
  }

  $("refresh-leads").addEventListener("click", () => {
    const btn = $("refresh-leads");
    btn.disabled = true;
    btn.textContent = "Refreshing…";
    post("/api/leads/refresh")
      .then(({ data }) => {
        btn.textContent = `Refresh leads (+${data.added || 0} new)`;
        load();
      })
      .finally(() => {
        btn.disabled = false;
      });
  });

  $("o-draft-btn").addEventListener("click", () => loadDraft("first"));

  $("o-copy-btn").addEventListener("click", () => {
    navigator.clipboard
      .writeText($("o-draft").value)
      .then(() => ($("o-hint").textContent = "Copied."));
  });

  $("o-log-btn").addEventListener("click", () => {
    post("/api/outreach", {
      company: $("o-company").value,
      person: $("o-person").value,
      link: $("o-link").value,
      channel: $("o-channel").value,
      note: $("o-draft").value,
      lead_id: activeLeadId,
    }).then(({ ok, data }) => {
      if (!ok) {
        $("o-hint").textContent = data.error || "Couldn't save.";
        return;
      }
      activeLeadId = "";
      ["o-company", "o-person", "o-link", "o-draft"].forEach(
        (id) => ($(id).value = ""),
      );
      $("o-hint").textContent = `Logged. Follow-up due ${data.item.follow_up_on}.`;
      load();
    });
  });

  $("w-add").addEventListener("click", () => {
    const btn = $("w-add");
    btn.disabled = true;
    $("w-hint").textContent = "Looking for their careers board…";
    post("/api/watchlist", { value: $("w-value").value })
      .then(({ ok, data }) => {
        $("w-hint").textContent = ok
          ? `Added ${data.company} (${data.ats}) — ${data.open_roles} open roles. Check it is the right company.`
          : data.error || "Couldn't add.";
        if (ok) {
          $("w-value").value = "";
          load();
        }
      })
      .finally(() => {
        btn.disabled = false;
      });
  });

  load();
})();
