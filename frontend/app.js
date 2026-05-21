/**
 * F.R.I.D.A.Y. — Frontend Application
 * ChatGPT-style interface with full conversation history, markdown, TTS, and file upload.
 */

const API = {
  chat: '/api/chat',
  chatStream: '/api/chat/stream',
  conversations: '/api/conversations',
  tts: '/api/tts',
  status: '/api/status',
  upload: '/api/upload',
};

// ── State ──────────────────────────────────────────────────────────────────

const state = {
  conversations: [],          // [{id, title, updated_at}]
  activeConvoId: null,
  messages: [],               // [{id, role, content, created_at}]
  isGenerating: false,
  isMicActive: false,
  pendingFile: null,          // {name, content (base64), type}
  autoTTS: false,
  mediaRec: null,
  audioChunks: [],
};

// ── DOM refs ───────────────────────────────────────────────────────────────

const $  = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

const dom = {
  sidebar:      () => document.querySelector('.sidebar'),
  convoList:    () => $('convoList'),
  messagesWrap: () => $('messagesWrap'),
  messagesInner:() => $('messagesInner'),
  userInput:    () => $('userInput'),
  sendBtn:      () => $('sendBtn'),
  micBtn:       () => $('micBtn'),
  uploadBtn:    () => $('uploadBtn'),
  uploadInput:  () => $('uploadInput'),
  uploadPreview:() => $('uploadPreview'),
  uploadName:   () => $('uploadName'),
  topbarTitle:  () => $('topbarTitle'),
  statusDot:    () => $('statusDot'),
  statusText:   () => $('statusText'),
  toastContainer:() => $('toastContainer'),
  audioPlayer:  () => $('audioPlayer'),
  renameModal:  () => $('renameModal'),
  renameInput:  () => $('renameInput'),
  inputBox:     () => $('inputBox'),
};

// ── Initialise ─────────────────────────────────────────────────────────────

async function init() {
  setupEventListeners();
  await Promise.all([loadConversations(), checkStatus()]);
  setInterval(checkStatus, 30_000);
}

// ── Event Listeners ────────────────────────────────────────────────────────

function setupEventListeners() {
  // Send on Enter (Shift+Enter for newline)
  dom.userInput().addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize textarea
  dom.userInput().addEventListener('input', () => {
    const el = dom.userInput();
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  });

  dom.sendBtn().addEventListener('click', sendMessage);
  dom.micBtn().addEventListener('click', toggleMic);

  dom.uploadBtn().addEventListener('click', () => dom.uploadInput().click());
  dom.uploadInput().addEventListener('change', handleFileSelect);
  $('removeUpload').addEventListener('click', clearUpload);

  $('newChatBtn').addEventListener('click', startNewChat);
  $('toggleSidebarTop').addEventListener('click', toggleSidebar);
  $('toggleSidebarBottom').addEventListener('click', toggleSidebar);
  $('clearChatBtn').addEventListener('click', clearCurrentChat);
  $('autoTTSBtn').addEventListener('click', () => {
    state.autoTTS = !state.autoTTS;
    $('autoTTSBtn').style.color = state.autoTTS ? 'var(--accent)' : '';
    showToast(state.autoTTS ? 'Auto-speak enabled' : 'Auto-speak disabled', 'info');
  });

  // Rename modal
  $('renameCancel').addEventListener('click', closeRenameModal);
  $('renameConfirm').addEventListener('click', confirmRename);
  dom.renameInput().addEventListener('keydown', e => {
    if (e.key === 'Enter') confirmRename();
    if (e.key === 'Escape') closeRenameModal();
  });
  dom.renameModal().addEventListener('click', e => {
    if (e.target === dom.renameModal()) closeRenameModal();
  });
}

// ── Status check ───────────────────────────────────────────────────────────

