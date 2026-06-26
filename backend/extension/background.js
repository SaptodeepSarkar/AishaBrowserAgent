let socket = null;
let agentTabId = null;
let isWatched = false;

// Initial badge state
chrome.action.setBadgeText({ text: "OFF" });
chrome.action.setBadgeBackgroundColor({ color: "#666" });

function connect() {
    socket = new WebSocket("ws://127.0.0.1:8763/ws/extension");

    socket.onopen = async () => {
        console.log("[AISha Bridge] Connected to Python server");
        chrome.action.setBadgeText({ text: "ON" });
        chrome.action.setBadgeBackgroundColor({ color: "#a855f7" });

        // Create the agent tab (start.html) silently — this is where the user browses and the agent acts
        ensureAgentTab();
    };

    socket.onmessage = (event) => {
        const command = JSON.parse(event.data);
        if (agentTabId) {
            chrome.tabs.sendMessage(agentTabId, command).catch(() => {});
        }
    };

    socket.onclose = () => {
        console.log("[AISha Bridge] Disconnected.");
        socket = null;
        isWatched = false;
        chrome.action.setBadgeText({ text: "OFF" });
        chrome.action.setBadgeBackgroundColor({ color: "#666" });
        setTimeout(connect, 2000);
    };

    socket.onerror = () => {
        console.log("[AISha Bridge] Connection error.");
        socket = null;
        chrome.action.setBadgeText({ text: "OFF" });
        chrome.action.setBadgeBackgroundColor({ color: "#666" });
    };
}

async function ensureAgentTab() {
    // Don't recreate if we already have a valid tab
    if (agentTabId) {
        try {
            await chrome.tabs.get(agentTabId);
            return; // tab still exists
        } catch {
            // tab was closed — fall through to create a new one
        }
    }

    const allTabs = await chrome.tabs.query({});
    const existing = allTabs.find(t =>
        t.url && t.url.includes("localhost:3000/start.html")
    );
    if (existing) {
        agentTabId = existing.id;
        console.log("[AISha Bridge] Reusing existing agent tab:", agentTabId);
    } else {
        try {
            const tab = await chrome.tabs.create({
                url: "http://localhost:3000/start.html",
                active: false  // no focus steal
            });
            agentTabId = tab.id;
            console.log("[AISha Bridge] Created agent tab:", agentTabId);
        } catch (e) {
            console.error("[AISha Bridge] Failed to create agent tab:", e);
        }
    }
}

// Track if agent tab is closed by the user
chrome.tabs.onRemoved.addListener(async (tabId) => {
    if (tabId === agentTabId) {
        console.log("[AISha Bridge] Agent tab was closed. Recreating...");
        agentTabId = null;
        isWatched = false;
        // If socket is still connected, recreate the agent tab immediately
        if (socket && socket.readyState === WebSocket.OPEN) {
            await ensureAgentTab();
        }
    }
});

// Navigate away from start.html → still our agent tab (user browsed somewhere)
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
    if (tabId === agentTabId && changeInfo.url) {
        console.log("[AISha Bridge] Agent tab navigated to:", changeInfo.url);
    }
});

// Forward messages from content script to WebSocket server
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if ((message.type === "action_result" || message.type === "dom_update") && socket && socket.readyState === WebSocket.OPEN) {
        // Only forward messages from the agent tab
        if (!sender.tab || sender.tab.id === agentTabId) {
            socket.send(JSON.stringify(message));
        }
    }
    else if (message.type === "get_status") {
        sendResponse({
            connected: !!(socket && socket.readyState === WebSocket.OPEN),
            agentTabCreated: !!agentTabId,
            isWatched: isWatched
        });
    }
    else if (message.type === "set_agent_tab") {
        agentTabId = message.tabId;
        console.log("[AISha Bridge] Agent tab set to:", agentTabId);
        sendResponse({ success: true });
    }
    else if (message.type === "verify_agent_tab") {
        // Check if a given tabId is the agent tab
        const tabId = message.tabId;
        sendResponse({
            isAgentTab: tabId === agentTabId
        });
    }
    else if (message.type === "set_watched_tab") {
        (async () => {
            try {
                const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
                if (!tab) {
                    sendResponse({ success: false, error: "No active tab found" });
                    return;
                }
                if (tab.id !== agentTabId) {
                    sendResponse({ success: false, error: "Not on the agent tab" });
                    return;
                }
                // Trigger an immediate DOM update to start streaming
                chrome.tabs.sendMessage(agentTabId, { action: "get_dom" }).catch(() => {
                    console.warn("[AISha Bridge] Agent tab not ready yet");
                });
                isWatched = true;
                // Notify server via WebSocket
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({
                        type: "watched_tab_changed",
                        content: { tabId: agentTabId, url: tab.url }
                    }));
                }
                sendResponse({ success: true, url: tab.url });
            } catch (e) {
                sendResponse({ success: false, error: e.message });
            }
        })();
        return true;
    }
    else if (message.type === "get_watched") {
        sendResponse({
            watched: isWatched,
            tabId: agentTabId
        });
    }
    return true;
});

connect();
