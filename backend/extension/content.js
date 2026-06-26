console.log("[AISha Bridge] Content script active");

let isLocked = false;
let lockOverlay = null;

function setLock(locked) {
    isLocked = locked;
    if (locked && !lockOverlay) {
        lockOverlay = document.createElement("div");
        lockOverlay.id = "aisha-lock-overlay";
        
        // Add animation style if not exists
        if (!document.getElementById('aisha-lock-styles')) {
            const style = document.createElement('style');
            style.id = 'aisha-lock-styles';
            style.innerHTML = `
                @keyframes aisha-glow-pulse {
                    0% { box-shadow: inset 0 0 30px rgba(255, 0, 255, 0.4); }
                    50% { box-shadow: inset 0 0 60px rgba(255, 0, 255, 0.7); }
                    100% { box-shadow: inset 0 0 30px rgba(255, 0, 255, 0.4); }
                }
            `;
            document.head.appendChild(style);
        }

        Object.assign(lockOverlay.style, {
            position: "fixed",
            top: "0",
            left: "0",
            width: "100vw",
            height: "100vh",
            backgroundColor: "transparent",
            zIndex: "2147483647",
            cursor: "not-allowed",
            pointerEvents: "all",
            border: "4px solid rgba(255, 0, 255, 0.5)",
            boxSizing: "border-box",
            animation: "aisha-glow-pulse 2s infinite ease-in-out"
        });
        
        document.body.appendChild(lockOverlay);
    } else if (!locked && lockOverlay) {
        lockOverlay.remove();
        lockOverlay = null;
    }
}

function getDOMSummary() {
    const interactiveElements = [];
    const elements = document.querySelectorAll("a, button, input, select, textarea, [role='button'], [onclick], h1, h2, h3, p");
    
    elements.forEach((el, index) => {
        const rect = el.getBoundingClientRect();
        const isVisible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
        
        if (isVisible) {
            const id = `el_${index}`;
            el.setAttribute("data-aisha-id", id);
            const data = {
                id: id,
                tag: el.tagName,
                text: el.innerText.trim().substring(0, 200), // Increased limit for better context
                type: el.type || "",
                placeholder: el.placeholder || ""
            };
            // Include href for anchor tags so the LLM knows the destination URL
            if (el.tagName === "A" && el.href) {
                data.href = el.href;
            }
            interactiveElements.push(data);
        }
    });

    return {
        url: window.location.href,
        title: document.title,
        elements: interactiveElements,
        pageText: document.body.innerText.substring(0, 2000).replace(/\s+/g, ' ')
    };
}

