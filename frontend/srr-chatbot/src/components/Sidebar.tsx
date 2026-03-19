import React, { useState, useEffect, useCallback } from 'react';
import { Sun, Moon, MessageSquare, Folder, Plus, Trash2, Bot, User, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { useChat } from '../contexts/ChatContext';
import { useTheme } from '../contexts/ThemeContext';
import { getUserSessions, deleteChatSession } from '../services/api';
import type { Session } from '../services/api';
import UserInfoModal from './UserInfoModal';
import './Sidebar.css';

interface SidebarProps {
  currentView: 'chat' | 'files';
  onViewChange: (view: 'chat' | 'files') => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
  isMobile?: boolean;
}

const Sidebar: React.FC<SidebarProps> = ({ 
  currentView, 
  onViewChange, 
  collapsed, 
  onToggleCollapse,
  mobileOpen = false,
  onCloseMobile,
  isMobile = false,
}) => {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { sessionId, switchSession, createSession, messages } = useChat();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [userInfoOpen, setUserInfoOpen] = useState(false);
  const [conversationListExpanded, setConversationListExpanded] = useState(true);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const list = await getUserSessions();
      setSessions(list);
    } catch (err) {
      console.error('Load sessions error:', err);
      setSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!collapsed && user) loadSessions();
  }, [collapsed, user, loadSessions]);

  const handleDeleteSession = async (e: React.MouseEvent, sid: string) => {
    e.stopPropagation();
    try {
      await deleteChatSession(sid);
      if (sid === sessionId) createSession();
      await loadSessions();
    } catch (err) {
      console.error('Delete session error:', err);
    }
  };

  const handleSelectSession = (sid: string) => {
    if (sid !== sessionId) switchSession(sid);
    onViewChange('chat');
  };

  const iconGradient = 'url(#navIconGradient)';
  const showAsOverlay = isMobile && mobileOpen;
  const effectivelyExpanded = !collapsed || showAsOverlay;

  return (
    <div className={`sidebar ${collapsed && !isMobile ? 'collapsed' : ''} ${showAsOverlay ? 'sidebar-mobile-open' : ''} ${isMobile ? 'sidebar-mobile' : ''}`}>
      {/* SVG 漸變定義，供側欄圖標使用 */}
      <svg width="0" height="0" style={{ position: 'absolute', pointerEvents: 'none' }} aria-hidden="true">
        <defs>
          <linearGradient id="navIconGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#b91c1c" />
            <stop offset="100%" stopColor="#eab308" />
          </linearGradient>
        </defs>
      </svg>
      <div className="sidebar-header">
        {isMobile && mobileOpen && onCloseMobile && (
          <button
            type="button"
            onClick={onCloseMobile}
            className="sidebar-close-mobile"
            aria-label="Close menu"
          >
            <X size={24} />
          </button>
        )}
        <button
          type="button"
          onClick={isMobile ? undefined : onToggleCollapse}
          className="sidebar-collapse-btn"
          aria-label={isMobile ? undefined : "Expand/collapse sidebar"}
          title={isMobile ? undefined : "Expand/collapse sidebar"}
        >
          <div className="w-12 h-12 rounded-full gradient-red-yellow flex items-center justify-center flex-shrink-0">
            <Bot size={25} className="text-white" />
          </div>
        </button>
        {effectivelyExpanded && (
          <div className="sidebar-brand flex items-center min-w-0">
            <span className="sidebar-brand-title truncate">SRR Chatbot</span>
          </div>
        )}
      </div>
      
      <nav className="sidebar-nav">
        {/* 對話 + 對話列表 合併在上方 */}
        <div className="sidebar-conversation-block">
          <button
            type="button"
            className={`nav-item ${currentView === 'chat' ? 'active' : ''}`}
            onClick={() => {
              setConversationListExpanded((prev) => !prev);
              onViewChange('chat');
            }}
            title={conversationListExpanded ? 'Collapse conversation list' : 'Expand conversation list'}
          >
            <div className={`nav-icon nav-icon-gradient ${currentView === 'chat' ? 'active' : ''}`}>
              <MessageSquare size={30} stroke={iconGradient} />
            </div>
            {effectivelyExpanded && <span className="nav-label">Chat</span>}
          </button>
          {effectivelyExpanded && user && conversationListExpanded && (
            <div className="sidebar-sessions">
              <div className="sidebar-sessions-header">
                <span className="sidebar-sessions-title">Conversations</span>
                <button
                  type="button"
                  className="sidebar-session-new"
                  onClick={async () => { 
                    await createSession(); 
                    await loadSessions();
                    onViewChange('chat'); 
                  }}
                  title="New conversation"
                >
                  <Plus size={22} />
                  <span>New</span>
                </button>
              </div>
              <div className="sidebar-sessions-list">
                {sessionsLoading ? (
                  <div className="sidebar-sessions-loading">Loading...</div>
                ) : (
                  <>
                    {!sessions.some(s => s.session_id === sessionId) && sessionId && (
                      <div
                        key={sessionId}
                        className="sidebar-session-item active"
                        onClick={() => handleSelectSession(sessionId)}
                        title="New session"
                      >
                        <span className="sidebar-session-label">
                          Current {messages.length}
                        </span>
                        <button
                          type="button"
                          className="sidebar-session-delete"
                          onClick={async (e) => {
                            e.stopPropagation();
                            await createSession();
                            await loadSessions();
                          }}
                          title="Clear session"
                          aria-label="Clear session"
                        >
                          <Trash2 size={22} />
                        </button>
                      </div>
                    )}
                    {sessions.length === 0 && !sessionId ? (
                      <div className="sidebar-sessions-empty">No conversations</div>
                    ) : (
                      sessions.map((s) => (
                        <div
                          key={s.session_id}
                          className={`sidebar-session-item ${s.session_id === sessionId ? 'active' : ''}`}
                          onClick={() => handleSelectSession(s.session_id)}
                          title={`${s.message_count} messages · ${s.last_message_time || ''}`}
                        >
                          <span className="sidebar-session-label">
                            {s.session_id === sessionId ? 'Current ' : ''}{s.message_count}
                          </span>
                          <button
                            type="button"
                            className="sidebar-session-delete"
                            onClick={(e) => handleDeleteSession(e, s.session_id)}
                            title="Delete session"
                            aria-label="Delete session"
                          >
                            <Trash2 size={22} />
                          </button>
                        </div>
                      ))
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>

        <button
          className={`nav-item ${currentView === 'files' ? 'active' : ''}`}
          onClick={() => onViewChange('files')}
          title="Files"
        >
          <div className={`nav-icon nav-icon-gradient ${currentView === 'files' ? 'active' : ''}`}>
            <Folder size={30} stroke={iconGradient} />
          </div>
          {effectivelyExpanded && <span className="nav-label">Files</span>}
        </button>

        <button
          type="button"
          className="nav-item nav-item-theme"
          onClick={toggleTheme}
          title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
        >
          <div className="nav-icon nav-icon-gradient">
            {theme === 'light' ? <Moon size={30} stroke={iconGradient} /> : <Sun size={30} stroke={iconGradient} />}
          </div>
          {effectivelyExpanded && <span className="nav-label">{theme === 'light' ? 'Dark mode' : 'Light mode'}</span>}
        </button>
      </nav>

      {/* 中間彈性空間，使 footer 保持在底部 */}
      <div className="sidebar-spacer" aria-hidden="true" />

      {effectivelyExpanded && user && (
        <div className="sidebar-footer">
          <button
            type="button"
            className="user-profile user-profile-clickable"
            onClick={() => setUserInfoOpen(true)}
            title="View user info"
          >
            <div className="user-avatar">
              <div className="w-12 h-12 rounded-full gradient-red-yellow flex items-center justify-center text-white font-semibold">
                {(user.full_name && user.full_name.charAt(0)) || (user.email && user.email.charAt(0)) || '?'}
              </div>
            </div>
            <div className="user-info">
              <div className="user-name">{user.full_name || 'User'}</div>
              <div className="user-department">{user.department || 'No department'}</div>
            </div>
          </button>
        </div>
      )}

      {/* 摺疊時底部顯示與導航圖標同風格的用戶圖標 */}
      {collapsed && !showAsOverlay && user && (
        <div className="sidebar-footer-collapsed">
          <button
            type="button"
            className="nav-item user-icon-collapsed"
            onClick={() => setUserInfoOpen(true)}
            title="View user info"
            aria-label="View user info"
          >
            <div className="nav-icon nav-icon-gradient">
              <User size={30} stroke={iconGradient} />
            </div>
          </button>
        </div>
      )}
      <UserInfoModal open={userInfoOpen} onClose={() => setUserInfoOpen(false)} />
    </div>
  );
};

export default Sidebar;