// ============================================================
// 별무리 고등학교 AI 스케줄 비서 - 대시보드 클라이언트 로직
// ============================================================

const DAY_NAMES = ["월", "화", "수", "목", "금"];

// ---------------- 공통 API 헬퍼 ----------------
async function api(method, url, data) {
  const opts = { method, headers: {} };
  if (data !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(data);
  }
  const res = await fetch(url, opts);
  if (res.status === 401) {
    window.location.href = "/login";
    return null;
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || "요청 처리 중 오류가 발생했습니다.");
  return body;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function formatDue(dueDate) {
  if (!dueDate) return "";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(dueDate + "T00:00:00");
  const diffDays = Math.round((d - today) / 86400000);
  let label = dueDate.slice(5).replace("-", "/");
  let cls = "text-white/50";
  if (diffDays < 0) { label += " (지남)"; cls = "due-soon"; }
  else if (diffDays === 0) { label += " (오늘)"; cls = "due-soon"; }
  else if (diffDays === 1) { label += " (내일)"; cls = "text-amber-300"; }
  return `<span class="${cls}">${label}</span>`;
}

// ---------------- 사용자 정보 / 로그아웃 ----------------
async function loadMe() {
  try {
    const me = await api("GET", "/api/me");
    if (me) {
      document.getElementById("userLabel").textContent = `${me.name} · ${me.grade}학년 ${me.class_no}반`;
    }
  } catch (e) { /* noop */ }
}

document.getElementById("logoutBtn").addEventListener("click", async () => {
  await api("POST", "/api/logout");
  window.location.href = "/login";
});

// ---------------- 시간표 ----------------
const toggleScheduleFormBtn = document.getElementById("toggleScheduleForm");
const scheduleForm = document.getElementById("scheduleForm");
toggleScheduleFormBtn.addEventListener("click", () => {
  scheduleForm.classList.toggle("hidden");
});

async function loadSchedule() {
  const items = await api("GET", "/api/schedule");
  const tbody = document.getElementById("timetableBody");
  const emptyMsg = document.getElementById("timetableEmpty");
  tbody.innerHTML = "";

  if (!items || items.length === 0) {
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");

  const periods = [...new Set(items.map((i) => i.period))].sort((a, b) => a - b);
  const grid = {};
  items.forEach((i) => {
    grid[`${i.period}-${i.day_of_week}`] = i;
  });

  periods.forEach((period) => {
    const tr = document.createElement("tr");
    let rowHtml = `<td class="text-center text-white/40 font-medium">${period}</td>`;
    for (let day = 0; day < 5; day++) {
      const item = grid[`${period}-${day}`];
      if (item) {
        rowHtml += `
          <td class="group relative rounded-xl bg-white/5 border border-white/10 px-2 py-2 text-center align-top">
            <p class="font-semibold">${escapeHtml(item.subject)}</p>
            ${item.room ? `<p class="text-[11px] text-white/40">${escapeHtml(item.room)}</p>` : ""}
            <button data-id="${item.id}" class="schedule-delete absolute -top-1.5 -right-1.5 hidden group-hover:flex
              w-4 h-4 rounded-full bg-red-500/80 text-white text-[10px] items-center justify-center">✕</button>
          </td>`;
      } else {
        rowHtml += `<td class="rounded-xl bg-white/[0.02] border border-white/5"></td>`;
      }
    }
    tr.innerHTML = rowHtml;
    tbody.appendChild(tr);
  });
}

document.getElementById("timetableBody").addEventListener("click", async (e) => {
  const btn = e.target.closest(".schedule-delete");
  if (!btn) return;
  await api("DELETE", `/api/schedule/${btn.dataset.id}`);
  loadSchedule();
});

scheduleForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(scheduleForm);
  try {
    await api("POST", "/api/schedule", {
      day_of_week: fd.get("day_of_week"),
      period: fd.get("period"),
      subject: fd.get("subject"),
      room: fd.get("room"),
    });
    scheduleForm.reset();
    scheduleForm.classList.add("hidden");
    loadSchedule();
  } catch (err) {
    alert(err.message);
  }
});

