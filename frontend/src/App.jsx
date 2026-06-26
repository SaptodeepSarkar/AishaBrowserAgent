import { useState, useEffect, useRef, useCallback } from 'react'
import ChatPanel from './components/ChatPanel.jsx'
import BrowserView from './components/BrowserView.jsx'
import './App.css'

const WS_URL = `ws://${window.location.hostname}:8763/ws/agent`

export default function App() {
  const [messages, setMessages] = useState([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [agentStatus, setAgentStatus] = useState('')
  const [agentThinking, setAgentThinking] = useState('')
  const [agentSteps, setAgentSteps] = useState([])
  const [currentAction, setCurrentAction] = useState(null)
  const [connected, setConnected] = useState(false)
  const [chatId, setChatId] = useState(null)
  const [chatList, setChatList] = useState([])
  const [currentUrl, setCurrentUrl] = useState('about:blank')
  const [isTaskCompleted, setIsTaskCompleted] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Modal State
  const [chatToDelete, setChatToDelete] = useState(null)

  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)

  // Derive the server's status label
  const getServerStatusLabel = () => {
    if (!connected) return 'Disconnected'
    if (isProcessing) return 'Processing'
    return 'Connected'
  }

  const getServerStatusClass = () => {
    if (!connected) return 'offline'
    if (isProcessing) return 'working'
    return 'idle'
  }

  // Derive the AI's status text
  const getAiStatusText = () => {
    if (!connected) return 'AISha is offline'
    if (agentStatus) return agentStatus
    if (agentThinking) return 'Analyzing page state...'
    if (isProcessing) return 'Working on task...'
    return 'Waiting for new task...'
  }

  const fetchChats = async () => {
    try {
      const res = await fetch('http://localhost:8763/api/chats')
      const data = await res.json()
      setChatList(data)
    } catch (e) {
      console.error('Failed to fetch chats:', e)
    }
  }

  const loadChat = async (id) => {
    try {
      const res = await fetch(`http://localhost:8763/api/chats/${id}`)
      const data = await res.json()
      setChatId(id)
      setMessages(data.messages || [])
      setIsTaskCompleted(false)
      setIsProcessing(false)
    } catch (e) {
      console.error('Failed to load chat:', e)
    }
  }

  const handleDeleteClick = (e, id) => {
    e.stopPropagation()
    setChatToDelete(id)
  }

  const confirmDelete = async () => {
    if (!chatToDelete) return
    try {
      await fetch(`http://localhost:8763/api/chats/${chatToDelete}`, { method: 'DELETE' })
      if (chatId === chatToDelete) {
        createNewChat()
      }
      fetchChats()
      setChatToDelete(null)
    } catch (e) {
      console.error('Failed to delete chat:', e)
    }
  }

  const createNewChat = () => {
    setChatId(null)
    setMessages([])
    setAgentSteps([])
    setAgentThinking('')
    setCurrentAction(null)
    setIsTaskCompleted(false)
    setIsProcessing(false)
  }

  const connectWS = useCallback(() => {
    console.log('[WS] Connecting to:', WS_URL)
    const ws = new WebSocket(WS_URL)

    ws.onopen = () => {
      console.log('[WS] Connected')
      setConnected(true)
      fetchChats()
    }

    ws.onclose = () => {
      console.log('[WS] Disconnected, retrying...')
      setConnected(false)
      reconnectTimer.current = setTimeout(connectWS, 3000)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        switch (data.type) {
          case 'status':
            setAgentStatus(data.content)
            break
          case 'thinking':
            setAgentThinking(prev => prev + data.content)
            break
          case 'action':
            setCurrentAction(data.content)
            setAgentThinking('')
            break
          case 'step_complete':
            setAgentSteps(prev => [...prev, data.content])
            setCurrentAction(null)
            break
          case 'answer':
            setMessages(prev => [...prev, { role: 'assistant', content: data.text, metadata: data.metadata }])
            setIsProcessing(false)
            setAgentStatus('')
            setAgentThinking('')
            setAgentSteps([])
            setCurrentAction(null)
            fetchChats()
            break
          case 'dom_update':
            setCurrentUrl(data.url)
            break
          case 'chat_created':
            setChatId(data.chat.id)
            fetchChats()
            break
          case 'task_complete':
            setIsTaskCompleted(true)
            setIsProcessing(false)
            setCurrentAction(null)
            break
          default:
            break
        }
      } catch (e) {
        console.error('[WS] Parse error:', e)
      }
    }

    wsRef.current = ws
  }, [])

  useEffect(() => {
    connectWS()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connectWS])

  const sendTask = (content) => {
    if (!content.trim() || isProcessing || !wsRef.current) return
    setMessages(prev => [...prev, { role: 'user', content }])
    setIsProcessing(true)
    setIsTaskCompleted(false)
    setAgentThinking('')
    setAgentSteps([])
    setCurrentAction(null)
    wsRef.current.send(JSON.stringify({
      type: 'user_message',
      content,
      chat_id: chatId
    }))
  }

  return (
    <div className="app-container aura-theme">
      <button className={`sidebar-toggle-btn ${sidebarOpen ? 'open' : 'closed'}`} onClick={() => setSidebarOpen(prev => !prev)} title={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}>
        {sidebarOpen ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M15 18l-6-6 6-6" /></svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M9 18l6-6-6-6" /></svg>
        )}
      </button>
      {/* ── Sidebar (Left) ── */}
      <aside className={`aura-sidebar ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="brand-icon">
              <img src="/aisha_avatar.png" alt="AISha" />
            </div>
            <span className="brand-name">AISha</span>
          </div>
          <button className="new-task-btn" onClick={createNewChat} disabled={isProcessing}>
            + New Task
          </button>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-label">History</div>
          <div className="chat-history-list">
            {chatList.map(chat => (
              <div
                key={chat.id}
                className={`nav-item ${chatId === chat.id ? 'active' : ''}`}
                onClick={() => loadChat(chat.id)}
              >
                <span className="nav-icon">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
                </span>
                <span className="nav-text">{chat.title}</span>
                <button className="delete-chat-btn" onClick={(e) => handleDeleteClick(e, chat.id)}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18m-2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
                </button>
              </div>
            ))}
          </div>
        </nav>
      </aside>

      {/* ── Main Workspace ── */}
      <main className="aura-main">
        <div className="workspace-container">
          {/* Chat column with its own header */}
          <div className="chat-column">
            <header className="chat-column-header">
              <div className="header-brand">
                <div className="brand-logo">
                  <img src="/aisha_avatar.png" alt="AISha" />
                </div>
                <div className="brand-meta">
                  <h1 className="brand-title">AISha</h1>
                  <div className="brand-status">
                    <span className="status-text">{getAiStatusText()}</span>
                  </div>
                </div>
              </div>
              <div className="header-actions">
                <div className={`status-badge ${getServerStatusClass()}`}>
                  {getServerStatusLabel()}
                </div>
              </div>
            </header>
            <ChatPanel
              messages={messages}
              onSend={sendTask}
              isProcessing={isProcessing}
              agentStatus={agentStatus}
              agentThinking={agentThinking}
              agentSteps={agentSteps}
              currentAction={currentAction}
              isTaskCompleted={isTaskCompleted}
            />
          </div>

          {/* Browser column — extends full height, no header above it */}
          <div className="browser-column">
            <BrowserView
              agentStatus={agentStatus}
              agentThinking={agentThinking}
              currentAction={currentAction}
              isProcessing={isProcessing}
              currentUrl={currentUrl}
            />
          </div>
        </div>
      </main>

      {/* ── Custom Delete Confirmation Modal ── */}
      {chatToDelete && (
        <div className="modal-overlay">
          <div className="modal-content aura-modal">
            <div className="modal-header">
              <h3>Delete Conversation</h3>
            </div>
            <div className="modal-body">
              <p>Are you sure you want to permanently delete this chat? This action cannot be undone.</p>
            </div>
            <div className="modal-footer">
              <button className="modal-btn secondary" onClick={() => setChatToDelete(null)}>Cancel</button>
              <button className="modal-btn danger" onClick={confirmDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
