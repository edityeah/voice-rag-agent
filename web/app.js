// Dashboard logic: usage, voice cloning, LiveKit call.

const fmt = (s) => {
  s = Math.max(0, Math.floor(s));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
};

async function api(path, opts = {}) {
  const r = await fetch(path, { credentials: "include", ...opts });
  if (r.status === 401) {
    window.location.href = "/";
    return;
  }
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail?.error || err.detail || r.statusText);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.blob();
}

let state = { me: null, room: null, currentSeconds: 0 };

async function refreshMe() {
  state.me = await api("/api/me");
  document.getElementById("userName").textContent = state.me.name || state.me.email;
  if (state.me.picture) document.getElementById("avatar").src = state.me.picture;

  const q = state.me.quota;
  const pct = Math.min(100, (q.seconds_used / q.limit_seconds) * 100);
  document.getElementById("meterFill").style.width = pct + "%";
  document.getElementById("usedLabel").textContent = fmt(q.seconds_used);
  document.getElementById("remainingLabel").textContent = fmt(q.seconds_remaining);
  const reset = new Date(q.resets_at);
  document.getElementById("resetLabel").textContent = reset.toLocaleDateString();

  document.getElementById("callBtn").disabled = q.seconds_remaining <= 0;
}

async function refreshUsage() {
  const rows = await api("/api/usage");
  const ul = document.getElementById("sessionList");
  ul.innerHTML = rows.length === 0
    ? '<li><span>No sessions yet</span></li>'
    : rows.map(r => `<li><span>${new Date(r.started_at).toLocaleString()}</span><span>${fmt(r.duration_seconds)}</span></li>`).join("");
}

// ---------- Voice recording + library ----------
let mediaRecorder = null, recChunks = [], recBlob = null, recStartTime = 0, recTimerHandle = null;
const recBtn = document.getElementById("recBtn");
const stopRecBtn = document.getElementById("stopRecBtn");
const recTimer = document.getElementById("recTimer");
const cloneBtn = document.getElementById("cloneBtn");
const voiceListEl = document.getElementById("voiceList");
const voiceNameInput = document.getElementById("voiceName");

recBtn.onclick = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => recChunks.push(e.data);
    mediaRecorder.onstop = () => {
      recBlob = new Blob(recChunks, { type: "audio/webm" });
      const url = URL.createObjectURL(recBlob);
      const audio = document.getElementById("recPreview");
      audio.src = url;
      audio.hidden = false;
      cloneBtn.disabled = false;
      stream.getTracks().forEach(t => t.stop());
      clearInterval(recTimerHandle);
    };
    mediaRecorder.start();
    recStartTime = Date.now();
    recTimer.textContent = "Recording… 00:00";
    recTimerHandle = setInterval(() => {
      const s = Math.floor((Date.now() - recStartTime) / 1000);
      recTimer.textContent = `Recording… ${fmt(s)}`;
    }, 250);
    recBtn.disabled = true;
    stopRecBtn.disabled = false;
  } catch (e) {
    alert("Could not access microphone: " + e.message);
  }
};

stopRecBtn.onclick = () => {
  mediaRecorder?.stop();
  recBtn.disabled = false;
  stopRecBtn.disabled = true;
  recTimer.textContent = "Sample ready — name it and save.";
};

cloneBtn.onclick = async () => {
  const name = voiceNameInput.value.trim();
  if (!name) {
    alert("Give this voice a name first.");
    return;
  }
  if (!recBlob) return;
  cloneBtn.disabled = true;
  cloneBtn.textContent = "Saving…";
  try {
    const fd = new FormData();
    fd.append("name", name);
    fd.append("sample", recBlob, "sample.webm");
    await api("/api/voices", { method: "POST", body: fd });
    voiceNameInput.value = "";
    recBlob = null;
    document.getElementById("recPreview").hidden = true;
    recTimer.textContent = "";
    await refreshVoices();
    await refreshMe();
  } catch (e) {
    alert("Save failed: " + e.message);
  } finally {
    cloneBtn.textContent = "Save voice";
    cloneBtn.disabled = recBlob == null;
  }
};

