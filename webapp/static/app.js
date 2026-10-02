// ------------------------------------------------------------------
// Shared helpers
// ------------------------------------------------------------------

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function recClass(rec) {
  if (!rec) return "skip";
  const r = rec.toUpperCase();
  if (r.includes("ASAP")) return "asap";
  if (r === "APPLY") return "apply";
  if (r === "CONSIDER") return "consider";
  return "skip";
}

// Follow a background run started by the server: stream its log into
// logEl once a second and call onFinish(ok) when it ends. Used by the
// kit / add-job / resume buttons (the pipeline buttons keep their own
// poller further down).
function followRun(runId, logEl, onFinish) {
  const timer = setInterval(() => {
    fetch(`/api/run/${runId}/status`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          clearInterval(timer);
          onFinish(false);
          return;
        }
        logEl.textContent = data.lines.join("\n");
        logEl.scrollTop = logEl.scrollHeight;
        if (data.status === "done" || data.status === "failed") {
          clearInterval(timer);
          onFinish(data.status === "done");
        }
      })
      .catch(() => {
        clearInterval(timer);
        onFinish(false);
      });
  }, 1000);
}

// POST that starts a run, then follows it. `button` is disabled meanwhile.
function startRun(url, options, logEl, button, onFinish) {
  logEl.classList.remove("hidden");
  logEl.textContent = "Starting...";
  button.disabled = true;

  fetch(url, options)
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        logEl.textContent = "Error: " + data.error;
        button.disabled = false;
        return;
      }
      followRun(data.run_id, logEl, (ok) => {
        button.disabled = false;
        onFinish(ok);
      });
    })
    .catch(() => {
      logEl.textContent = "Couldn't start. Is the server still running?";
      button.disabled = false;
    });
}

// ------------------------------------------------------------------
// Dashboard page
// ------------------------------------------------------------------

const jobListEl = document.getElementById("job-list");