async function checkStatus() {
  try {
    const r = await fetch(API.status);
    const d = await r.json();
    const online = d.status === 'online';
    dom.statusDot().className = 'status-dot' + (online ? '' : ' offline');
    dom.statusText().textContent = online ? (d.gemini ? 'Gemini Connected' : 'Local Mode') : 'Offline';
  } catch {
    dom.statusDot().className = 'status-dot offline';
    dom.statusText().textContent = 'Offline';
  }
}

// ── Conversation management ────────────────────────────────────────────────

async function loadConversations() {
  try {
    const r = await fetch(API.conversations);
    const d = await r.json();
    state.conversations = d.conversations || [];
    renderConvoList();
  } catch (e) {
    console.error('Failed to load conversations:', e);
  }
}

function renderConvoList() {
  const list = dom.convoList();
  list.innerHTML = '';
  if (state.conversations.length === 0) {
    list.innerHTML = '<div style="padding:8px 10px;font-size:12px;color:var(--text-muted)">No conversations yet</div>';
    return;
  }
  state.conversations.forEach(c => {
    const item = document.createElement('div');
    item.className = 'convo-item' + (c.id === state.activeConvoId ? ' active' : '');
    item.dataset.id = c.id;
    item.innerHTML = `
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="flex-shrink:0;opacity:.5">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
      </svg>
      <span class="convo-item-title">${escHtml(c.title)}</span>
      <div class="convo-item-actions">
        <button class="convo-action-btn rename-btn" title="Rename" onclick="openRenameModal('${c.id}', event)">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
        </button>
        <button class="convo-action-btn danger" title="Delete" onclick="deleteConversation('${c.id}', event)">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6m4-6v6"/><path d="M9 6V4h6v2"/>
          </svg>
        </button>
      </div>`;
    item.addEventListener('click', e => {
      if (e.target.closest('.convo-item-actions')) return;
      loadConversation(c.id);
    });
    list.appendChild(item);
  });
}

async function loadConversation(id) {
  try {
    const r = await fetch(`${API.conversations}/${id}`);
    const d = await r.json();
    state.activeConvoId = id;
    state.messages = d.messages || [];
    dom.topbarTitle().textContent = d.title || 'F.R.I.D.A.Y.';
    renderMessages();
    renderConvoList();
    scrollToBottom(false);
  } catch (e) {
    showToast('Failed to load conversation', 'error');
  }
}

async function startNewChat() {
  state.activeConvoId = null;
  state.messages = [];
  dom.topbarTitle().textContent = 'F.R.I.D.A.Y.';
  renderMessages();
  renderConvoList();
  dom.userInput().focus();
}

async function deleteConversation(id, e) {
  e.stopPropagation();
  try {
    await fetch(`${API.conversations}/${id}`, { method: 'DELETE' });
    if (state.activeConvoId === id) await startNewChat();
    await loadConversations();
    showToast('Conversation deleted', 'success');
  } catch {
    showToast('Failed to delete', 'error');
  }
}

function openRenameModal(id, e) {
  e.stopPropagation();
  const c = state.conversations.find(x => x.id === id);
  if (!c) return;
  dom.renameInput().value = c.title;
  dom.renameModal().dataset.targetId = id;
  dom.renameModal().classList.add('visible');
  setTimeout(() => dom.renameInput().select(), 50);
}

function closeRenameModal() {
  dom.renameModal().classList.remove('visible');
}

