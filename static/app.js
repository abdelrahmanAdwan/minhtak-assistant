/* منحتك Assistant — the web client.
 *
 * Two pieces of state live here:
 *   sessionId  the server-side conversation (holds the model's memory + the
 *              uploaded documents). Kept in localStorage so a refresh resumes.
 *   transcript the VISIBLE conversation, also in localStorage. The server may
 *              restart and lose its half; the user's half survives, and we say
 *              so honestly instead of pretending nothing happened.
 */

const API = "";                       // same origin: the API serves this page
const LS_SESSION = "minhtak.session";
const LS_TRANSCRIPT = "minhtak.transcript";

const el = {
  messages: document.getElementById("messages"),
  welcome: document.getElementById("welcome"),
  form: document.getElementById("chatForm"),
  input: document.getElementById("input"),
  send: document.getElementById("sendBtn"),
  upload: document.getElementById("uploadBtn"),
  file: document.getElementById("fileInput"),
  newChat: document.getElementById("newChatBtn"),
  banner: document.getElementById("errorBanner"),
  bannerText: document.getElementById("errorText"),
  bannerClose: document.getElementById("errorClose"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  docBar: document.getElementById("docBar"),
  docList: document.getElementById("docList"),
  suggestions: document.getElementById("suggestions"),
};

let sessionId = localStorage.getItem(LS_SESSION) || null;
let transcript = readTranscript();
let busy = false;

/* ------------------------------------------------------------------ utils */

function readTranscript() {
  try {
    const raw = localStorage.getItem(LS_TRANSCRIPT);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];                       // corrupt storage must never block the app
  }
}

function saveTranscript() {
  try {
    localStorage.setItem(LS_TRANSCRIPT, JSON.stringify(transcript.slice(-60)));
  } catch {
    /* quota or private mode — the conversation still works, it just won't resume */
  }
}

function showError(message) {
  // A blank banner tells the user nothing and looks like a rendering bug.
  el.bannerText.textContent = message || "حدث خطأ غير متوقع. حاول مرة أخرى.";
  el.banner.hidden = false;
}

function clearError() {
  el.banner.hidden = true;
}

function setStatus(state, text) {
  el.statusDot.className = "dot" + (state ? " " + state : "");
  el.statusText.textContent = text;
}

function scrollToEnd() {
  el.messages.scrollTop = el.messages.scrollHeight;
}

/* --------------------------------------------------------------- rendering */

function hideWelcome() {
  if (el.welcome) el.welcome.style.display = "none";
}

/* The model replies in markdown (bold, bullets). We render a deliberately tiny
 * subset by BUILDING DOM NODES — never innerHTML — so model output can carry
 * no markup into the page. Anything outside the subset stays literal text. */
function appendInline(target, text) {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let cursor = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      target.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    }
    const token = match[0];
    const node = document.createElement(token.startsWith("**") ? "strong" : "code");
    node.textContent = token.startsWith("**") ? token.slice(2, -2) : token.slice(1, -1);
    target.appendChild(node);
    cursor = match.index + token.length;
  }
  if (cursor < text.length) {
    target.appendChild(document.createTextNode(text.slice(cursor)));
  }
}

function renderRich(container, raw) {
  let list = null;
  let paragraph = null;
  String(raw == null ? "" : raw).split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim();
    const bullet = trimmed.match(/^(?:[*\-•]|\d+[.)])\s+(.*)$/);
    if (bullet) {
      paragraph = null;
      const ordered = /^\d/.test(trimmed);
      if (!list || list.tagName !== (ordered ? "OL" : "UL")) {
        list = document.createElement(ordered ? "ol" : "ul");
        container.appendChild(list);
      }
      const item = document.createElement("li");
      appendInline(item, bullet[1]);
      list.appendChild(item);
      return;
    }
    list = null;
    if (!trimmed) {
      paragraph = null;
      return;
    }
    if (paragraph) {
      paragraph.appendChild(document.createElement("br"));
    } else {
      paragraph = document.createElement("p");
      container.appendChild(paragraph);
    }
    appendInline(paragraph, trimmed);
  });
}