// ---------------- To-Do ----------------
async function loadTodos() {
  const items = await api("GET", "/api/todos");
  const list = document.getElementById("todoList");
  const emptyMsg = document.getElementById("todoEmpty");
  const countLabel = document.getElementById("todoCount");
  list.innerHTML = "";

  if (!items || items.length === 0) {
    emptyMsg.classList.remove("hidden");
    countLabel.textContent = "";
    return;
  }
  emptyMsg.classList.add("hidden");
  const doneCount = items.filter((i) => i.is_done).length;
  countLabel.textContent = `${doneCount} / ${items.length} 완료`;

  items.forEach((item) => {
    const li = document.createElement("li");
    li.className = "flex items-center gap-3 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5";
    const sourceTag =
      item.source === "ai" ? '<span class="text-[10px] text-violet-300">AI 추가</span>'
      : item.source === "memo" ? '<span class="text-[10px] text-blue-300">메모 분석</span>' : "";
    li.innerHTML = `
      <input type="checkbox" ${item.is_done ? "checked" : ""} data-id="${item.id}"
        class="todo-check w-4 h-4 rounded accent-violet-500 shrink-0">
      <div class="flex-1 min-w-0">
        <p class="text-sm truncate ${item.is_done ? "todo-done" : ""}">${escapeHtml(item.title)}</p>
        <div class="flex items-center gap-2 text-[11px]">${formatDue(item.due_date)}${sourceTag}</div>
      </div>
      <button data-id="${item.id}" class="todo-delete text-white/30 hover:text-red-300 text-sm shrink-0">✕</button>
    `;
    list.appendChild(li);
  });
}

document.getElementById("todoList").addEventListener("change", async (e) => {
  if (!e.target.classList.contains("todo-check")) return;
  await api("PATCH", `/api/todos/${e.target.dataset.id}`, { is_done: e.target.checked });
  loadTodos();
});

document.getElementById("todoList").addEventListener("click", async (e) => {
  const btn = e.target.closest(".todo-delete");
  if (!btn) return;
  await api("DELETE", `/api/todos/${btn.dataset.id}`);
  loadTodos();
});

document.getElementById("todoForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);
  const title = fd.get("title").trim();
  if (!title) return;
  await api("POST", "/api/todos", { title, due_date: fd.get("due_date") || null });
  form.reset();
  loadTodos();
});

// ---------------- 메모 ----------------
async function loadMemos() {
  const items = await api("GET", "/api/memos");
  const list = document.getElementById("memoList");
  const emptyMsg = document.getElementById("memoEmpty");
  list.innerHTML = "";

  if (!items || items.length === 0) {
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");

  items.forEach((memo) => {
    const div = document.createElement("div");
    div.className = "bg-white/5 border border-white/10 rounded-xl px-4 py-3";
    div.innerHTML = `
      <p class="text-sm whitespace-pre-wrap">${escapeHtml(memo.content)}</p>
      <div class="flex items-center justify-between mt-2">
        <span class="text-[11px] text-white/40">${memo.created_at.slice(0, 16).replace("T", " ")}</span>
        <div class="flex items-center gap-2">
          ${memo.analyzed ? '<span class="text-[11px] text-emerald-300">✓ 분석 완료</span>' : ""}
          <button data-id="${memo.id}" class="memo-analyze btn-pill-outline text-[11px] px-3 py-1">
            ${memo.analyzed ? "다시 분석" : "✨ AI 분석"}
          </button>
          <button data-id="${memo.id}" class="memo-delete text-white/30 hover:text-red-300 text-sm">✕</button>
        </div>
      </div>
    `;
    list.appendChild(div);
  });
}

document.getElementById("memoForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);
  const content = fd.get("content").trim();
  if (!content) return;
  await api("POST", "/api/memos", { content });
  form.reset();
  loadMemos();
});

document.getElementById("memoList").addEventListener("click", async (e) => {
  const analyzeBtn = e.target.closest(".memo-analyze");
  const deleteBtn = e.target.closest(".memo-delete");

  if (deleteBtn) {
    await api("DELETE", `/api/memos/${deleteBtn.dataset.id}`);
    loadMemos();
    return;
  }
  if (analyzeBtn) {
    const originalText = analyzeBtn.textContent;
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "분석 중...";
    try {
      const result = await api("POST", `/api/memos/${analyzeBtn.dataset.id}/analyze`);
      await loadMemos();
      await loadTodos();
      if (result.added_tasks && result.added_tasks.length > 0) {
        const titles = result.added_tasks.map((t) => `· ${t.title}`).join("\n");
        alert(`To-Do에 추가되었어요:\n${titles}`);
      } else {
        alert("메모에서 특별한 할 일을 찾지 못했어요.");
      }
    } catch (err) {
      alert(err.message);
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = originalText;
    }
  }
});

