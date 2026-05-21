/**
 * F.R.I.D.A.Y. — ChatGPT-style Web UI
 * Handles: conversations CRUD, streaming chat, markdown rendering,
 *          code blocks w/ syntax highlighting, voice input, TTS.
 */

'use strict';

/* ── DOM refs ───────────────────────────────────────────────────────── */
const sidebar            = document.getElementById('sidebar');
const sidebarToggleBtn   = document.getElementById('sidebarToggle');
const openSidebarBtn     = document.getElementById('openSidebarBtn');
const newChatBtn         = document.getElementById('newChatBtn');
const conversationsList  = document.getElementById('conversationsList');
const convEmpty          = document.getElementById('convEmpty');
const chatTitle          = document.getElementById('chatTitle');
const messagesArea       = document.getElementById('messagesArea');
const welcomeScreen      = document.getElementById('welcomeScreen');
const messagesContainer  = document.getElementById('messagesContainer');
const messageInput       = document.getElementById('messageInput');
const sendBtn            = document.getElementById('sendBtn');
const voiceBtn           = document.getElementById('voiceBtn');
const clearChatBtn       = document.getElementById('clearChatBtn');
const statusDot          = document.getElementById('statusDot');
const statusLabel        = document.getElementById('statusLabel');
const renameModal        = document.getElementById('renameModal');
const renameInput        = document.getElementById('renameInput');
const renameSaveBtn      = document.getElementById('renameSaveBtn');
const renameCancelBtn    = document.getElementById('renameCancelBtn');
const toastEl            = document.getElementById('toast');

/* ── App state ──────────────────────────────────────────────────────── */
let currentConvId    = null;
let conversations    = [];
let isStreaming      = false;
let renameTargetId   = null;
let mediaRecorder    = null;
let isRecording      = false;
let audioChunks      = [];

/* ════════════════════════════════════════════════════════════════════
   INITIALISATION
   ════════════════════════════════════════════════════════════════════ */
(async function init() {
  await checkStatus();
  await loadConversations();
  bindEvents();
  messageInput.focus();
})();

/* ── Status poll ────────────────────────────────────────────────────── */
async function checkStatus() {
  try {
    const r = await fetch('/api/status');
    if (!r.ok) throw new Error('offline');
    const d = await r.json();
    if (d.status === 'online') {
      statusDot.className   = 'status-dot';
      statusLabel.textContent = d.gemini ? 'F.R.I.D.A.Y. Online' : 'F.R.I.D.A.Y. (local mode)';
    }
  } catch {
    statusDot.className     = 'status-dot offline';
    statusLabel.textContent = 'Server unreachable';
  }
}

/* ════════════════════════════════════════════════════════════════════
   CONVERSATIONS
   ════════════════════════════════════════════════════════════════════ */
async function loadConversations() {
  try {
    const r = await fetch('/api/conversations');
    if (!r.ok) return;
    conversations = await r.json();
    renderConversationList();
  } catch (e) {
    console.warn('Could not load conversations:', e);
  }
}

function renderConversationList() {
  // Group by relative date
  const groups = {};
  const now    = new Date();
  for (const conv of conversations) {
    const d = new Date(conv.updated_at || conv.created_at);
    const key = dateGroupLabel(d, now);
    if (!groups[key]) groups[key] = [];
    groups[key].push(conv);
  }

  // Clear existing content (keep convEmpty)
  const items = conversationsList.querySelectorAll('.conv-group-label, .conv-item');
  items.forEach(el => el.remove());

  if (conversations.length === 0) {
    convEmpty.style.display = 'block';
    return;
  }
  convEmpty.style.display = 'none';

  const orderedKeys = ['Today', 'Yesterday', 'Last 7 days', 'Last 30 days', 'Older'];
  for (const key of orderedKeys) {
    if (!groups[key]) continue;
    const label = document.createElement('div');
    label.className      = 'conv-group-label';
    label.textContent    = key;
    conversationsList.appendChild(label);

    for (const conv of groups[key]) {
      conversationsList.appendChild(buildConvItem(conv));
    }
  }
}

