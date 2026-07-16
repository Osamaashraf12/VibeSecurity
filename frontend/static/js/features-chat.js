console.log('[Features] Loading features-chat.js...');

// --- CHAT & ASSISTANT LOGIC ---

/**
 * Initializes the main AI Security Chat view.
 */
function initChat() {
    const chatContainer = document.querySelector('#view-ai-assistant .chat-container');
    if (!chatContainer) return;
    const messages = chatContainer.querySelector('#chat-messages');
    const input = chatContainer.querySelector('#chat-input');
    const sendBtn = chatContainer.querySelector('#send-btn');
    const mentorBtn = chatContainer.querySelector('#mode-mentor-btn');
    const hunterBtn = chatContainer.querySelector('#mode-hunter-btn');
    let currentMode = 'mentor';

    if (!messages || !input || !sendBtn) return;

    if (mentorBtn && hunterBtn) {
        mentorBtn.addEventListener('click', () => {
            currentMode = 'mentor';
            window._chatMode = 'mentor';
            window._hunterSend = null;
            mentorBtn.style.background = 'var(--color-primary)';
            mentorBtn.style.color = 'white';
            hunterBtn.style.background = 'transparent';
            hunterBtn.style.color = 'var(--color-text)';

            chatContainer.querySelector('.chat-title h2').textContent = 'AI Security Chat';
            chatContainer.style.border = 'none';
            chatContainer.style.boxShadow = 'none';
            sendBtn.style.background = 'var(--color-primary)';
            input.placeholder = 'Ask me about security testing, vulnerabilities, or best practices...';
        });

        hunterBtn.addEventListener('click', () => {
            currentMode = 'hunter';
            window._chatMode = 'hunter';  // shared flag for sendMessage dispatcher
            hunterBtn.style.background = '#ef4444';
            hunterBtn.style.color = 'white';
            mentorBtn.style.background = 'transparent';
            mentorBtn.style.color = 'var(--color-text)';

            chatContainer.querySelector('.chat-title h2').textContent = 'AI HUNTER AGENT (Hunter Mode)';
            chatContainer.style.border = '1px solid #ef4444';
            chatContainer.style.boxShadow = '0 0 15px rgba(239, 68, 68, 0.2)';
            sendBtn.style.background = '#ef4444';
            input.placeholder = 'Hunter Mode: type a target URL (e.g. https://example.com) and press Enter...';

            if (typeof initHunterAgent === 'function') {
                initHunterAgent(messages);
            }
        });
    }

    function appendMessage(type, text) {
        const msg = document.createElement('div');
        msg.className = `message ${type}`;
        const formattedText = text.replace(/\n/g, '<br>');
        msg.innerHTML = `
            <div class="message-avatar">${type === 'user' ? 'You' : 'AI'}</div>
            <div class="message-content"><p>${formattedText}</p></div>
        `;
        messages.appendChild(msg);
        messages.scrollTop = messages.scrollHeight;
    }

    // ── Mode-aware send dispatcher ──────────────────────────────────────────
    // initHunterAgent() sets window._hunterSend to intercept messages in hunter mode.
    // In mentor mode that global is null and sendMessage runs normally.
    async function sendMessage() {
        // Delegate to hunter mode handler if active
        if (window._chatMode === 'hunter' && typeof window._hunterSend === 'function') {
            window._hunterSend(input, messages);
            return;
        }

        const text = input.value.trim();
        if (!text) return;
        appendMessage('user', text);
        input.value = '';

        const loadingId = 'loading-' + Date.now();
        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'message bot loading-msg';
        loadingMsg.id = loadingId;
        loadingMsg.innerHTML = `<div class="message-avatar">AI</div><div class="message-content"><p>Thinking...</p></div>`;
        messages.appendChild(loadingMsg);
        messages.scrollTop = messages.scrollHeight;

        if (isOffline()) {
            setTimeout(() => {
                document.getElementById(loadingId).remove();
                appendMessage('bot', "I am currently in Offline Mode. Please start the VibeSecurity server to enable the AI Security Chat.");
            }, 1000);
            return;
        }

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });

            if (!response.ok) throw new Error('Network response was not ok');
            const data = await response.json();

            document.getElementById(loadingId).remove();
            appendMessage('bot', data.response);

        } catch (error) {
            if (document.getElementById(loadingId)) document.getElementById(loadingId).remove();
            appendMessage('bot', "Error: Could not connect to the AI server.");
        }
    }

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keypress', e => e.key === 'Enter' && sendMessage());

    document.querySelectorAll('.quick-action-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            input.value = btn.dataset.prompt;
            sendMessage();
        });
    });
}

/**
 * Helpers for the "Scan Assistant" sidebars found in recon views.
 */
function getActiveContext() {
    const activeView = document.querySelector('.view.active');
    return activeView || document.body;
}

function askScanAssistant(message) {
    const context = getActiveContext();
    const input = context.querySelector('.scan-assistant-input input');
    if (input) {
        input.value = message;
        sendScanAssistantMessage();
    }
}