if (jobListEl) {
  let currentRecFilter = "all";
  let currentAppliedFilter = null;
  let currentSearch = "";

  function loadSummary() {
    fetch("/api/summary")
      .then((r) => r.json())
      .then((data) => {
        if (data.error) return;
        document.getElementById("s-tracked").textContent =
          data.tracked_jobs ?? "–";
        document.getElementById("s-queue").textContent =
          data.apply_queue ?? "–";
        document.getElementById("s-asap").textContent = data.apply_asap ?? "–";
        document.getElementById("s-apply").textContent = data.apply ?? "–";
        document.getElementById("s-kits").textContent = data.kits_ready ?? "–";
        document.getElementById("s-applied").textContent = data.applied ?? "–";
        const lu = document.getElementById("last-updated");
        if (lu && data.updated_at)
          lu.textContent = "Last updated: " + data.updated_at;
      })
      .catch(() => {});
  }

  function renderJobs(jobs) {
    if (!jobs.length) {
      jobListEl.innerHTML = '<p class="muted">No jobs match this filter.</p>';
      return;
    }

    jobListEl.innerHTML = jobs
      .map((j) => {
        const rc = recClass(j.recommendation);
        const score =
          j.match_score !== null && j.match_score !== undefined
            ? Math.round(j.match_score)
            : "–";
        const kitTag = j.kit_folder
          ? '<span class="kit-tag">Kit ready</span>'
          : '<span class="kit-tag none">No kit</span>';
        const appliedTag = j.applied
          ? '<span class="applied-tag">Applied</span>'
          : "";

        return `
        <a class="job-card ${j.applied ? "applied" : ""}" href="/job/${encodeURIComponent(j.job_key)}">
          <span class="rec-badge ${rc}">${escapeHtml(j.recommendation || "—")}</span>
          <div class="job-main">
            <div class="role">${escapeHtml(j.role || "Untitled role")}</div>
            <div class="company">${escapeHtml(j.company || "Unknown company")}</div>
            <div class="job-meta">
              <span>${escapeHtml(j.location || "—")}</span>
              <span>${escapeHtml(j.work_mode || "")}</span>
              <span>${escapeHtml(j.stipend || "")}</span>
              ${j.ppo_signal ? `<span>PPO: ${escapeHtml(j.ppo_signal)}</span>` : ""}
            </div>
          </div>
          ${kitTag}
          ${appliedTag}
          <span class="job-score">${score}</span>
        </a>`;
      })
      .join("");
  }

  function loadJobs() {
    jobListEl.innerHTML = '<p class="muted">Loading jobs…</p>';
    const params = new URLSearchParams();
    if (currentRecFilter !== "all")
      params.set("recommendation", currentRecFilter);
    if (currentAppliedFilter) params.set("apply_status", currentAppliedFilter);
    if (currentSearch) params.set("q", currentSearch);

    fetch("/api/jobs?" + params.toString())
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          jobListEl.innerHTML = `<p class="muted">${escapeHtml(data.error)}</p>`;
          return;
        }
        renderJobs(data);
      })
      .catch(() => {
        jobListEl.innerHTML = '<p class="muted">Couldn\'t load jobs.</p>';
      });
  }

  document.querySelectorAll(".filter-btn[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".filter-btn[data-filter]")
        .forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentRecFilter = btn.dataset.filter;
      loadJobs();
    });
  });

  document.querySelectorAll(".filter-btn[data-applied]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const already = btn.classList.contains("active");
      document
        .querySelectorAll(".filter-btn[data-applied]")
        .forEach((b) => b.classList.remove("active"));
      if (already) {
        currentAppliedFilter = null;
      } else {
        btn.classList.add("active");
        currentAppliedFilter = btn.dataset.applied;
      }
      loadJobs();
    });
  });

  let searchTimer = null;
  document.getElementById("search-box").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      currentSearch = e.target.value.trim();
      loadJobs();
    }, 300);
  });

  loadSummary();
  loadJobs();

  // --- Pipeline runner ---

  const logEl = document.getElementById("pipeline-log");
  let pollTimer = null;

  function setStepState(stepId, state) {
    document.querySelectorAll(".step-btn").forEach((btn) => {
      if (
        btn.dataset.step === stepId ||
        (stepId === "all" && btn.classList.contains("run-all"))
      ) {
        btn.classList.remove("running", "done", "failed");
        if (state) btn.classList.add(state);
      }
    });
  }

  function setAllButtonsDisabled(disabled) {
    document
      .querySelectorAll(".step-btn")
      .forEach((btn) => (btn.disabled = disabled));
  }

  function pollRun(runId, stepId) {
    fetch(`/api/run/${runId}/status`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          clearInterval(pollTimer);
          setAllButtonsDisabled(false);
          return;
        }

        logEl.textContent = data.lines.join("\n");
        logEl.scrollTop = logEl.scrollHeight;

        if (data.status === "done") {
          clearInterval(pollTimer);
          setStepState(stepId, "done");
          setAllButtonsDisabled(false);
          loadSummary();
          loadJobs();
        } else if (data.status === "failed") {
          clearInterval(pollTimer);
          setStepState(stepId, "failed");
          setAllButtonsDisabled(false);
        }
      })
      .catch(() => {
        clearInterval(pollTimer);
        setAllButtonsDisabled(false);
      });
  }

  document.querySelectorAll(".step-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const stepId = btn.dataset.step;
      logEl.classList.remove("hidden");
      logEl.textContent = "Starting...";
      setAllButtonsDisabled(true);
      setStepState(stepId, "running");

      fetch(`/api/run/${stepId}`, { method: "POST" })
        .then((r) => r.json())
        .then((data) => {
          if (data.error) {
            logEl.textContent = "Error: " + data.error;
            setAllButtonsDisabled(false);
            return;
          }
          pollTimer = setInterval(() => pollRun(data.run_id, stepId), 1000);
        })
        .catch(() => {
          logEl.textContent = "Couldn't start the pipeline step.";
          setAllButtonsDisabled(false);
        });
    });
  });

  // --- Add a job by hand ---

  const njSubmit = document.getElementById("nj-submit");

  njSubmit.addEventListener("click", () => {
    const field = (id) => document.getElementById(id).value.trim();
    const body = {
      company: field("nj-company"),
      title: field("nj-title"),
      url: field("nj-url"),
      location: field("nj-location"),
      stipend: field("nj-stipend"),
      description: field("nj-description"),
    };

    if (!body.description && !body.url) {
      alert("Paste the job description, or give the posting URL.");
      return;
    }

    startRun(
      "/api/jobs/new",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      logEl,
      njSubmit,
      (ok) => {
        if (!ok) return;
        [
          "nj-company",
          "nj-title",
          "nj-url",
          "nj-location",
          "nj-stipend",
          "nj-description",
        ].forEach((id) => (document.getElementById(id).value = ""));
        loadSummary();
        loadJobs();
      },
    );
  });

  // --- Profile + resume upload ---

  function loadProfile() {
    fetch("/api/profile")
      .then((r) => r.json())
      .then((data) => {
        document.getElementById("career-brain").textContent =
          data.career_brain || "No profile found.";
        document.getElementById("resume-updated").textContent =
          data.resume_updated_at
            ? "Last resume update: " + data.resume_updated_at.replace("T", " ")
            : "";
        document.getElementById("nj-hint").textContent = data.firecrawl
          ? "Firecrawl is on: a URL alone is enough."
          : "No Firecrawl key: paste the description (URL-only works for simple pages).";
      })
      .catch(() => {});
  }

  const resumeSubmit = document.getElementById("resume-submit");

  resumeSubmit.addEventListener("click", () => {
    const file = document.getElementById("resume-file").files[0];
    if (!file) {
      alert("Choose a resume file first.");
      return;
    }
    const form = new FormData();
    form.append("resume", file);

    startRun(
      "/api/profile/resume",
      { method: "POST", body: form },
      logEl,
      resumeSubmit,
      (ok) => {
        if (ok) loadProfile();
      },
    );
  });

  loadProfile();
}