function buildConvItem(conv) {
  const item = document.createElement('div');
  item.className   = 'conv-item' + (conv.id === currentConvId ? ' active' : '');
  item.dataset.id  = conv.id;

  const title = document.createElement('span');
  title.className  = 'conv-item-title';
  title.textContent = conv.title || 'New Conversation';

  const actions = document.createElement('div');
  actions.className = 'conv-item-actions';

  const renameBtn = document.createElement('button');
  renameBtn.className = 'conv-action-btn rename-btn';
  renameBtn.title     = 'Rename';
  renameBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`;
  renameBtn.addEventListener('click', e => { e.stopPropagation(); openRenameModal(conv.id, conv.title); });

  const delBtn = document.createElement('button');
  delBtn.className  = 'conv-action-btn delete-btn';
  delBtn.title      = 'Delete';
  delBtn.innerHTML  = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3,6 5,6 21,6"/><path d="M19,6l-1,14H6L5,6"/><path d="M10,11v6"/><path d="M14,11v6"/><path d="M9,6V4h6v2"/></svg>`;
  delBtn.addEventListener('click', e => { e.stopPropagation(); deleteConversation(conv.id); });

  actions.appendChild(renameBtn);
  actions.appendChild(delBtn);

  item.appendChild(title);
  item.appendChild(actions);

  item.addEventListener('click', () => openConversation(conv.id));
  return item;
}

function dateGroupLabel(date, now) {
  const msPerDay = 86400000;
  const diffDays = Math.floor((now - date) / msPerDay);
  if (diffDays < 1)  return 'Today';
  if (diffDays < 2)  return 'Yesterday';
  if (diffDays < 7)  return 'Last 7 days';
  if (diffDays < 30) return 'Last 30 days';
  return 'Older';
}

async function openConversation(convId) {
  currentConvId = convId;
  const conv = conversations.find(c => c.id === convId);
  chatTitle.textContent = conv?.title || 'F.R.I.D.A.Y.';

  // Update active state in sidebar
  document.querySelectorAll('.conv-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id === convId);
  });

  // Load messages
  messagesContainer.innerHTML = '';
  welcomeScreen.style.display = 'none';
  try {
    const r = await fetch(`/api/conversations/${convId}`);
    if (!r.ok) return;
    const data = await r.json();
    for (const msg of (data.messages || [])) {
      appendMessage(msg.role, msg.content, false);
    }
    scrollToBottom(false);
  } catch (e) {
    console.warn('Load messages error:', e);
  }
}

async function createConversation() {
  try {
    const r = await fetch('/api/conversations', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title: 'New Conversation' }),
    });
    if (!r.ok) throw new Error('create failed');
    const conv = await r.json();
    conversations.unshift(conv);
    currentConvId = conv.id;
    chatTitle.textContent = 'New Conversation';
    messagesContainer.innerHTML = '';
    welcomeScreen.style.display = 'flex';
    renderConversationList();
    messageInput.focus();
    return conv.id;
  } catch (e) {
    console.warn('Create conversation error:', e);
    return null;
  }
}

async function deleteConversation(convId) {
  if (!confirm('Delete this conversation? This cannot be undone.')) return;
  try {
    await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
    conversations = conversations.filter(c => c.id !== convId);
    if (currentConvId === convId) {
      currentConvId = null;
      chatTitle.textContent = 'F.R.I.D.A.Y.';
      messagesContainer.innerHTML = '';
      welcomeScreen.style.display = 'flex';
    }
    renderConversationList();
    showToast('Conversation deleted');
  } catch (e) {
    showToast('Delete failed');
  }
}

function openRenameModal(convId, currentTitle) {
  renameTargetId       = convId;
  renameInput.value    = currentTitle || '';
  renameModal.hidden   = false;
  renameInput.focus();
  renameInput.select();
}

