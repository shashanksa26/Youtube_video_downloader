(() => {
  const inspectForm = document.getElementById("inspect-form");
  const urlInput = document.getElementById("youtube-url");
  const inspectBtn = document.getElementById("inspect-btn");
  const inspectStatus = document.getElementById("inspect-status");

  const videoSection = document.getElementById("video-section");
  const videoThumb = document.getElementById("video-thumb");
  const videoTitle = document.getElementById("video-title");
  const videoDuration = document.getElementById("video-duration");
  const qualityOptions = document.getElementById("quality-options");
  const downloadForm = document.getElementById("download-form");
  const downloadBtn = document.getElementById("download-btn");

  const progressSection = document.getElementById("progress-section");
  const progressHeading = document.getElementById("progress-heading");
  const progressLabel = document.getElementById("progress-label");
  const progressPct = document.getElementById("progress-pct");
  const progressBar = document.getElementById("download-progress");
  const progressBarText = document.getElementById("progress-bar-text");
  const downloadStatus = document.getElementById("download-status");
  const cancelBtn = document.getElementById("cancel-btn");
  const fileDownloadLink = document.getElementById("file-download-link");

  let activeUrl = "";
  let activeTaskId = null;
  let pollTimer = null;

  // Accessible error announcement & aria-invalid synchronization
  const announcer = document.createElement("div");
  announcer.setAttribute("aria-live", "polite");
  announcer.classList.add("visually-hidden");
  document.body.append(announcer);

  let announceTimer;
  let announcedField;
  const flagged = new WeakSet();
  const announced = new WeakSet();

  const linkError = (el, shown) => {
    const errorId = el.dataset.error;
    if (!errorId) return;
    const ids = (el.getAttribute("aria-describedby") || "")
      .split(/\s+/)
      .filter((id) => id && id !== errorId);
    if (shown) ids.push(errorId);
    if (ids.length) el.setAttribute("aria-describedby", ids.join(" "));
    else el.removeAttribute("aria-describedby");
  };

  const spokenText = (node) => {
    const copy = node.cloneNode(true);
    copy.querySelectorAll('[aria-hidden="true"]').forEach((n) => n.remove());
    copy
      .querySelectorAll('[role="img"][aria-label]')
      .forEach((n) => n.replaceWith(`${n.getAttribute("aria-label")}: `));
    return copy.textContent.replace(/\s+/g, " ").trim();
  };

  const announceError = (el) => {
    const error = document.getElementById(el.dataset.error);
    if (!error) return;
    const label = el.labels?.[0] ? `${spokenText(el.labels[0])}: ` : "";
    clearTimeout(announceTimer);
    announcer.textContent = "";
    announcedField = el;
    announceTimer = setTimeout(() => {
      announcer.textContent = label + spokenText(error);
    }, 500);
  };

  const syncAria = (el, announce = false) => {
    if (!el.matches?.("input, select, textarea")) return;
    const invalid = el.matches(":user-invalid") || el.classList.contains("user-invalid-fallback");
    if (invalid) {
      if (announce && !announced.has(el)) {
        announceError(el);
        announced.add(el);
      }
      el.setAttribute("aria-invalid", "true");
      linkError(el, true);
      flagged.add(el);
    } else if (flagged.has(el) || el.getAttribute("aria-invalid") !== "true") {
      el.setAttribute("aria-invalid", "false");
      linkError(el, false);
      flagged.delete(el);
      announced.delete(el);
      if (announcedField === el) {
        clearTimeout(announceTimer);
        announcer.textContent = "";
      }
    }
  };

  syncAria(urlInput);
  urlInput.addEventListener("blur", () => syncAria(urlInput, true));
  urlInput.addEventListener("input", () => {
    urlInput.classList.remove("user-invalid-fallback");
    urlInput.setCustomValidity("");
    syncAria(urlInput);
  });
  urlInput.addEventListener("invalid", () => {
    announced.add(urlInput);
    syncAria(urlInput);
  });

  const formatDuration = (seconds) => {
    if (seconds == null || Number.isNaN(Number(seconds))) return "Duration unknown";
    const total = Math.max(0, Math.round(Number(seconds)));
    const hrs = Math.floor(total / 3600);
    const mins = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return hrs > 0 ? `${hrs}:${pad(mins)}:${pad(secs)}` : `${mins}:${pad(secs)}`;
  };

  const setStatus = (el, message, kind = "") => {
    el.textContent = message;
    el.classList.remove("is-error", "is-success");
    if (kind) el.classList.add(kind);
  };

  const buildQualityOption = (value, label, detail, checked) => {
    const wrapper = document.createElement("label");
    wrapper.className = "quality-option";

    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "resolution";
    radio.value = value;
    radio.checked = checked;

    const details = document.createElement("span");
    details.className = "quality-details";

    const title = document.createElement("span");
    title.className = "quality-name";
    title.textContent = label;

    const sub = document.createElement("span");
    sub.className = "quality-sub";
    sub.textContent = detail;

    details.append(title, sub);
    wrapper.append(radio, details);
    return wrapper;
  };

  const renderFormats = (data) => {
    videoTitle.textContent = data.title || "Untitled Video";
    videoDuration.textContent = `Duration: ${formatDuration(data.duration)}`;

    if (data.thumbnail) {
      videoThumb.src = data.thumbnail;
      videoThumb.alt = `Thumbnail for ${data.title || "video"}`;
      videoThumb.hidden = false;
    } else {
      videoThumb.removeAttribute("src");
      videoThumb.alt = "";
      videoThumb.hidden = true;
    }

    qualityOptions.replaceChildren();
    qualityOptions.append(
      buildQualityOption("best", "Best Available", "Highest resolution + best audio", true)
    );

    for (const fmt of data.formats || []) {
      const parts = [];
      if (fmt.fps) parts.push(`${fmt.fps} fps`);
      if (fmt.filesize_mb != null) parts.push(`~${fmt.filesize_mb} MB`);
      parts.push(fmt.has_audio ? "Combined stream" : "Video + best audio");
      qualityOptions.append(
        buildQualityOption(fmt.resolution, fmt.resolution, parts.join(" · "), false)
      );
    }

    videoSection.hidden = false;
    videoTitle.focus();
  };

  const stopPolling = () => {
    if (pollTimer !== null) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  };

  const resetProgress = () => {
    stopPolling();
    progressBar.removeAttribute("value");
    progressBar.removeAttribute("max");
    progressLabel.textContent = "Queued…";
    progressPct.textContent = "";
    progressBarText.textContent = "Queued…";
    fileDownloadLink.hidden = true;
    fileDownloadLink.setAttribute("href", "#");
    setStatus(downloadStatus, "Waiting for worker to start…");
  };

  const formatSpeed = (speedMbS) => {
    if (typeof speedMbS !== "number" || Number.isNaN(speedMbS) || speedMbS <= 0) return null;
    if (speedMbS < 1) {
      return `${Math.round(speedMbS * 1024)} KB/s`;
    }
    return `${speedMbS.toFixed(2)} MB/s`;
  };

  const formatBarTelemetry = (data) => {
    const parts = [];
    if (typeof data.progress === "number") {
      parts.push(`${data.progress.toFixed(1)}%`);
    }
    if (typeof data.downloaded_mb === "number" && typeof data.total_mb === "number") {
      parts.push(`${data.downloaded_mb.toFixed(2)} / ${data.total_mb.toFixed(2)} MB`);
    } else if (typeof data.downloaded_mb === "number") {
      parts.push(`${data.downloaded_mb.toFixed(2)} MB`);
    } else if (typeof data.total_mb === "number") {
      parts.push(`Total: ${data.total_mb.toFixed(2)} MB`);
    }
    const speedText = formatSpeed(data.speed_mb_s);
    if (speedText) {
      parts.push(speedText);
    }
    if (parts.length === 0) {
      return data.stage || data.status || "Working…";
    }
    return parts.join(" · ");
  };

  const pollStatus = async (taskId) => {
    try {
      const res = await fetch(`/api/v1/status/${encodeURIComponent(taskId)}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Status check failed (${res.status})`);
      }

      const data = await res.json();
      const stageText = data.stage || data.status;
      progressLabel.textContent = stageText;

      if (typeof data.progress === "number") {
        progressBar.max = 100;
        progressBar.value = data.progress;
        progressPct.textContent = `${data.progress.toFixed(1)}%`;
      } else {
        progressBar.removeAttribute("value");
        progressBar.removeAttribute("max");
        progressPct.textContent = "";
      }

      progressBarText.textContent = formatBarTelemetry(data);

      if (data.status === "completed") {
        activeTaskId = null;
        progressBar.max = 100;
        progressBar.value = 100;
        progressPct.textContent = "100%";
        const sizeNote = typeof data.total_mb === "number" ? ` · ${data.total_mb.toFixed(2)} MB` : "";
        progressBarText.textContent = `100%${sizeNote} · Complete`;
        cancelBtn.hidden = true;
        fileDownloadLink.href = data.download_url;
        fileDownloadLink.hidden = false;
        setStatus(downloadStatus, "Merge complete. Click Save MP4 File to download.", "is-success");
        downloadBtn.disabled = false;
        downloadBtn.textContent = "Download MP4";
        return;
      }

      if (data.status === "cancelled") {
        activeTaskId = null;
        progressBar.max = 100;
        progressBar.value = 0;
        progressPct.textContent = "";
        progressBarText.textContent = "Cancelled";
        cancelBtn.hidden = true;
        setStatus(downloadStatus, "Download cancelled.");
        downloadBtn.disabled = false;
        downloadBtn.textContent = "Download MP4";
        return;
      }

      if (data.status === "failed") {
        activeTaskId = null;
        progressBar.max = 100;
        progressBar.value = 0;
        progressPct.textContent = "";
        progressBarText.textContent = "Failed";
        cancelBtn.hidden = true;
        setStatus(downloadStatus, data.error || "Download failed.", "is-error");
        downloadBtn.disabled = false;
        downloadBtn.textContent = "Download MP4";
        return;
      }

      setStatus(downloadStatus, `${stageText}…`);
      pollTimer = setTimeout(() => pollStatus(taskId), 800);
    } catch (err) {
      activeTaskId = null;
      cancelBtn.hidden = true;
      setStatus(downloadStatus, err.message, "is-error");
      downloadBtn.disabled = false;
      downloadBtn.textContent = "Download MP4";
    }
  };

  inspectForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (!urlInput.checkValidity()) {
      urlInput.classList.add("user-invalid-fallback");
      syncAria(urlInput, true);
      urlInput.focus();
      return;
    }

    const rawUrl = urlInput.value.trim();
    activeUrl = rawUrl;
    inspectBtn.disabled = true;
    inspectBtn.textContent = "Fetching…";
    setStatus(inspectStatus, "Fetching available video formats…");
    videoSection.hidden = true;
    progressSection.hidden = true;
    stopPolling();

    try {
      const res = await fetch(`/api/v1/formats?url=${encodeURIComponent(rawUrl)}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Failed to inspect URL (${res.status})`);
      }
      const data = await res.json();
      setStatus(inspectStatus, `Found ${data.formats.length} video resolutions.`, "is-success");
      renderFormats(data);
    } catch (err) {
      setStatus(inspectStatus, err.message, "is-error");
    } finally {
      inspectBtn.disabled = false;
      inspectBtn.textContent = "Fetch Qualities";
    }
  });

  downloadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!activeUrl) return;

    const selected = downloadForm.querySelector('input[name="resolution"]:checked');
    const resolution = selected ? selected.value : "best";

    downloadBtn.disabled = true;
    downloadBtn.textContent = "Processing…";
    progressSection.hidden = false;
    resetProgress();
    cancelBtn.hidden = false;
    cancelBtn.disabled = false;
    cancelBtn.textContent = "Cancel Download";
    progressHeading.focus();

    try {
      const res = await fetch("/api/v1/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: activeUrl, resolution }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Failed to queue download (${res.status})`);
      }

      const data = await res.json();
      activeTaskId = data.task_id;
      pollStatus(data.task_id);
    } catch (err) {
      activeTaskId = null;
      cancelBtn.hidden = true;
      setStatus(downloadStatus, err.message, "is-error");
      downloadBtn.disabled = false;
      downloadBtn.textContent = "Download MP4";
    }
  });

  cancelBtn.addEventListener("click", async () => {
    if (!activeTaskId) return;
    const targetTaskId = activeTaskId;
    cancelBtn.disabled = true;
    cancelBtn.textContent = "Cancelling…";
    setStatus(downloadStatus, "Cancelling download…");

    try {
      const res = await fetch(`/api/v1/cancel/${encodeURIComponent(targetTaskId)}`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Failed to cancel download (${res.status})`);
      }
      const data = await res.json();
      if (data.status === "cancelled") {
        stopPolling();
        activeTaskId = null;
        progressBar.max = 100;
        progressBar.value = 0;
        progressPct.textContent = "";
        progressLabel.textContent = "Cancelled";
        progressBarText.textContent = "Cancelled";
        cancelBtn.hidden = true;
        setStatus(downloadStatus, "Download cancelled.");
        downloadBtn.disabled = false;
        downloadBtn.textContent = "Download MP4";
      }
    } catch (err) {
      setStatus(downloadStatus, err.message, "is-error");
      cancelBtn.disabled = false;
      cancelBtn.textContent = "Cancel Download";
    }
  });
})();