// ------------------------------------------------------------------
// Job detail page
// ------------------------------------------------------------------

const detailEl = document.getElementById("job-detail");

if (detailEl) {
  const jobKey = detailEl.dataset.jobKey;

  function renderDetail(job, kit) {
    const rc = recClass(job.recommendation);
    const score =
      job.match_score !== null && job.match_score !== undefined
        ? Math.round(job.match_score)
        : "–";

    let html = `
    <div class="detail-header">
      <span class="rec-badge ${rc}">${escapeHtml(job.recommendation || "—")}</span>
      <h1>${escapeHtml(job.role || "Untitled role")}</h1>
      <div class="company">${escapeHtml(job.company || "Unknown company")} · Score ${score}</div>

      <div class="detail-meta-grid">
        <div class="item"><span class="k">Location</span>${escapeHtml(job.location || "—")}</div>
        <div class="item"><span class="k">Work Mode</span>${escapeHtml(job.work_mode || "—")}</div>
        <div class="item"><span class="k">Stipend</span>${escapeHtml(job.stipend || "—")}</div>
        <div class="item"><span class="k">Duration</span>${escapeHtml(job.duration || "—")}</div>
        <div class="item"><span class="k">PPO Signal</span>${escapeHtml(job.ppo_signal || "—")}</div>
        <div class="item"><span class="k">Source</span>${escapeHtml(job.source || "—")}</div>
        <div class="item"><span class="k">Eligibility</span>${escapeHtml(job.eligibility_status || "—")}</div>
        <div class="item"><span class="k">Availability</span>${escapeHtml(job.availability_status || "—")}</div>
      </div>

      ${job.hard_blockers ? `<p class="muted" style="color:var(--asap); margin-top:10px;"><strong>Hard blockers:</strong> ${escapeHtml(job.hard_blockers)}</p>` : ""}
      ${job.red_flags ? `<p class="muted" style="margin-top:6px;"><strong>Red flags:</strong> ${escapeHtml(job.red_flags)}</p>` : ""}

      
      <div class="detail-actions">
        ${/^https?:\/\//i.test(job.url || "") ? `<a class="btn btn-outline" href="${escapeHtml(job.url)}" target="_blank" rel="noopener">Open job posting ↗</a>` : ""}
        <button class="btn ${job.applied ? "btn-outline" : "btn-success"}" id="mark-applied-btn">
          ${job.applied ? "Mark as Not Applied" : "Mark as Applied"}
        </button>
        <button class="btn ${kit ? "btn-outline" : "btn-primary"}" id="generate-kit-btn">
          ${kit ? "Regenerate kit" : "Generate application kit"}
        </button>
      </div>
      <pre id="kit-log" class="pipeline-log run-log hidden"></pre>
    </div>`;

    if (kit) {
      if (kit.resume_bullets && kit.resume_bullets.length) {
        html += `
        <div class="kit-section">
          <h3>Tailored Resume Bullets</h3>
          <ul class="bullet-list">
            ${kit.resume_bullets.map((b) => `<li>${escapeHtml(b)}</li>`).join("")}
          </ul>
        </div>`;
      }

      if (kit.cover_letter) {
        html += `
        <div class="kit-section">
          <button class="copy-btn" data-copy-target="cover-letter-text">Copy</button>
          <h3>Cover Letter</h3>
          <div class="cover-letter-text" id="cover-letter-text">${escapeHtml(kit.cover_letter)}</div>
        </div>`;
      }

      const qaEntries = Object.entries(kit.screening_answers || {});
      if (qaEntries.length) {
        html += `<div class="kit-section"><h3>Screening Answers</h3>`;
        for (const [q, a] of qaEntries) {
          const label = q
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase());
          html += `<div class="qa-item"><div class="q">${escapeHtml(label)}</div><div class="a">${escapeHtml(a)}</div></div>`;
        }
        html += `</div>`;
      }

      if (
        (kit.skills_to_highlight && kit.skills_to_highlight.length) ||
        (kit.skill_gaps && kit.skill_gaps.length)
      ) {
        html += `<div class="kit-section"><h3>Skills</h3>`;
        if (kit.skills_to_highlight && kit.skills_to_highlight.length) {
          html += `<p class="muted">Highlight these:</p><div class="tag-list">${kit.skills_to_highlight
            .map((s) => `<span class="tag-pill">${escapeHtml(s)}</span>`)
            .join("")}</div>`;
        }
        if (kit.skill_gaps && kit.skill_gaps.length) {
          html += `<p class="muted" style="margin-top:10px;">Gaps to be ready to discuss:</p><div class="tag-list">${kit.skill_gaps
            .map((s) => `<span class="tag-pill gap">${escapeHtml(s)}</span>`)
            .join("")}</div>`;
        }
        html += `</div>`;
      }

      if (kit.application_strategy && kit.application_strategy.length) {
        html += `
        <div class="kit-section">
          <h3>Application Strategy</h3>
          <ul class="bullet-list">
            ${kit.application_strategy.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}
          </ul>
        </div>`;
      }
    } else {
      html += `<div class="no-kit-notice">No application kit has been generated for this job yet. The daily pipeline only builds kits for APPLY / APPLY ASAP jobs — use "Generate application kit" above to build one for this job now.</div>`;
    }

    detailEl.innerHTML = html;

    document
      .getElementById("mark-applied-btn")
      .addEventListener("click", () => {
        const nowApplied = !job.applied;
        fetch(`/api/job/${encodeURIComponent(jobKey)}/mark_applied`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ applied: nowApplied }),
        })
          .then((r) => r.json())
          .then((data) => {
            if (data.error) {
              alert(data.error);
              return;
            }
            job.applied = nowApplied;
            renderDetail(job, kit);
          })
          .catch(() => alert("Couldn't save. Try again."));
      });

    const kitBtn = document.getElementById("generate-kit-btn");

    kitBtn.addEventListener("click", () => {
      if (
        kit &&
        !confirm("Replace the existing kit with a newly generated one?")
      ) {
        return;
      }
      startRun(
        `/api/job/${encodeURIComponent(jobKey)}/generate_kit`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ force: Boolean(kit) }),
        },
        document.getElementById("kit-log"),
        kitBtn,
        (ok) => {
          if (ok) loadDetail();
        },
      );
    });

    document.querySelectorAll("[data-copy-target]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = document.getElementById(btn.dataset.copyTarget);
        navigator.clipboard.writeText(target.textContent).then(() => {
          btn.textContent = "Copied!";
          setTimeout(() => (btn.textContent = "Copy"), 1200);
        });
      });
    });
  }

  function loadDetail() {
    fetch(`/api/job/${encodeURIComponent(jobKey)}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          detailEl.innerHTML = `<p class="muted">${escapeHtml(data.error)}</p>`;
          return;
        }
        renderDetail(data.job, data.kit);
      })
      .catch(() => {
        detailEl.innerHTML = '<p class="muted">Couldn\'t load this job.</p>';
      });
  }

  loadDetail();
}
