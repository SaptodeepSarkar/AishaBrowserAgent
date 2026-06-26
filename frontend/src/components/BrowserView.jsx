import './BrowserView.css'

export default function BrowserView({ agentStatus, agentThinking, currentAction, isProcessing, currentUrl }) {

  return (
    <div className="browser-view">
      <div className="browser-header">
        <div className="browser-header-top">
          <div className="browser-header-left">
            <div className="browser-dots">
              <span className="dot red"></span>
              <span className="dot yellow"></span>
              <span className="dot green"></span>
            </div>
          </div>
          <div className="browser-header-right">
            {isProcessing && (
              <div className="badge">
                <span className="dot"></span>
                LIVE
              </div>
            )}
          </div>
        </div>

        <div className="browser-address-bar">
          <div className="address-icon">
             <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </div>
          <div className="address-text">
            {currentUrl || 'about:blank'}
          </div>
        </div>
      </div>

      <div className="browser-content">
        <div className="browser-placeholder">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.3">
            <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
            <line x1="8" y1="21" x2="16" y2="21"/>
            <line x1="12" y1="17" x2="12" y2="21"/>
          </svg>
          <span>AISha is standing by...</span>
          <p className="placeholder-hint">Use the AISha extension popup to start a live session</p>
        </div>
      </div>

      <div className="browser-utility-bar">
        <div className="utility-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          Agent Status
        </div>
        <div className="utility-info">
          {isProcessing ? (
            <>
              {agentStatus && <span className="utility-status-text">{agentStatus}</span>}
              {currentAction && currentAction.action !== 'answer' && (
                <div className="utility-action">
                  <span className="utility-action-type">{currentAction.action}</span>
                  {currentAction.url && <span className="utility-action-detail">{currentAction.url}</span>}
                  {currentAction.element_id && <span className="utility-action-detail">{currentAction.element_id}</span>}
                  {currentAction.text && <span className="utility-action-detail">"{currentAction.text}"</span>}
                </div>
              )}
            </>
          ) : (
            <span className="utility-idle-text">Agent is standing by</span>
          )}
        </div>
      </div>

    </div>
  )
}