async function saveRename() {
  const newTitle = renameInput.value.trim();
  if (!newTitle || !renameTargetId) return;
  try {
    const r = await fetch(`/api/conversations/${renameTargetId}`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title: newTitle }),
    });
    if (!r.ok) throw new Error('rename failed');
    const idx = conversations.findIndex(c => c.id === renameTargetId);
    if (idx !== -1) conversations[idx].title = newTitle;
    if (currentConvId === renameTargetId) chatTitle.textContent = newTitle;
    renderConversationList();
    showToast('Renamed');
  } catch (e) {
    showToast('Rename failed');
  } finally {
    renameModal.hidden = true;
    renameTargetId     = null;
  }
}

/* ════════════════════════════════════════════════════════════════════
   CHAT / STREAMING
   ════════════════════════════════════════════════════════════════════ */
async function sendMessage() {
  const text = messageInput.value.trim();
  if (!text || isStreaming) return;

  // Ensure we have a conversation
  if (!currentConvId) {
    const id = await createConversation();
    if (!id) { showToast('Could not start conversation'); return; }
  }

  // Clear input
  messageInput.value = '';
  autoResize();
  sendBtn.disabled = true;

  // Hide welcome, show user message
  welcomeScreen.style.display = 'none';
  appendMessage('user', text);
  scrollToBottom();

  // Streaming AI response
  isStreaming = true;
  const thinkingRow = appendTypingIndicator();
  scrollToBottom();

  let fullText = '';
  let assistantRow = null;
  let bubbleEl = null;

  try {
    const resp = await fetch('/chat/stream', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message: text, conversation_id: currentConvId }),
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer    = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let payload;
        try { payload = JSON.parse(line.slice(6)); } catch { continue; }

        if (payload.text !== undefined) {
          // First chunk — remove typing indicator, create assistant message
          if (thinkingRow.parentNode) thinkingRow.remove();
          if (!assistantRow) {
            const result      = appendMessage('assistant', '', false, /* returnEl */ true);
            assistantRow      = result.row;
            bubbleEl          = result.bubble;
          }
          fullText += payload.text;
          renderMarkdown(bubbleEl, fullText);
          scrollToBottom();
        }

        if (payload.done) break;
      }
    }
  } catch (err) {
    console.error('Stream error:', err);
    if (thinkingRow.parentNode) thinkingRow.remove();
    appendMessage('assistant', '⚠ Connection error — please try again.');
  } finally {
    isStreaming = false;
    sendBtn.disabled = messageInput.value.trim().length === 0;

    // Apply syntax highlighting to any new code blocks
    messagesContainer.querySelectorAll('pre code:not(.hljs-applied)').forEach(el => {
      if (window.hljs) {
        window.hljs.highlightElement(el);
        el.classList.add('hljs-applied');
      }
    });

    // Update conversation list (title may have been set server-side)
    await loadConversations();
  }
}

/* ── Message rendering ──────────────────────────────────────────────── */
function appendMessage(role, content, animate = true, returnEl = false) {
  const row = document.createElement('div');
  row.className = `message-row ${role}`;
  if (!animate) row.style.animation = 'none';

  // Avatar
  const avatar = document.createElement('div');
  if (role === 'user') {
    avatar.className  = 'avatar user-avatar';
    avatar.textContent = 'U';
  } else {
    avatar.className  = 'avatar ai-avatar';
    avatar.innerHTML  = `<svg width="14" height="14" viewBox="0 0 28 28" fill="none"><circle cx="14" cy="14" r="5" fill="#60a5fa"/><circle cx="14" cy="14" r="11" stroke="#60a5fa" stroke-width="1.5"/></svg>`;
  }

  const msgContent = document.createElement('div');
  msgContent.className = 'message-content';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';

  if (content) {
    if (role === 'assistant') {
      renderMarkdown(bubble, content);
    } else {
      bubble.textContent = content;
    }
  }

  msgContent.appendChild(bubble);
  row.appendChild(avatar);
  row.appendChild(msgContent);
  messagesContainer.appendChild(row);

  if (returnEl) return { row, bubble };
  return row;
}