async function refreshVoices() {
  const voices = await api("/api/voices");
  if (voices.length === 0) {
    voiceListEl.innerHTML = '<li class="voice-empty">No voices saved yet — record one above.</li>';
    return;
  }
  voiceListEl.innerHTML = voices.map(v => `
    <li class="voice-row ${v.is_active ? 'active' : ''}" data-id="${v.id}">
      <div class="voice-head">
        <strong>${v.name}</strong>
        ${v.is_active ? '<span class="badge-active">In use</span>' : ''}
      </div>
      <div class="row" style="margin-top:8px">
        ${v.has_sample ? `<button class="btn" data-act="sample">▶ Original sample</button>` : ''}
        <input class="preview-text" placeholder="Type something to hear" value="Hello! This is my saved voice." />
        <button class="btn" data-act="preview">🔊 Preview TTS</button>
        ${v.is_active ? '' : `<button class="btn btn-primary" data-act="activate">Use this voice</button>`}
        <button class="btn btn-ghost" data-act="delete">Delete</button>
      </div>
      <audio class="voice-audio" controls hidden></audio>
    </li>
  `).join("");

  voiceListEl.querySelectorAll(".voice-row").forEach(row => {
    const id = row.dataset.id;
    const audioEl = row.querySelector(".voice-audio");
    row.querySelectorAll("[data-act]").forEach(btn => {
      btn.onclick = async () => {
        const act = btn.dataset.act;
        if (act === "sample") {
          audioEl.src = `/api/voices/${id}/sample`;
          audioEl.hidden = false;
          audioEl.play().catch(() => {});
        } else if (act === "preview") {
          const text = row.querySelector(".preview-text").value.trim();
          btn.disabled = true; btn.textContent = "…";
          try {
            const blob = await api(`/api/voices/${id}/preview`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ text }),
            });
            audioEl.src = URL.createObjectURL(blob);
            audioEl.hidden = false;
            audioEl.play();
          } catch (e) { alert("Preview failed: " + e.message); }
          finally { btn.disabled = false; btn.textContent = "🔊 Preview TTS"; }
        } else if (act === "activate") {
          await api(`/api/voices/${id}/activate`, { method: "POST" });
          await refreshVoices();
          await refreshMe();
        } else if (act === "delete") {
          if (!confirm("Delete this voice?")) return;
          await api(`/api/voices/${id}`, { method: "DELETE" });
          await refreshVoices();
          await refreshMe();
        }
      };
    });
  });
}

// ---------- Knowledge base ----------
const kbFiles = document.getElementById("kbFiles");
const kbUploadBtn = document.getElementById("kbUploadBtn");
const kbStatus = document.getElementById("kbStatus");
const kbList = document.getElementById("kbList");

let selectedKbIds = new Set();

async function refreshKb() {
  const docs = await api("/api/kb");
  if (docs.length === 0) {
    kbList.innerHTML = '<li class="kb-empty">No documents yet — upload to talk about them.</li>';
    selectedKbIds = new Set();
    return;
  }
  // Default: select all on first load; preserve selection across refreshes.
  if (selectedKbIds.size === 0) selectedKbIds = new Set(docs.map(d => d.id));
  kbList.innerHTML = docs.map(d => `
    <li class="kb-row ${selectedKbIds.has(d.id) ? 'selected' : ''}" data-id="${d.id}">
      <input type="checkbox" ${selectedKbIds.has(d.id) ? 'checked' : ''} />
      <span class="kb-name">${d.filename}</span>
      <span class="kb-meta">${(d.chars / 1000).toFixed(1)}k chars</span>
      <button class="btn btn-ghost" data-del="${d.id}">✕</button>
    </li>
  `).join("");
  kbList.querySelectorAll(".kb-row").forEach(row => {
    const id = parseInt(row.dataset.id);
    const cb = row.querySelector('input[type="checkbox"]');
    cb.onchange = () => {
      if (cb.checked) { selectedKbIds.add(id); row.classList.add("selected"); }
      else { selectedKbIds.delete(id); row.classList.remove("selected"); }
    };
    row.querySelector("[data-del]").onclick = async (e) => {
      e.stopPropagation();
      if (!confirm("Delete this document?")) return;
      await api(`/api/kb/${id}`, { method: "DELETE" });
      selectedKbIds.delete(id);
      await refreshKb();
    };
  });
}

document.getElementById("kbSelectAll").onclick = () => {
  kbList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.checked = true; cb.dispatchEvent(new Event("change"));
  });
};
document.getElementById("kbSelectNone").onclick = () => {
  kbList.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.checked = false; cb.dispatchEvent(new Event("change"));
  });
};

kbUploadBtn.onclick = async () => {
  if (!kbFiles.files.length) {
    kbStatus.textContent = "Pick at least one file.";
    return;
  }
  kbUploadBtn.disabled = true;
  kbStatus.textContent = "Uploading…";
  try {
    const fd = new FormData();
    for (const f of kbFiles.files) fd.append("files", f);
    const res = await api("/api/kb/upload", { method: "POST", body: fd });
    const skipped = res.skipped?.length
      ? ` (skipped: ${res.skipped.map(s => `${s.filename} — ${s.reason}`).join(", ")})`
      : "";
    kbStatus.textContent = `Added ${res.added.length} document(s)${skipped}`;
    kbFiles.value = "";
    await refreshKb();
  } catch (e) {
    kbStatus.textContent = "Upload failed: " + e.message;
  } finally {
    kbUploadBtn.disabled = false;
  }
};

