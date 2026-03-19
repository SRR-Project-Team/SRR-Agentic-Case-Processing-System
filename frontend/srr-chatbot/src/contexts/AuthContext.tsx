import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import * as api from '../services/api';

/**
 * User interface
 */
export interface User {
  phone_number: string;
  full_name: string;
  department: string;
  role: string;
  email: string;
}

/**
 * Authentication Context Type
 */
interface AuthContextType {
  user: User | null;
  token: string | null;
  login: (phone: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
  isLoading: boolean;
}

/**
 * Create Authentication Context
 */
const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Authentication Provider Props
 */
interface AuthProviderProps {
  children: ReactNode;
}

/**
 * Authentication Provider Component
 * 
 * Manages user authentication state and provides:
 * - Login/logout functionality
 * - Stage 1: Token storage in localStorage with centralized unauthorized handling
 * - Stage 2 (planned): move to HttpOnly secure cookie-based auth
 * - Automatic state restoration from localStorage (until Stage 2 migration)
 * - User information management
 */
export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load token and user info from localStorage on mount
  useEffect(() => {
    let mounted = true;
    
    const loadAuthState = async () => {
      try {
        const storedToken = localStorage.getItem('token');
        const storedUser = localStorage.getItem('user');

        if (storedToken && storedUser) {
          if (!mounted) return;
          setToken(storedToken);
          setUser(JSON.parse(storedUser));
          console.log('✅ 从localStorage恢复认证状态');
        }
      } catch (error) {
        console.error('加载认证状态失败:', error);
        localStorage.removeItem('token');
        localStorage.removeItem('user');
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    };

    loadAuthState();
    
    // Listen for auth:unauthorized event from API interceptor
    const handleUnauthorized = () => {
      if (mounted) {
        setToken(null);
        setUser(null);
      }
    };
    
    window.addEventListener('auth:unauthorized', handleUnauthorized);
    
    return () => {
      mounted = false;
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, []);

  /**
   * Login function
   */
  const login = async (phone: string, password: string) => {
    try {
      const response = await api.login(phone, password);
      setToken(response.access_token);
      setUser(response.user);
      localStorage.setItem('token', response.access_token);
      localStorage.setItem('user', JSON.stringify(response.user));
      console.log('✅ 登录成功:', response.user.full_name);
    } catch (error) {
      console.error('❌ 登录失败:', error);
      throw error;
    }
  };

  /**
   * Logout function
   */
  const logout = () => {
    // Clear state
    setToken(null);
    setUser(null);
    
    // Clear localStorage
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    
    // Optional: call backend logout endpoint
    api.logout().catch(err => console.error('Logout API call failed:', err));
    
    console.log('✅ 已登出');
  };

  const value: AuthContextType = {
    user,
    token,
    login,
    logout,
    isAuthenticated: !!token && !!user,
    isLoading
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * Hook to use Authentication Context
 * 
 * @throws Error if used outside AuthProvider
 */
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