function appendTypingIndicator() {
  const row = document.createElement('div');
  row.className = 'message-row assistant';
  row.id        = 'typingRow';

  const avatar = document.createElement('div');
  avatar.className  = 'avatar ai-avatar';
  avatar.innerHTML  = `<svg width="14" height="14" viewBox="0 0 28 28" fill="none"><circle cx="14" cy="14" r="5" fill="#60a5fa"/><circle cx="14" cy="14" r="11" stroke="#60a5fa" stroke-width="1.5"/></svg>`;

  const msgContent = document.createElement('div');
  msgContent.className = 'message-content';

  const indicator = document.createElement('div');
  indicator.className = 'typing-indicator';
  indicator.innerHTML = `<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>`;

  msgContent.appendChild(indicator);
  row.appendChild(avatar);
  row.appendChild(msgContent);
  messagesContainer.appendChild(row);
  return row;
}

/* ── Markdown renderer ──────────────────────────────────────────────── */
function renderMarkdown(el, text) {
  // Security: escape HTML first, then selectively unescape for rendering
  let html = escapeHtml(text);

  // Code blocks (```lang\ncode\n```)
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const displayLang = lang || 'plaintext';
    const rawCode     = unescapeHtml(code.trim());
    return buildCodeBlock(displayLang, rawCode);
  });

  // Inline code
  html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');

  // Bold **text**
  html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  // Italic *text*  or _text_
  html = html.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>');
  html = html.replace(/_([^_\n]+)_/g, '<em>$1</em>');

  // Headings
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm,  '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm,   '<h1>$1</h1>');

  // Unordered lists (run of - or * lines)
  html = html.replace(/((?:^[-*] .+\n?)+)/gm, match => {
    const items = match.trim().split('\n').map(l => `<li>${l.replace(/^[-*] /, '')}</li>`).join('');
    return `<ul>${items}</ul>`;
  });

  // Ordered lists
  html = html.replace(/((?:^\d+\. .+\n?)+)/gm, match => {
    const items = match.trim().split('\n').map(l => `<li>${l.replace(/^\d+\. /, '')}</li>`).join('');
    return `<ol>${items}</ol>`;
  });

  // URLs — linkify bare http(s) URLs (not already in anchor or code)
  html = html.replace(/(?<!['"=])https?:\/\/[^\s<>"]+/g, url => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);

  // Paragraphs — double newlines
  html = html.replace(/\n{2,}/g, '</p><p>');
  // Single newlines → <br> only outside block elements
  html = html.replace(/([^>])\n([^<])/g, '$1<br>$2');

  el.innerHTML = `<p>${html}</p>`;

  // Apply highlight.js to newly inserted code blocks
  el.querySelectorAll('pre code:not(.hljs-applied)').forEach(codeEl => {
    if (window.hljs) {
      window.hljs.highlightElement(codeEl);
      codeEl.classList.add('hljs-applied');
    }
    // Wire copy button
    const wrapper = codeEl.closest('.code-block-wrapper');
    if (wrapper) {
      const copyBtn = wrapper.querySelector('.copy-code-btn');
      if (copyBtn) {
        copyBtn.addEventListener('click', () => {
          navigator.clipboard.writeText(codeEl.textContent).then(() => {
            copyBtn.classList.add('copied');
            copyBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg> Copied!`;
            setTimeout(() => {
              copyBtn.classList.remove('copied');
              copyBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy`;
            }, 2000);
          });
        });
      }
    }
  });
}

function buildCodeBlock(lang, code) {
  const safeCode = escapeHtml(code);
  return `<div class="code-block-wrapper">
    <div class="code-block-header">
      <span class="code-lang-label">${lang}</span>
      <button class="copy-code-btn" type="button">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
        </svg> Copy
      </button>
    </div>
    <pre><code class="language-${lang}">${safeCode}</code></pre>
  </div>`;
}

function escapeHtml(s) {
  return s
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#039;');
}

function unescapeHtml(s) {
  return s
    .replace(/&amp;/g,  '&')
    .replace(/&lt;/g,   '<')
    .replace(/&gt;/g,   '>')
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'");
}

/* ── Scroll helper ──────────────────────────────────────────────────── */
function scrollToBottom(smooth = true) {
  messagesArea.scrollTo({
    top:      messagesArea.scrollHeight,
    behavior: smooth ? 'smooth' : 'instant',
  });
}

