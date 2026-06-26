import { useState, useRef, useEffect } from 'react'
import { formatMarkdownLite } from '../utils/markdown.jsx'
import './ChatPanel.css'

// ── Helpers ──

/** Strip the raw JSON code block from the thinking text so it doesn't render twice */
const cleanThinkingText = (raw) => {
  if (!raw) return ''
  // Remove the leading "**Thinking:**" prefix
  let text = raw.replace(/^\*\*Thinking:\*\*\s*/i, '')
  // Remove fenced ```json ... ``` blocks
  text = text.replace(/```json[\s\S]*?```/g, '')
  // Remove any trailing whitespace left behind
  return text.trim()
}

/** Get a human-friendly label for an action type */
const getActionLabel = (action) => {
  if (!action) return null
  switch (action.action) {
    case 'navigate': return 'Navigate'
    case 'click':    return 'Click'
    case 'type':     return 'Type'
    case 'type_and_enter': return 'Type & Enter'
    case 'scroll':   return 'Scroll'
    case 'answer':   return 'Answer'
    case 'get_dom':  return 'Read Page'
    default:         return action.action
  }
}

/** Get an accent colour for an action type */
const getActionColor = (action) => {
  if (!action) return { bg: 'rgba(148,148,184,0.08)', border: 'rgba(148,148,184,0.15)', text: '#9494b8' }
  switch (action.action) {
    case 'navigate': return { bg: 'rgba(56,189,248,0.08)', border: 'rgba(56,189,248,0.18)', text: '#38bdf8' }
    case 'click':    return { bg: 'rgba(74,222,128,0.08)', border: 'rgba(74,222,128,0.18)', text: '#4ade80' }
    case 'type':
    case 'type_and_enter': return { bg: 'rgba(251,191,36,0.08)', border: 'rgba(251,191,36,0.18)', text: '#fbbf24' }
    case 'scroll':   return { bg: 'rgba(168,85,247,0.08)',  border: 'rgba(168,85,247,0.18)',  text: '#a855f7' }
    case 'answer':   return { bg: 'rgba(52,211,153,0.08)',  border: 'rgba(52,211,153,0.18)',  text: '#34d399' }
    default:         return { bg: 'rgba(148,148,184,0.08)', border: 'rgba(148,148,184,0.15)', text: '#9494b8' }
  }
}

const highlightedJSON = (formatted) => {
  return formatted.replace(/(\"(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*\"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
    let cls = 'number';
    if (/^"/.test(match)) {
        if (/:$/.test(match)) {
            cls = 'key';
            return `<span class="json-key">${match.slice(0, -1)}</span>:`;
        } else {
            cls = 'string';
        }
    } else if (/true|false/.test(match)) {
        cls = 'boolean';
    } else if (/null/.test(match)) {
        cls = 'null';
    }
    return `<span class="json-${cls}">${match}</span>`;
  });
}

const formatJSON = (jsonStr) => {
  try {
    const obj = typeof jsonStr === 'string' ? JSON.parse(jsonStr) : jsonStr
    const formatted = JSON.stringify(obj, null, 2)
    return highlightedJSON(formatted)
  } catch (e) {
    return jsonStr
  }
}

// ── Components ──