async function confirmRename() {
  const id = dom.renameModal().dataset.targetId;
  const title = dom.renameInput().value.trim();
  if (!title) return;
  closeRenameModal();
  try {
    await fetch(`${API.conversations}/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    await loadConversations();
    if (state.activeConvoId === id) dom.topbarTitle().textContent = title;
  } catch {
    showToast('Failed to rename', 'error');
  }
}

async function clearCurrentChat() {
  if (!state.activeConvoId) return;
  await deleteConversation(state.activeConvoId, { stopPropagation: () => {} });
}

// ── Sending messages ───────────────────────────────────────────────────────

async function sendMessage() {
  const input = dom.userInput();
  const text = input.value.trim();
  if ((!text && !state.pendingFile) || state.isGenerating) return;

  // Build message text (append file context if present)
  let messageText = text;
  if (state.pendingFile) {
    messageText = text
      ? `${text}\n\n[Attached file: ${state.pendingFile.name}]`
      : `[Analyse this file: ${state.pendingFile.name}]`;
  }

  // Clear input
  input.value = '';
  input.style.height = 'auto';
  clearUpload();

  // Append user message locally
  const userMsg = { id: Date.now(), role: 'user', content: messageText };
  state.messages.push(userMsg);
  renderMessages();
  scrollToBottom();

  state.isGenerating = true;
  updateSendBtn();
  showTypingIndicator();

  try {
    const body = {
      message: messageText,
      conversation_id: state.activeConvoId,
    };
    if (state.pendingFile) body.file = state.pendingFile;

    const r = await fetch(API.chatStream, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!r.ok) throw new Error('Request failed');

    const assistantMsg = { id: Date.now() + 1, role: 'friday', content: '' };
    state.messages.push(assistantMsg);
    hideTypingIndicator();
    renderMessages();

    // Stream reading
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let done = false;

    while (!done) {
      const { value, done: rdDone } = await reader.read();
      done = rdDone;
      if (value) buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const ev = JSON.parse(line.slice(6));
          if (ev.done) {
            // Capture conversation id & title from server
            if (ev.conversation_id) {
              state.activeConvoId = ev.conversation_id;
              dom.topbarTitle().textContent = ev.title || 'Conversation';
              await loadConversations();
            }
            if (state.autoTTS && assistantMsg.content) {
              speakText(assistantMsg.content);
            }
            done = true;
            break;
          }
          if (ev.text) {
            assistantMsg.content += ev.text;
            updateLastMessage(assistantMsg.content);
          }
        } catch {}
      }
    }
  } catch (err) {
    hideTypingIndicator();
    const errMsg = { id: Date.now() + 2, role: 'friday', content: 'I encountered an error processing your request. Please try again.' };
    state.messages.push(errMsg);
    renderMessages();
    showToast('Connection error', 'error');
  } finally {
    state.isGenerating = false;
    updateSendBtn();
    scrollToBottom();
  }
}

// ── Rendering ──────────────────────────────────────────────────────────────

function renderMessages() {
  const inner = dom.messagesInner();
  inner.innerHTML = '';

  if (state.messages.length === 0) {
    inner.innerHTML = `
      <div class="welcome">
        <div class="welcome-icon">F</div>
        <h1>F.R.I.D.A.Y.</h1>
        <p>Female Replacement Intelligent Digital Assistant Youth.<br>How can I help you today, Sir?</p>
        <div class="welcome-suggestions">
          ${[
            ['Research a topic', 'Ask me to research anything and get a synthesized report'],
            ['Run some code', 'I can write and execute Python or shell scripts'],
            ['Analyse a document', 'Upload a PDF, Word doc, or image for analysis'],
            ['System status', 'Check CPU, RAM, battery, and system info'],
          ].map(([t, s]) => `
            <div class="suggestion-card" onclick="fillSuggestion('${t}')">
              <div class="s-title">${t}</div>
              <div class="s-sub">${s}</div>
            </div>`).join('')}
        </div>
      </div>`;
    return;
  }

  state.messages.forEach(msg => {
    const row = document.createElement('div');
    row.className = `msg-row ${msg.role}`;
    row.id = `msg-${msg.id}`;

    const label = document.createElement('div');
    label.className = 'msg-role-label';
    label.textContent = msg.role === 'user' ? 'You' : 'F.R.I.D.A.Y.';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = msg.role === 'friday' ? renderMarkdown(msg.content) : escHtml(msg.content).replace(/\n/g, '<br>');

    // Actions
    const actions = document.createElement('div');
    actions.className = 'msg-actions';
    if (msg.role === 'friday') {
      actions.innerHTML = `
        <button class="msg-action-btn" onclick="copyMessage(this, ${msg.id})" title="Copy">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
          Copy
        </button>
        <button class="msg-action-btn" onclick="speakMessage(${msg.id})" title="Speak">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"/></svg>
          Speak
        </button>`;
    } else {
      actions.innerHTML = `
        <button class="msg-action-btn" onclick="copyMessage(this, ${msg.id})" title="Copy">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
          Copy
        </button>`;
    }

    row.appendChild(label);
    row.appendChild(bubble);
    row.appendChild(actions);
    inner.appendChild(row);
  });

  // Apply syntax highlighting
  $$('pre code').forEach(el => {
    if (window.hljs) hljs.highlightElement(el);
  });
}

function updateLastMessage(content) {
  const rows = dom.messagesInner().querySelectorAll('.msg-row.friday');
  if (!rows.length) return;
  const last = rows[rows.length - 1];
  const bubble = last.querySelector('.msg-bubble');
  if (bubble) {
    bubble.innerHTML = renderMarkdown(content);
    // Re-highlight code blocks
    bubble.querySelectorAll('pre code').forEach(el => {
      if (window.hljs) hljs.highlightElement(el);
    });
  }
  scrollToBottom();
}

// ── Typing indicator ──────────────────────────────────────────────────────

function showTypingIndicator() {
  hideTypingIndicator();
  const inner = dom.messagesInner();
  const el = document.createElement('div');
  el.id = 'typingIndicator';
  el.className = 'typing-row';
  el.innerHTML = `
    <div class="msg-role-label">F.R.I.D.A.Y.</div>
    <div class="typing-bubble">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>`;
  inner.appendChild(el);
  scrollToBottom();
}

function hideTypingIndicator() {
  const el = $('typingIndicator');
  if (el) el.remove();
}

// ── Markdown rendering ────────────────────────────────────────────────────

function renderMarkdown(text) {
  if (!text) return '';
  if (window.marked) {
    marked.setOptions({
      highlight: (code, lang) => {
        if (window.hljs && lang && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return window.hljs ? hljs.highlightAuto(code).value : code;
      },
      breaks: true,
      gfm: true,
    });
    // Post-process to wrap code blocks with copy button
    let html = marked.parse(text);
    html = html.replace(/<pre><code class="language-(\w+)">([\s\S]*?)<\/code><\/pre>/g,
      (_, lang, code) => codeBlockHtml(lang, code));
    html = html.replace(/<pre><code>([\s\S]*?)<\/code><\/pre>/g,
      (_, code) => codeBlockHtml('', code));
    return html;
  }
  // Fallback: basic escaping with line breaks
  return escHtml(text).replace(/\n/g, '<br>');
}

function codeBlockHtml(lang, code) {
  const id = 'cb_' + Math.random().toString(36).slice(2, 8);
  return `
    <div class="code-block-wrap">
      <div class="code-block-header">
        <span class="code-lang">${lang || 'code'}</span>
        <button class="copy-code-btn" onclick="copyCodeBlock('${id}', this)">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
          Copy
        </button>
      </div>
      <pre><code id="${id}" class="language-${lang}">${code}</code></pre>
    </div>`;
}

// ── Utilities ──────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function scrollToBottom(smooth = true) {
  const wrap = dom.messagesWrap();
  if (smooth) {
    wrap.scrollTo({ top: wrap.scrollHeight, behavior: 'smooth' });
  } else {
    wrap.scrollTop = wrap.scrollHeight;
  }
}

function updateSendBtn() {
  const btn = dom.sendBtn();
  btn.disabled = state.isGenerating;
}

function fillSuggestion(text) {
  dom.userInput().value = text;
  dom.userInput().focus();
  dom.userInput().dispatchEvent(new Event('input'));
}

function toggleSidebar() {
  dom.sidebar().classList.toggle('collapsed');
}

// ── Copy helpers ──────────────────────────────────────────────────────────

function copyMessage(btn, id) {
  const msg = state.messages.find(m => m.id === id);
  if (!msg) return;
  navigator.clipboard.writeText(msg.content).then(() => {
    showToast('Copied to clipboard', 'success');
  });
}

function copyCodeBlock(id, btn) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).then(() => {
    btn.innerHTML = `<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg> Copied!`;
    btn.classList.add('copied');
    setTimeout(() => {
      btn.innerHTML = `<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg> Copy`;
      btn.classList.remove('copied');
    }, 2000);
  });
}

// ── TTS ───────────────────────────────────────────────────────────────────

async function speakText(text) {
  try {
    const r = await fetch(API.tts, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.slice(0, 1000) }),
    });
    if (!r.ok) return;
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const player = dom.audioPlayer();
    player.src = url;
    player.play();
    player.onended = () => URL.revokeObjectURL(url);
  } catch (e) {
    console.error('TTS error:', e);
  }
}

function speakMessage(id) {
  const msg = state.messages.find(m => m.id === id);
  if (msg) speakText(msg.content);
}

// ── Microphone ────────────────────────────────────────────────────────────

async function toggleMic() {
  if (state.isMicActive) {
    stopMic();
  } else {
    startMic();
  }
}

async function startMic() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.audioChunks = [];
    state.mediaRec = new MediaRecorder(stream);
    state.mediaRec.ondataavailable = e => state.audioChunks.push(e.data);
    state.mediaRec.onstop = handleMicStop;
    state.mediaRec.start();
    state.isMicActive = true;
    dom.micBtn().classList.add('mic-active');
    dom.micBtn().title = 'Stop recording';
  } catch {
    showToast('Microphone access denied', 'error');
  }
}

function stopMic() {
  if (state.mediaRec) {
    state.mediaRec.stop();
    state.mediaRec.stream.getTracks().forEach(t => t.stop());
    state.mediaRec = null;
  }
  state.isMicActive = false;
  dom.micBtn().classList.remove('mic-active');
  dom.micBtn().title = 'Voice input';
}

async function handleMicStop() {
  const blob = new Blob(state.audioChunks, { type: 'audio/webm' });
  const fd = new FormData();
  fd.append('audio', blob, 'recording.webm');
  try {
    const r = await fetch('/api/listen', { method: 'POST', body: fd });
    const d = await r.json();
    if (d.text) {
      dom.userInput().value = d.text;
      dom.userInput().dispatchEvent(new Event('input'));
      dom.userInput().focus();
    } else {
      showToast(d.error || 'Could not transcribe audio', 'error');
    }
  } catch {
    showToast('Transcription failed', 'error');
  }
}

// ── File upload ───────────────────────────────────────────────────────────

async function handleFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = '';

  const MAX_SIZE = 10 * 1024 * 1024; // 10 MB
  if (file.size > MAX_SIZE) {
    showToast('File too large (max 10 MB)', 'error');
    return;
  }

  const reader = new FileReader();
  reader.onload = ev => {
    const b64 = ev.target.result.split(',')[1];
    state.pendingFile = { name: file.name, content: b64, type: file.type };
    dom.uploadName().textContent = file.name;
    dom.uploadPreview().classList.add('visible');
    dom.inputBox().classList.add('has-upload');
  };
  reader.readAsDataURL(file);
}

function clearUpload() {
  state.pendingFile = null;
  dom.uploadPreview().classList.remove('visible');
  dom.inputBox().classList.remove('has-upload');
}

// ── Toast notifications ───────────────────────────────────────────────────

function showToast(msg, type = 'info', duration = 3000) {
  const icons = {
    success: '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>',
    error: '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    info: '<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
  };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span class="toast-icon">${icons[type] || ''}</span><span>${escHtml(msg)}</span>`;
  dom.toastContainer().appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut 0.25s ease forwards';
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

// ── Start ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', init);