/* ── Auto-resize textarea ───────────────────────────────────────────── */
function autoResize() {
  messageInput.style.height = 'auto';
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + 'px';
}

/* ════════════════════════════════════════════════════════════════════
   VOICE INPUT
   ════════════════════════════════════════════════════════════════════ */
async function toggleVoice() {
  if (isRecording) {
    stopRecording();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks  = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(audioChunks, { type: 'audio/webm' });
      await transcribeAudio(blob);
    };
    mediaRecorder.start();
    isRecording = true;
    voiceBtn.classList.add('recording');
  } catch (e) {
    showToast('Microphone access denied');
  }
}

function stopRecording() {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
    voiceBtn.classList.remove('recording');
  }
}

async function transcribeAudio(blob) {
  // Use browser SpeechRecognition if available (free, no server round-trip)
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    // We already recorded via MediaRecorder; for simplicity, restart recognition
    const recog = new SpeechRecognition();
    recog.lang  = 'en-US';
    recog.onresult = e => {
      const transcript = e.results[0][0].transcript;
      messageInput.value = transcript;
      autoResize();
      sendBtn.disabled = false;
      messageInput.focus();
    };
    recog.onerror = () => showToast('Speech recognition failed');
    recog.start();
    return;
  }
  showToast('Voice recognition not supported in this browser');
}

/* ════════════════════════════════════════════════════════════════════
   TOAST
   ════════════════════════════════════════════════════════════════════ */
let _toastTimer = null;
function showToast(msg, duration = 2500) {
  toastEl.textContent = msg;
  toastEl.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => toastEl.classList.remove('show'), duration);
}

/* ════════════════════════════════════════════════════════════════════
   EVENT BINDINGS
   ════════════════════════════════════════════════════════════════════ */
function bindEvents() {
  /* Sidebar toggle */
  sidebarToggleBtn.addEventListener('click', () => sidebar.classList.add('collapsed'));
  openSidebarBtn.addEventListener('click',   () => sidebar.classList.remove('collapsed'));

  /* New chat */
  newChatBtn.addEventListener('click', async () => {
    await createConversation();
    messageInput.focus();
  });

  /* Welcome chips */
  document.querySelectorAll('.suggestion-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      messageInput.value = chip.dataset.msg;
      autoResize();
      sendBtn.disabled = false;
      sendMessage();
    });
  });

  /* Input field */
  messageInput.addEventListener('input', () => {
    autoResize();
    sendBtn.disabled = messageInput.value.trim().length === 0 || isStreaming;
  });

  messageInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) sendMessage();
    }
  });

  /* Send button */
  sendBtn.addEventListener('click', sendMessage);

  /* Voice */
  voiceBtn.addEventListener('click', toggleVoice);

  /* Clear chat */
  clearChatBtn.addEventListener('click', async () => {
    if (!currentConvId) return;
    if (!confirm('Clear all messages in this conversation?')) return;
    try {
      await fetch(`/api/conversations/${currentConvId}/clear`, { method: 'POST' });
      messagesContainer.innerHTML = '';
      welcomeScreen.style.display = 'flex';
      // Reset AI context on server
      await fetch('/chat/reset', { method: 'POST' });
      showToast('Conversation cleared');
    } catch {
      showToast('Could not clear conversation');
    }
  });

  /* Rename modal */
  renameSaveBtn.addEventListener('click',   saveRename);
  renameCancelBtn.addEventListener('click', () => { renameModal.hidden = true; });
  renameInput.addEventListener('keydown',   e => { if (e.key === 'Enter') saveRename(); if (e.key === 'Escape') renameModal.hidden = true; });
  renameModal.addEventListener('click',     e => { if (e.target === renameModal) renameModal.hidden = true; });

  /* Auto-start a new chat when clicking into empty state */
  welcomeScreen.addEventListener('click', e => {
    if (e.target === welcomeScreen && !currentConvId) {
      messageInput.focus();
    }
  });
}