// ---------------- 급식 / 공지 ----------------
async function loadMeals() {
  const items = await api("GET", "/api/meals");
  const list = document.getElementById("mealList");
  const emptyMsg = document.getElementById("mealEmpty");
  list.innerHTML = "";
  if (!items || items.length === 0) {
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");
  items.forEach((meal) => {
    const div = document.createElement("div");
    div.className = "bg-white/5 border border-white/10 rounded-xl px-4 py-3";
    div.innerHTML = `
      <p class="text-xs text-violet-300 font-semibold mb-1">${escapeHtml(meal.meal_type)}</p>
      <p class="text-white/80 leading-relaxed">${escapeHtml(meal.menu)}</p>
    `;
    list.appendChild(div);
  });
}

async function loadNotices() {
  const items = await api("GET", "/api/notices");
  const list = document.getElementById("noticeList");
  list.innerHTML = "";
  (items || []).forEach((n) => {
    const div = document.createElement("div");
    div.className = "bg-white/5 border border-white/10 rounded-xl px-4 py-3";
    div.innerHTML = `
      <p class="font-semibold text-sm mb-1">${escapeHtml(n.title)}</p>
      <p class="text-white/60 text-xs leading-relaxed">${escapeHtml(n.content)}</p>
    `;
    list.appendChild(div);
  });
}

// ---------------- 챗봇 ----------------
const chatToggleBtn = document.getElementById("chatToggleBtn");
const chatPanel = document.getElementById("chatPanel");
const chatCloseBtn = document.getElementById("chatCloseBtn");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");

let chatOpened = false;

function openChat() {
  chatPanel.classList.remove("hidden-panel");
  chatOpened = true;
  if (chatMessages.children.length === 0) {
    appendChatBubble("ai", "안녕하세요! 저는 별비서예요 ✨ 시간표, 할 일, 오늘 급식, 학교 공지사항까지 물어보면 바로 알려드릴게요.");
  }
  chatInput.focus();
}
function closeChat() {
  chatPanel.classList.add("hidden-panel");
}
chatToggleBtn.addEventListener("click", () => (chatOpened ? closeChat() : openChat()) || (chatOpened = !chatOpened));
chatCloseBtn.addEventListener("click", closeChat);

function appendChatBubble(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `flex fade-in ${role === "user" ? "justify-end" : "justify-start"}`;
  const bubble = document.createElement("div");
  bubble.className = `max-w-[80%] rounded-2xl px-4 py-2.5 whitespace-pre-wrap ${
    role === "user" ? "chat-bubble-user" : "chat-bubble-ai"
  }`;
  bubble.textContent = text;
  wrap.appendChild(bubble);
  chatMessages.appendChild(wrap);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return wrap;
}

function appendTypingIndicator() {
  const wrap = document.createElement("div");
  wrap.className = "flex justify-start fade-in";
  wrap.id = "typingIndicator";
  wrap.innerHTML = `<div class="chat-bubble-ai rounded-2xl px-4 py-3">
    <div class="dot-typing"><span></span><span></span><span></span></div>
  </div>`;
  chatMessages.appendChild(wrap);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}
function removeTypingIndicator() {
  document.getElementById("typingIndicator")?.remove();
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  appendChatBubble("user", message);
  chatInput.value = "";
  appendTypingIndicator();

  try {
    const result = await api("POST", "/api/chat", { message });
    removeTypingIndicator();
    appendChatBubble("ai", result.reply);
    // 챗봇이 할 일을 추가했을 수 있으니 목록 새로고침
    loadTodos();
  } catch (err) {
    removeTypingIndicator();
    appendChatBubble("ai", `이런! 오류가 발생했어요: ${err.message}`);
  }
});

// ---------------- 초기 로드 ----------------
(async function init() {
  loadMe();
  loadSchedule();
  loadTodos();
  loadMemos();
  loadMeals();
  loadNotices();
})();