function renderMessage(entry, persist = true) {
  hideWelcome();
  const wrap = document.createElement("div");
  wrap.className = "msg " + (entry.role === "user" ? "user" : "bot");

  const bubble = document.createElement("div");
  bubble.className = "bubble" + (entry.kind === "note" ? " note" : "");
  if (entry.role === "bot" && entry.kind !== "note") {
    renderRich(bubble, entry.text);
  } else {
    bubble.textContent = entry.text;   // user text and notes are literal
  }
  wrap.appendChild(bubble);

  if (entry.trace && entry.trace.length) wrap.appendChild(renderTrace(entry.trace));

  el.messages.appendChild(wrap);
  scrollToEnd();

  if (persist) {
    transcript.push(entry);
    saveTranscript();
  }
}

const TOOL_LABELS = {
  search_scholarships: "🔎 بحث في الكتالوج",
  browse_catalogue: "📚 تصفّح الكتالوج",
  get_scholarship_details: "📄 تفاصيل منحة",
  get_weather: "🌤️ الطقس",
  calculate: "🧮 حساب",
  search_uploaded_documents: "📎 بحث في ملفك",
};

function renderTrace(trace) {
  const box = document.createElement("div");
  box.className = "trace";
  trace.forEach((step) => {
    const chip = document.createElement("span");
    chip.className = "trace-chip" + (step.ok ? "" : " failed");
    const label = TOOL_LABELS[step.tool] || step.tool;
    chip.append(document.createTextNode(label + " · "));
    const detail = document.createElement("code");
    detail.textContent = step.summary || "";
    chip.appendChild(detail);
    chip.title = JSON.stringify(step.args || {}, null, 1);
    box.appendChild(chip);
  });
  return box;
}

function showTyping() {
  hideWelcome();
  const wrap = document.createElement("div");
  wrap.className = "msg bot";
  wrap.id = "typing";
  wrap.innerHTML =
    '<div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div>';
  el.messages.appendChild(wrap);
  scrollToEnd();
}

function hideTyping() {
  document.getElementById("typing")?.remove();
}

function renderDocuments(documents) {
  if (!documents || !documents.length) {
    el.docBar.hidden = true;
    el.docList.textContent = "";
    return;
  }
  el.docList.textContent = "";
  documents.forEach((name) => {
    const pill = document.createElement("span");
    pill.className = "doc-pill";
    pill.textContent = "📄 " + name;
    el.docList.appendChild(pill);
  });
  el.docBar.hidden = false;
}

/* ------------------------------------------------------------------- HTTP */

async function callApi(path, options = {}) {
  let response;
  try {
    response = await fetch(API + path, options);
  } catch {
    // A network failure is not the assistant being wrong — say which it is.
    throw new Error("تعذّر الاتصال بالخادم. تحقّق من اتصالك بالإنترنت.");
  }
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    throw new Error((data && data.message) || "حدث خطأ في الخادم. حاول مرة أخرى.");
  }
  return data;
}

/* ------------------------------------------------------------------ flows */

async function sendMessage(text) {
  if (busy || !text.trim()) return;
  busy = true;
  el.send.disabled = true;
  clearError();

  renderMessage({ role: "user", text });
  el.input.value = "";
  autoGrow();
  showTyping();

  try {
    const data = await callApi("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
    });
    hideTyping();

    if (data.new_session) {
      // The server forgot (restart or TTL) — the user's transcript is intact,
      // but the model's memory of it is not. Never hide that.
      renderMessage({
        role: "bot", kind: "note",
        text: "انتهت صلاحية الجلسة السابقة على الخادم، فبدأنا جلسة جديدة. " +
              "إن كنت قد رفعت ملفًا من قبل، أعد رفعه.",
      });
    }
    sessionId = data.session_id;
    localStorage.setItem(LS_SESSION, sessionId);

    renderMessage({ role: "bot", text: data.reply, trace: data.trace });
    renderDocuments(data.documents);
    setStatus("ok", "متصل");
  } catch (error) {
    hideTyping();
    showError(error.message);
    setStatus("bad", "تعذّر الاتصال");
  } finally {
    busy = false;
    el.send.disabled = !el.input.value.trim();
    el.input.focus();
  }
}

