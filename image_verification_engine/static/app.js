(function () {
  const run = document.getElementById("run");
  const status = document.getElementById("status");
  const out = document.getElementById("out");
  const summary = document.getElementById("summary");
  const tableWrap = document.getElementById("table-wrap");
  const progressPanel = document.getElementById("progress-panel");
  const progressFill = document.getElementById("progress-fill");
  const progressDetail = document.getElementById("progress-detail");
  const progressTrack = document.getElementById("progress-track");
  const elapsedBanner = document.getElementById("elapsed-banner");

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function rowTokensSum(parts) {
    if (!parts || !parts.length) return "";
    let t = 0;
    for (const p of parts) {
      const tok = p.tokens || {};
      const tot = tok.total;
      if (typeof tot === "number") t += tot;
    }
    return t || "";
  }

  function rowTokensIo(parts) {
    if (!parts || !parts.length) return "—";
    let pi = 0,
      co = 0;
    for (const p of parts) {
      const b = (p.tokens && p.tokens.bifurcation) || {};
      if (typeof b.prompt_token_count === "number") pi += b.prompt_token_count;
      if (typeof b.candidates_token_count === "number") co += b.candidates_token_count;
    }
    if (!pi && !co) return "—";
    return pi + " / " + co;
  }

  function validCell(r) {
    if (r.error) return '<span class="tag-bad">Error</span>';
    if (r.valid === true) return '<span class="tag-ok">true</span>';
    if (r.valid === false) return '<span class="tag-bad">false</span>';
    return '<span class="tag-unk">unknown</span>';
  }

  function buildRowHtml(r) {
    const media =
      r.media_kind === "error"
        ? "—"
        : r.media_kind === "pdf"
          ? "PDF (" + (r.page_count || 0) + "p)"
          : "Image";
    const notes = r.error || r.notes || "";
    const tokSum = rowTokensSum(r.parts);
    const io = rowTokensIo(r.parts);
    return (
      "<tr><td>" +
      esc(r.row) +
      "</td><td>" +
      validCell(r) +
      "</td><td>" +
      esc(media) +
      "</td><td>" +
      esc(tokSum) +
      "</td><td>" +
      esc(io) +
      "</td><td>" +
      esc(notes) +
      "</td><td><a href=\"" +
      esc(r.url) +
      "\" target=\"_blank\" rel=\"noopener\">link</a></td></tr>"
    );
  }

  async function readNdjsonStream(response, onObj) {
    const reader = response.body && response.body.getReader();
    if (!reader) throw new Error("Streaming not supported");
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        const t = line.trim();
        if (!t) continue;
        onObj(JSON.parse(t));
      }
    }
    const tail = buffer.trim();
    if (tail) onObj(JSON.parse(tail));
  }

  run.addEventListener("click", async () => {
    const fileInput = document.getElementById("csv");
    const url_column = document.getElementById("url_column").value.trim();

    if (!fileInput.files || !fileInput.files[0]) {
      status.textContent = "Choose a CSV file.";
      return;
    }

    const fd = new FormData();
    fd.append("csv", fileInput.files[0]);
    if (url_column) fd.append("url_column", url_column);

    run.disabled = true;
    status.textContent = "Starting…";
    out.hidden = true;
    if (elapsedBanner) {
      elapsedBanner.hidden = true;
      elapsedBanner.textContent = "";
    }
    progressPanel.hidden = false;
    progressFill.style.width = "0%";
    progressDetail.textContent = "";
    if (progressTrack) {
      progressTrack.setAttribute("aria-valuenow", "0");
      progressTrack.setAttribute("aria-valuemax", "100");
    }

    let html =
      "<table><thead><tr><th>Row</th><th>Valid</th><th>Media</th><th>Tokens Σ</th><th>Input / out</th><th>Notes</th><th>URL</th></tr></thead><tbody></tbody></table>";
    tableWrap.innerHTML = html;
    const tbody = tableWrap.querySelector("tbody");

    try {
      const res = await fetch("/api/verify", { method: "POST", body: fd });
      if (!res.ok) {
        const err = await res.json().catch(function () {
          return {};
        });
        status.textContent = err.error || res.statusText;
        progressPanel.hidden = true;
        return;
      }
      await readNdjsonStream(res, function (obj) {
        const ev = obj.event;
        if (ev === "prepare") {
          if (obj.phase === "download" && obj.current != null && obj.rows != null) {
            status.textContent = "Preparing " + obj.current + " / " + obj.rows + "…";
            progressDetail.textContent = obj.url ? "GET " + obj.url : "";
          } else {
            status.textContent = obj.message || "Preparing…";
          }
        } else if (ev === "start") {
          status.textContent =
            "Verifying " + (obj.total_steps || 0) + " screenshot(s) / page(s)…";
          if (progressTrack && obj.total_steps > 0) {
            progressTrack.setAttribute("aria-valuemax", String(obj.total_steps));
          }
        } else if (ev === "progress") {
          const tot = obj.total || 1;
          const step = obj.step || 0;
          const pct = Math.round((100 * step) / tot);
          progressFill.style.width = pct + "%";
          if (progressTrack) progressTrack.setAttribute("aria-valuenow", String(pct));
          progressDetail.textContent = obj.detail || "";
          status.textContent = "Step " + step + " / " + tot;
        } else if (ev === "row") {
          tbody.insertAdjacentHTML("beforeend", buildRowHtml(obj.payload));
          out.hidden = false;
        } else if (ev === "done") {
          const human = obj.elapsed_human != null ? obj.elapsed_human : "";
          const sec = obj.elapsed_sec;
          summary.textContent = JSON.stringify(
            {
              model: obj.model,
              elapsed_sec: obj.elapsed_sec,
              elapsed_human: obj.elapsed_human,
              aggregate_token_hints: obj.aggregate_token_hints,
            },
            null,
            2
          );
          if (elapsedBanner && (human || typeof sec === "number")) {
            elapsedBanner.textContent =
              "Total time (entire run): " +
              (human || (sec != null ? String(sec) + " s" : ""));
            elapsedBanner.hidden = false;
          }
          status.textContent = human ? "Done in " + human + "." : "Done.";
          progressFill.style.width = "100%";
          if (progressTrack) progressTrack.setAttribute("aria-valuenow", "100");
          progressDetail.textContent = "";
        }
      });
    } catch (e) {
      status.textContent = String(e);
    } finally {
      run.disabled = false;
      progressPanel.hidden = true;
    }
  });
})();