// Listen for commands from background -> Python
chrome.runtime.onMessage.addListener((command, sender, sendResponse) => {
    if (command.type === "action") {
        const action = command.content;
        let resultMsg = "Action executed successfully.";
        
        try {
            if (action.action === "lock") {
                setLock(true);
            } else if (action.action === "unlock") {
                setLock(false);
            } else if (action.action === "click") {
                const el = document.querySelector(`[data-aisha-id="${action.element_id}"]`);
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    // Simulate full click lifecycle for complex React/Polymer sites like YouTube
                    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                    el.click();
                    resultMsg = `Successfully clicked element ${action.element_id}.`;
                } else {
                    resultMsg = `FAILED: Element ${action.element_id} not found on the page. The DOM may have changed.`;
                }
            } else if (action.action === "click_label") {
                const label = action.label.toLowerCase();
                const elements = Array.from(document.querySelectorAll("a, button, input, [role='button']"));
                const target = elements.find(el => 
                    el.innerText.toLowerCase().includes(label) || 
                    (el.value && el.value.toLowerCase().includes(label)) ||
                    (el.ariaLabel && el.ariaLabel.toLowerCase().includes(label))
                );

                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    target.click();
                    resultMsg = `Successfully clicked element with label: "${action.label}"`;
                } else {
                    resultMsg = `FAILED: No element found with label: "${action.label}"`;
                }
            } else if (action.action === "click_pixel") {
                const x = parseInt(action.x, 10);
                const y = parseInt(action.y, 10);
                if (isNaN(x) || isNaN(y)) {
                    resultMsg = `FAILED: Invalid pixel coordinates x=${action.x}, y=${action.y}.`;
                } else {
                    // Temporarily hide our lock overlay so elementFromPoint finds the real element
                    if (lockOverlay) lockOverlay.style.pointerEvents = "none";
                    const el = document.elementFromPoint(x, y);
                    if (lockOverlay) lockOverlay.style.pointerEvents = "all";

                    if (el) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        // Recalculate position after scroll
                        const rect = el.getBoundingClientRect();
                        const clickX = rect.left + rect.width / 2;
                        const clickY = rect.top + rect.height / 2;
                        el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, clientX: clickX, clientY: clickY }));
                        el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, clientX: clickX, clientY: clickY }));
                        el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, clientX: clickX, clientY: clickY }));
                        resultMsg = `Successfully clicked at pixel (${x}, ${y}) — hit element: <${el.tagName.toLowerCase()}>${el.innerText ? " '" + el.innerText.substring(0, 50) + "'" : ""}.`;
                    } else {
                        // No element found at that point — dispatch click directly on document
                        document.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, clientX: x, clientY: y }));
                        resultMsg = `Clicked at pixel (${x}, ${y}) — no specific element found, dispatched click on document.`;
                    }
                }
            } else if (action.action === "type") {
                const el = document.querySelector(`[data-aisha-id="${action.element_id}"]`);
                if (el) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    el.focus();
                    el.value = action.text;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    if (action.press_enter) {
                        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                        el.dispatchEvent(new KeyboardEvent('keypress', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                        el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
                        
                        // Fallback for search bars: try to find and submit the parent form
                        const form = el.closest('form');
                        if (form) {
                            form.submit();
                        }
                    }
                    resultMsg = `Successfully typed text into element ${action.element_id}.`;
                } else {
                    resultMsg = `FAILED: Element ${action.element_id} not found. Cannot type text.`;
                }
            } else if (action.action === "scroll") {
                const distance = action.direction === "down" ? 600 : -600;
                window.scrollBy({ top: distance, behavior: 'smooth' });
                resultMsg = `Successfully scrolled ${action.direction}.`;
            } else if (action.action === "navigate") {
                // Report result FIRST, then navigate.
                // After navigation, this content script dies.
                // The NEW page's content script will send its own initial DOM.
                chrome.runtime.sendMessage({
                    type: "action_result",
                    content: `Successfully started navigation to ${action.url}.`
                });
                window.location.href = action.url;
                return; // Don't send DOM — we're leaving this page
            } else if (action.action === "get_dom") {
                sendUpdate();
                resultMsg = "DOM update requested and sent.";
            }
        } catch (err) {
            resultMsg = `FAILED with JavaScript error: ${err.message}`;
        }
        
        // Report result back to server
        if (action.action !== "lock" && action.action !== "unlock") {
            chrome.runtime.sendMessage({
                type: "action_result",
                content: resultMsg
            });
            // Force an immediate DOM update after an action
            sendUpdate();
        }
    }
});

function sendUpdate() {
    // Only send updates if NOT on the dashboard itself.
    // This prevents the URL bar from fluctuating to localhost:3000.
    if (window.location.href.includes("localhost:3000") && !window.location.href.includes("start.html")) {
        return;
    }
    chrome.runtime.sendMessage({
        type: "dom_update",
        content: getDOMSummary()
    });
}

// Watch for changes
const observer = new MutationObserver(() => {
    if (window.aishaUpdateTimer) clearTimeout(window.aishaUpdateTimer);
    window.aishaUpdateTimer = setTimeout(sendUpdate, 1000);
});

observer.observe(document.body, { childList: true, subtree: true, attributes: true });

// Initial DOM push — send as soon as possible on page load
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    sendUpdate();
} else {
    document.addEventListener('DOMContentLoaded', () => sendUpdate());
}

// Additional push after full load (images, iframes, etc.)
window.addEventListener('load', () => {
    setTimeout(sendUpdate, 500);
});

// Periodic fallback (safety net)
setInterval(sendUpdate, 5000);

// Detect URL changes in SPAs (YouTube, GitHub, etc.)
window.addEventListener('popstate', sendUpdate);

// Monkeypatch pushState and replaceState to detect programmatic URL changes
const originalPushState = history.pushState;
history.pushState = function() {
    originalPushState.apply(this, arguments);
    sendUpdate();
};

const originalReplaceState = history.replaceState;
history.replaceState = function() {
    originalReplaceState.apply(this, arguments);
    sendUpdate();
};

// Update when user switches back to the tab
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
        sendUpdate();
    }
});
