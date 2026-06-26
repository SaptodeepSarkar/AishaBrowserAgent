async function init() {
    const backendEl = document.getElementById('backend-status');
    const agentTabEl = document.getElementById('agent-tab-status');
    const btn = document.getElementById('broadcast-btn');
    const hintEl = document.getElementById('hint-text');
    const infoEl = document.getElementById('watching-info');

    // 1. Check Backend (port 8763)
    let backendOk = false;
    try {
        const res = await fetch('http://127.0.0.1:8763/api/chats', {
            method: 'GET',
            signal: AbortSignal.timeout(3000)
        });
        if (res.ok) {
            backendEl.textContent = 'Running';
            backendEl.className = 'value online';
            backendOk = true;
        } else {
            backendEl.textContent = 'Error';
            backendEl.className = 'value offline';
        }
    } catch {
        backendEl.textContent = 'Disconnected';
        backendEl.className = 'value offline';
    }

    // 2. Get background status
    let bgStatus = null;
    try {
        bgStatus = await chrome.runtime.sendMessage({ type: "get_status" });
    } catch {
        // background not reachable
    }

    let agentTabCreated = bgStatus && bgStatus.connected && bgStatus.agentTabCreated;
    const isWatched = bgStatus && bgStatus.isWatched;

    // 3. Wait briefly for agent tab to be created (background creates it on connect)
    if (!agentTabCreated && backendOk) {
        for (let i = 0; i < 10; i++) {
            await new Promise(r => setTimeout(r, 300));
            try {
                const retry = await chrome.runtime.sendMessage({ type: "get_status" });
                if (retry && retry.connected && retry.agentTabCreated) {
                    agentTabCreated = true;
                    break;
                }
            } catch {}
        }
    }

    // Show agent tab status
    if (agentTabCreated) {
        agentTabEl.textContent = 'Ready';
        agentTabEl.className = 'value online';
    } else {
        agentTabEl.textContent = 'Waiting...';
        agentTabEl.className = 'value offline';
    }

    // 4. Show watching status
    if (isWatched) {
        infoEl.textContent = '📡 Broadcasting live — check the chat UI';
        infoEl.className = 'watching-info visible';
    } else {
        infoEl.className = 'watching-info';
    }

    // 5. Check if current tab is the agent tab
    if (backendOk && agentTabCreated) {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab) {
                const verify = await chrome.runtime.sendMessage({
                    type: "verify_agent_tab",
                    tabId: tab.id
                });
                const onAgentTab = verify && verify.isAgentTab;
                if (isWatched) {
                    // Already broadcasting
                    btn.textContent = '✓ Broadcasting';
                    btn.className = 'btn btn-success';
                    btn.disabled = true;
                    hintEl.textContent = 'Live — check the chat UI to watch';
                } else if (onAgentTab) {
                    // On agent tab, not yet broadcasting — enable button
                    btn.textContent = 'Broadcast This Tab';
                    btn.className = 'btn btn-primary';
                    btn.disabled = false;
                    btn.title = 'Share this tab with the assistant';
                    hintEl.textContent = 'On agent tab — press to broadcast';
                } else {
                    btn.textContent = 'Broadcast This Tab';
                    btn.className = 'btn btn-primary';
                    btn.disabled = true;
                    btn.title = 'Switch to the agent tab first';
                    hintEl.textContent = 'Switch to the agent tab to broadcast';
                }
            }
        } catch {
            btn.disabled = true;
            hintEl.textContent = 'Error checking tab';
        }
    } else {
        btn.disabled = true;
        hintEl.textContent = !backendOk
            ? 'Start the backend server first'
            : 'Waiting for agent tab to be created...';
    }
}

// Broadcast button click
document.getElementById('broadcast-btn').addEventListener('click', async () => {
    const btn = document.getElementById('broadcast-btn');
    const hintEl = document.getElementById('hint-text');
    const infoEl = document.getElementById('watching-info');

    btn.textContent = 'Starting broadcast...';
    btn.disabled = true;

    try {
        const resp = await chrome.runtime.sendMessage({ type: "set_watched_tab" });
        if (resp && resp.success) {
            btn.textContent = '✓ Broadcasting';
            btn.className = 'btn btn-success';
            btn.disabled = true;
            infoEl.textContent = '📡 Broadcasting live — check the chat UI';
            infoEl.className = 'watching-info visible';
            hintEl.textContent = 'Go to the chat UI to watch the agent live';
        } else {
            btn.textContent = 'Broadcast This Tab';
            btn.disabled = false;
            hintEl.textContent = resp?.error || 'Failed to start broadcast';
        }
    } catch (e) {
        console.error('[Popup] Error:', e);
        btn.textContent = 'Broadcast This Tab';
        btn.disabled = false;
        hintEl.textContent = 'Error — check console';
    }
});

init();