async function uploadFile(file) {
  if (busy || !file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showError("يُقبل ملف PDF فقط.");
    return;
  }
  busy = true;
  clearError();
  renderMessage({ role: "user", kind: "note", text: "📎 رفع الملف: " + file.name });
  showTyping();

  const body = new FormData();
  body.append("file", file);
  if (sessionId) body.append("session_id", sessionId);

  try {
    const data = await callApi("/api/documents", { method: "POST", body });
    hideTyping();
    sessionId = data.session_id;
    localStorage.setItem(LS_SESSION, sessionId);
    renderDocuments(data.documents);
    renderMessage({
      role: "bot", kind: "note",
      text: `تمت قراءة «${data.filename}» وفهرسته في ${data.chunks} مقطعًا. ` +
            "اسألني عن أي شيء فيه — أو اطلب مني اقتراح منح تناسب ملفك.",
    });
    setStatus("ok", "متصل");
  } catch (error) {
    hideTyping();
    showError(error.message);
  } finally {
    busy = false;
    el.file.value = "";
    el.input.focus();
  }
}

async function newChat() {
  if (sessionId) {
    // Best-effort: tell the server to forget the documents immediately rather
    // than waiting for the TTL.
    try {
      await callApi("/api/session/" + sessionId, { method: "DELETE" });
    } catch { /* the TTL will collect it anyway */ }
  }
  sessionId = null;
  transcript = [];
  localStorage.removeItem(LS_SESSION);
  localStorage.removeItem(LS_TRANSCRIPT);
  el.messages.innerHTML = "";
  if (el.welcome) {
    el.messages.appendChild(el.welcome);
    el.welcome.style.display = "";
  }
  renderDocuments([]);
  clearError();
  el.input.focus();
}

/* ------------------------------------------------------------------- init */

function autoGrow() {
  el.input.style.height = "auto";
  el.input.style.height = Math.min(el.input.scrollHeight, 160) + "px";
}

el.form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(el.input.value);
});

el.input.addEventListener("input", () => {
  el.send.disabled = !el.input.value.trim() || busy;
  autoGrow();
});

el.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(el.input.value);
  }
});

el.upload.addEventListener("click", () => el.file.click());
el.file.addEventListener("change", () => uploadFile(el.file.files[0]));
el.newChat.addEventListener("click", newChat);
el.bannerClose.addEventListener("click", clearError);

el.suggestions?.addEventListener("click", (event) => {
  const chip = event.target.closest(".chip");
  if (chip) sendMessage(chip.dataset.prompt);
});

(async function boot() {
  // Replay the transcript the browser kept, so a refresh looks continuous.
  if (transcript.length) {
    transcript.forEach((entry) => renderMessage(entry, false));
  }
  try {
    const health = await callApi("/api/health");
    setStatus(health.gemini_key_configured ? "ok" : "bad",
              health.gemini_key_configured ? "متصل" : "الخدمة غير مهيأة");
  } catch {
    setStatus("bad", "تعذّر الاتصال");
  }
  // Restore the server's view of the session (documents survive a refresh).
  if (sessionId) {
    try {
      const info = await callApi("/api/session/" + sessionId);
      renderDocuments(info.documents);
    } catch {
      sessionId = null;
      localStorage.removeItem(LS_SESSION);
    }
  }
  el.input.focus();
})();