// ---------- LiveKit call ----------
let lkRoom = null, callStart = 0, timerHandle = null, agentJoined = false, agentWaitTimer = null;
const callBtn = document.getElementById("callBtn");
const hangupBtn = document.getElementById("hangupBtn");
const muteBtn = document.getElementById("muteBtn");
const callStatus = document.getElementById("callStatus");
const callTimer = document.getElementById("callTimer");

let micMuted = false;
muteBtn.onclick = async () => {
  if (!lkRoom) return;
  micMuted = !micMuted;
  await lkRoom.localParticipant.setMicrophoneEnabled(!micMuted);
  muteBtn.textContent = micMuted ? "🔇 Unmute" : "🎤 Mute";
  muteBtn.classList.toggle("btn-primary", micMuted);
};

callBtn.onclick = async () => {
  callBtn.disabled = true;
  callStatus.textContent = "Connecting…";
  try {
    const session = await api("/api/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kb_doc_ids: Array.from(selectedKbIds) }),
    });
    state.room = session.room;
    state.ttl = session.ttl_seconds;

    const room = new LivekitClient.Room({ adaptiveStream: true, dynacast: true });
    agentJoined = false;
    room.on(LivekitClient.RoomEvent.TrackSubscribed, (track, _pub, participant) => {
      if (track.kind === "audio") {
        const el = track.attach();
        el.autoplay = true;
        el.playsInline = true;
        document.body.appendChild(el);
        el.play().catch(() => {});
      }
    });
    room.on(LivekitClient.RoomEvent.ParticipantConnected, (p) => {
      if (!agentJoined) {
        agentJoined = true;
        callStart = Date.now();
        callStatus.textContent = `Connected — speak when ready (${p.identity})`;
        callTimer.classList.add("live");
        hangupBtn.disabled = false;
        clearTimeout(agentWaitTimer);
        timerHandle = setInterval(() => {
          const elapsed = Math.floor((Date.now() - callStart) / 1000);
          callTimer.textContent = fmt(elapsed);
          if (elapsed >= state.ttl) endCall("Time limit reached");
        }, 250);
      }
    });
    await room.connect(session.url, session.token);
    await room.localParticipant.setMicrophoneEnabled(true);
    try { await room.startAudio(); } catch {}
    lkRoom = room;

    callStatus.textContent = "Waiting for agent to join…";
    hangupBtn.disabled = false;
    muteBtn.disabled = false;
    micMuted = false;
    muteBtn.textContent = "🎤 Mute";
    muteBtn.classList.remove("btn-primary");
    agentWaitTimer = setTimeout(() => {
      if (!agentJoined) endCall("Agent did not join — not billed. Check Terminal 2.");
    }, 15000);

    room.on(LivekitClient.RoomEvent.Disconnected, () => endCall("Disconnected"));
  } catch (e) {
    callStatus.textContent = "";
    callBtn.disabled = false;
    alert("Could not start call: " + e.message);
  }
};

hangupBtn.onclick = () => endCall("Ended");

async function endCall(reason) {
  if (!lkRoom) return;
  const elapsed = agentJoined ? Math.floor((Date.now() - callStart) / 1000) : 0;
  const room = state.room;
  try { await lkRoom.disconnect(); } catch {}
  lkRoom = null;
  clearInterval(timerHandle);
  clearTimeout(agentWaitTimer);
  callTimer.classList.remove("live");
  callStatus.textContent = reason;
  hangupBtn.disabled = true;
  muteBtn.disabled = true;
  muteBtn.textContent = "🎤 Mute";
  muteBtn.classList.remove("btn-primary");
  callBtn.disabled = false;
  try {
    await api("/api/session/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room, duration_seconds: elapsed, agent_joined: agentJoined }),
    });
  } catch {}
  await refreshMe();
  await refreshUsage();
}

window.addEventListener("beforeunload", () => {
  if (lkRoom) {
    const elapsed = agentJoined ? Math.floor((Date.now() - callStart) / 1000) : 0;
    navigator.sendBeacon(
      "/api/session/end",
      new Blob([JSON.stringify({ room: state.room, duration_seconds: elapsed, agent_joined: agentJoined })],
        { type: "application/json" })
    );
  }
});

// ---------- Boot ----------
(async () => {
  try {
    await refreshMe();
    await refreshUsage();
    await refreshKb();
    await refreshVoices();
  } catch (e) {
    console.error(e);
  }
})();