const StatusStep = ({ step, iconType, text, status = 'success' }) => {
  const [expanded, setExpanded] = useState(false)

  const getIcon = () => {
    switch (iconType) {
      case 'search': return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
      case 'found': return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M20 6 9 17l-5-5"/></svg>
      case 'code': return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/></svg>
      case 'eye': return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
      case 'scroll': return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12l7 7 7-7"/></svg>
      default: return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
    }
  }

  const hasDetails = step && (step.thinking || step.action)
  const colors = getActionColor(step?.action)
  const cleanedThinking = cleanThinkingText(step?.thinking)
  const actionLabel = getActionLabel(step?.action)

  return (
    <div className={`step-container ${expanded ? 'expanded' : ''} ${status}`}>
      <div 
        className={`step-item ${status}`} 
        onClick={() => hasDetails && setExpanded(!expanded)}
        style={{ cursor: hasDetails ? 'pointer' : 'default' }}
      >
        <div className="step-icon" style={status === 'success' ? { color: colors.text, background: colors.bg, borderColor: colors.border } : undefined}>
          {getIcon()}
        </div>
        <span className="step-text">{text}</span>
        {actionLabel && status !== 'processing' && (
          <span className="step-action-badge" style={{ background: colors.bg, color: colors.text, border: `1px solid ${colors.border}` }}>
            {actionLabel}
          </span>
        )}
        {hasDetails && (
          <div className={`step-chevron ${expanded ? 'open' : ''}`}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m6 9 6 6 6-6"/></svg>
          </div>
        )}
      </div>
      {expanded && hasDetails && (
        <div className="step-details" style={{ borderLeftColor: colors.text }}>
          {cleanedThinking && (
            <div className="step-detail-section">
              <div className="step-detail-label">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/><path d="M12 16v-4M12 8h.01"/></svg>
                Thinking
              </div>
              <div className="step-detail-body thinking-body">
                {formatMarkdownLite(cleanedThinking)}
              </div>
            </div>
          )}
          {step.action && (
            <div className="step-detail-section">
              <div className="step-detail-label" style={{ color: colors.text }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/></svg>
                Action
              </div>
              <pre className="step-action-pre">
                <code dangerouslySetInnerHTML={{ __html: formatJSON(step.action) }} />
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const ArtifactBlock = ({ title, content, formatJSON, onCopy }) => (
  <div className="artifact-container">
    <div className="artifact-header">
      <div className="artifact-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>
        {title}
      </div>
      <button className="artifact-copy" onClick={() => onCopy(content)}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
      </button>
    </div>
    <pre className="artifact-body">
      <code dangerouslySetInnerHTML={{ __html: formatJSON(content) }} />
    </pre>
  </div>
)

export default function ChatPanel({ 
  messages, onSend, isProcessing, agentStatus, agentThinking, 
  agentSteps, currentAction, isTaskCompleted
}) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const handleInputChange = (e) => {
    setInput(e.target.value)
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 120) + 'px'
    }
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, agentStatus, agentThinking, agentSteps, currentAction])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || isProcessing) return
    onSend(input.trim())
    setInput('')
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text)
  }

  const getActionIcon = (action) => {
    if (!action) return 'info'
    const type = action.action
    if (type === 'scroll') return 'scroll'
    if (type.includes('search') || type.includes('navigate')) return 'search'
    if (type.includes('click') || type.includes('found')) return 'found'
    if (type.includes('type') || type.includes('json') || type.includes('format')) return 'code'
    return 'info'
  }

  const getActionText = (action) => {
    if (!action) return ''
    const type = action.action
    switch (type) {
      case 'navigate': return `Navigating to ${action.url?.replace(/^https?:\/\//, '').split('/')[0]}...`
      case 'click': return `Clicking element ${action.element_id || ''}...`
      case 'type': return `Typing "${(action.text || '').slice(0, 30)}"...`
      case 'type_and_enter': return `Typing & submitting...`
      case 'scroll': return `Scrolling ${action.direction || 'down'}...`
      case 'answer': return `Composing answer...`
      default: return `Processing step...`
    }
  }

  return (
    <div className="chat-panel">
      <div className="messages-area">
        {messages.map((msg, i) => (
          <div key={i} className={`message-wrapper ${msg.role}`}>
            {msg.role === 'user' ? (
              <div className="user-bubble">{msg.content}</div>
            ) : (
              <div className="assistant-content">
                {/* Status Steps */}
                <div className="nexus-steps">
                  {msg.metadata?.steps?.map((step, idx) => (
                    <StatusStep 
                      key={idx}
                      step={step}
                      iconType={getActionIcon(step.action)}
                      text={getActionText(step.action) || (step.thinking ? 'Analyzed state' : 'Step completed')}
                    />
                  ))}
                </div>

                {/* Artifact Block (Detect JSON in content) */}
                {msg.content.includes('```json') ? (
                  <>
                    <ArtifactBlock 
                      title={msg.content.split('```json')[0].trim().split('\n').pop() || 'data_output.json'}
                      content={msg.content.split('```json')[1].split('```')[0]}
                      formatJSON={formatJSON}
                      onCopy={handleCopy}
                    />
                    <div className="assistant-text">
                      {formatMarkdownLite(msg.content.split('```')[2] || msg.content.split('```json')[0])}
                    </div>
                  </>
                ) : (
                  <div className="assistant-text">
                    {formatMarkdownLite(msg.content)}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Live Processing State */}
        {isProcessing && (
          <div className="message-wrapper assistant">
            <div className="nexus-steps">
              {agentSteps.map((step, i) => (
                <StatusStep 
                  key={i}
                  step={step}
                  iconType={getActionIcon(step.action)}
                  text={getActionText(step.action) || (step.thinking ? 'Analyzed state' : 'Step completed')}
                />
              ))}
              <StatusStep 
                step={{ action: currentAction, thinking: agentThinking }}
                iconType={getActionIcon(currentAction)}
                text={agentStatus || 'Working...'}
                status="processing"
              />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-wrapper" onSubmit={handleSubmit}>
        <div className="input-pill">
          <textarea
            ref={inputRef}
            className="chat-input"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Message AISha..."
            disabled={isProcessing}
            rows={1}
          />
          <button className="send-btn-circle" type="submit" disabled={!input.trim() || isProcessing}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>
          </button>
        </div>
      </form>
    </div>
  )
}
