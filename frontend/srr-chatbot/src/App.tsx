import React, { useState, useEffect } from 'react';
import './App.css';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ChatProvider } from './contexts/ChatContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { Menu } from 'lucide-react';
import Sidebar from './components/Sidebar';
import ChatbotInterface from './components/ChatbotInterface';
import FileManagement from './components/FileManagement';
import LoginPage from './components/LoginPage';
import RegisterPage from './components/RegisterPage';

type AppView = 'chat' | 'files';
type AuthView = 'login' | 'register';

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const handler = () => setIsMobile(mq.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);
  return isMobile;
}

/**
 * Main App Component (Inner)
 * 
 * Renders the main application interface after authentication
 */
function AppContent() {
  const { isAuthenticated, isLoading } = useAuth();
  const [currentView, setCurrentView] = useState<AppView>('chat');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarMobileOpen, setSidebarMobileOpen] = useState(false);
  const [authView, setAuthView] = useState<AuthView>('login');
  const isMobile = useIsMobile();

  const handleViewChange = (view: 'chat' | 'files') => {
    setCurrentView(view);
    if (isMobile) setSidebarMobileOpen(false);
  };

  // Show loading spinner while checking auth state
  if (isLoading) {
    return (
      <div className="App loading min-h-screen flex items-center justify-center bg-background">
        <div className="loading-spinner text-center animate-fade-in">
          <div className="spinner-icon text-4xl mb-4 animate-bounce-light">🔄</div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <ChatProvider>
      <div className="App h-screen min-h-[100dvh] flex flex-row bg-background overflow-hidden">
        <Sidebar 
          currentView={currentView} 
          onViewChange={handleViewChange}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          mobileOpen={sidebarMobileOpen}
          onCloseMobile={() => setSidebarMobileOpen(false)}
          isMobile={isMobile}
        />
        {isMobile && sidebarMobileOpen && (
          <button
            type="button"
            className="sidebar-backdrop"
            onClick={() => setSidebarMobileOpen(false)}
            aria-label="Close menu"
          />
        )}
        <div className="app-main-content flex-1 flex flex-col min-h-0 p-4 md:p-6 lg:p-8 overflow-hidden relative min-w-0">
            {isMobile && isAuthenticated && (
              <button
                type="button"
                className="mobile-menu-btn"
                onClick={() => setSidebarMobileOpen(true)}
                aria-label="Open menu"
              >
                <Menu size={24} className="text-foreground" />
              </button>
            )}
            {isAuthenticated ? (
              currentView === 'chat' ? (
                <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
                  <ChatbotInterface />
                </div>
              ) : (
                <div className="flex-1 flex flex-col min-h-0 overflow-auto">
                  <FileManagement onSwitchToChat={() => setCurrentView('chat')} />
                </div>
              )
            ) : null}
            {/* Login/Register as overlay modal (no separate page) */}
            {!isAuthenticated && (
              <>
                <div className="auth-overlay" aria-hidden="true" />
                <div className="auth-modal-center">
                  {authView === 'register' ? (
                    <RegisterPage
                      embedded
                      onSwitchToLogin={() => setAuthView('login')}
                    />
                  ) : (
                    <LoginPage
                      embedded
                      onSwitchToRegister={() => setAuthView('register')}
                    />
                  )}
                </div>
              </>
            )}
          </div>
      </div>
    </ChatProvider>
  );
}

/**
 * Root App Component
 * 
 * Wraps the application with necessary providers
 */
function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;