function sendScanAssistantMessage() {
    const context = getActiveContext();
    const input = context.querySelector('.scan-assistant-input input');
    const messages = context.querySelector('.scan-assistant-messages');
    if (!input || !messages) return;
    const text = input.value.trim();
    if (!text) return;

    const userMessage = document.createElement('div');
    userMessage.className = 'scan-assistant-message user';
    userMessage.innerHTML = `<div class="scan-assistant-message-avatar">You</div><div class="scan-assistant-message-content"><p>${text}</p></div>`;
    messages.appendChild(userMessage);
    input.value = '';
    messages.scrollTop = messages.scrollHeight;

    setTimeout(() => {
        const botMessage = document.createElement('div');
        botMessage.className = 'scan-assistant-message bot';
        botMessage.innerHTML = `<div class="scan-assistant-message-avatar">AI</div><div class="scan-assistant-message-content"><p>I'm analyzing your request within the context of this module. How can I help further?</p></div>`;
        messages.appendChild(botMessage);
        messages.scrollTop = messages.scrollHeight;
    }, 1000);
}

// --- HUNTER AGENT ---

function initHunterAgent(messagesEl) {
    console.log('[HunterAgent] Registering hunter send delegate...');

    // ── State ─────────────────────────────────────────────────────────────
    let hunterSessionId = null;
    let hunterCursor = 0;
    let hunterPollTimer = null;

    // ── Message renderer ──────────────────────────────────────────────────
    function appendHunterMessage(text) {
        if (!messagesEl) return;
        const msg = document.createElement('div');
        msg.className = 'message bot';
        msg.innerHTML = `
            <div class="message-avatar" style="background:#ef4444;">HA</div>
            <div class="message-content"><p>${text.replace(/\n/g, '<br>')}</p></div>
        `;
        messagesEl.appendChild(msg);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function appendUserMessage(text) {
        if (!messagesEl) return;
        const msg = document.createElement('div');
        msg.className = 'message user';
        msg.innerHTML = `
            <div class="message-avatar">You</div>
            <div class="message-content"><p>${text}</p></div>
        `;
        messagesEl.appendChild(msg);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    // ── Hunter send handler (assigned to window._hunterSend) ───────────────
    // Receives the input element so it can read and clear the value.
    async function handleHunterSend(inputEl) {
        const text = inputEl.value.trim();
        if (!text) return;
        inputEl.value = '';

        // Already scanning?
        if (hunterSessionId) {
            appendHunterMessage('A scan is already in progress. Please wait for it to complete.');
            return;
        }

        // Normalise URL
        let targetUrl = text;
        if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) {
            targetUrl = 'https://' + targetUrl;
        }

        appendUserMessage(text);
        appendHunterMessage('Starting Hunter Agent pipeline on ' + targetUrl + '...');

        try {
            const res = await fetch('/api/hunter/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: targetUrl }),
            });
            const data = await res.json();

            if (res.ok && data.session_id) {
                hunterSessionId = data.session_id;
                hunterCursor = 0;
                appendHunterMessage('Session ' + hunterSessionId + ' started. Polling for updates...');
                startHunterPolling();
            } else {
                appendHunterMessage('Failed to start scan: ' + (data.error || data.message || 'Unknown error'));
            }
        } catch (err) {
            appendHunterMessage('Error connecting to server: ' + err.message);
        }
    }

    // Register as the global delegate — sendMessage() calls this in hunter mode
    window._hunterSend = handleHunterSend;

    // ── Polling ───────────────────────────────────────────────────────────
    function startHunterPolling() {
        if (hunterPollTimer) clearInterval(hunterPollTimer);
        pollHunterStatus();
        hunterPollTimer = setInterval(pollHunterStatus, 3000);
    }

    async function pollHunterStatus() {
        if (!hunterSessionId) return;
        try {
            const res = await fetch('/api/hunter/status/' + hunterSessionId + '?cursor=' + hunterCursor);
            const data = await res.json();

            if (data.entries && data.entries.length > 0) {
                for (const entry of data.entries) {
                    appendHunterMessage(entry.message || JSON.stringify(entry));
                }
                hunterCursor = data.next_cursor;
            }

            if (data.complete) {
                clearInterval(hunterPollTimer);
                hunterPollTimer = null;
                if (data.phase === 'error') {
                    appendHunterMessage('Scan ended with an error. Check server logs for details.');
                } else {
                    appendHunterMessage('Scan complete. Fetching report...');
                    await fetchHunterReport();
                }
                hunterSessionId = null;
                hunterCursor = 0;
            }
        } catch (err) {
            console.error('[HunterAgent] Polling error:', err);
        }
    }

    async function fetchHunterReport() {
        try {
            const res = await fetch('/api/hunter/report/' + hunterSessionId);
            if (!res.ok) {
                appendHunterMessage('Report not available yet. Check the Artifacts sidebar.');
                return;
            }
            const report = await res.json();
            const findings = report.findings || [];
            const score    = report.summary?.risk_score ?? 'N/A';
            const exec     = report.summary?.executive_text || '';

            appendHunterMessage(
                'Report ready: ' + findings.length + ' findings, risk score ' + score +
                (exec ? '\n\n' + exec : '')
            );

            for (const f of findings.slice(0, 5)) {
                appendHunterMessage(
                    '[' + (f.severity || 'Medium') + '] ' + (f.title || 'Untitled') +
                    '\nLocation: ' + (f.location || 'N/A') +
                    '\n' + (f.description || '').substring(0, 200)
                );
            }
            if (findings.length > 5) {
                appendHunterMessage('... and ' + (findings.length - 5) + ' more. View hunter_report.json in Artifacts.');
            }
        } catch (err) {
            appendHunterMessage('Could not fetch report: ' + err.message);
        }
    }
}
