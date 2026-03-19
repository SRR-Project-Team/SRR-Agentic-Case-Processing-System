import React, { createContext, useContext, useState, useEffect, useRef, ReactNode, useCallback } from 'react';
import { useAuth } from './AuthContext';
import * as api from '../services/api';
import { v4 as uuidv4 } from 'uuid';
import { ExtractedData, FileInfo as TypesFileInfo } from '../types';

/**
 * Message interface
 */
export interface Message {
  id?: string;
  type: 'user' | 'bot';
  content: string;
  timestamp: Date;
  fileInfo?: {
    name?: string;
    filename?: string;
    status?: string;
    size?: number;
    type?: string;
    thinkingSteps?: any[];
    ragEvaluation?: any;
    /** When set, this bot message is "file already processed" and links to this case detail */
    duplicateCaseId?: number;
  };
}

/**
 * Extended File Info interface for chat context
 * Extends the basic FileInfo with processing status
 */
export interface ChatFileInfo {
  filename: string;
  status: string;
  case_id?: number;
  name?: string;
  size?: number;
  type?: string;
}

/**
 * Chat Context Type
 */
/** Persist a message to a specific session (e.g. when a background task completes for that session). Does not update UI. */
export type SaveMessageToSessionPayload = {
  message_type: 'user' | 'bot';
  content: string;
  file_info?: any;
  case_id?: number;
};

export type ChatModelSelection = { provider: string; model: string };

interface ChatContextType {
  messages: Message[];
  extractedData: ExtractedData | null;
  currentFile: TypesFileInfo | null;
  rawFileContent: string | null;
  sessionId: string;
  chatModel: ChatModelSelection;
  setChatModel: (provider: string, model: string) => void;
  embeddingModel: ChatModelSelection;
  setEmbeddingModel: (provider: string, model: string) => void;
  addMessage: (message: Message) => void;
  /** Update content (and optionally fileInfo) of an existing message; set saveToBackend to persist. */
  updateMessageContent: (messageId: string, content: string, options?: { fileInfo?: any; saveToBackend?: boolean }) => void;
  removeMessage: (messageId: string) => void;
  setExtractedData: (data: ExtractedData | null) => void;
  setCurrentFile: (file: TypesFileInfo | null) => void;
  setRawFileContent: (content: string | null) => void;
  /** Persist message to a session (for background task completion). Does not update current UI. */
  saveMessageToSession: (sessionId: string, payload: SaveMessageToSessionPayload) => Promise<void>;
  /** Store extractedData/currentFile/raw_content for a session (restored when switching to that session). */
  setSessionData: (sessionId: string, data: { extractedData?: ExtractedData | null; currentFile?: TypesFileInfo | null; raw_content?: string | null }) => void;
  clearChat: () => void;
  loadChatHistory: () => Promise<void>;
  switchSession: (sessionId: string) => Promise<void>;
  createSession: () => Promise<void>;
  isLoading: boolean;
  /** Register the session that has in-flight file processing (so switchSession can refetch after load). */
  setProcessingSessionId: (id: string | null) => void;
}

/**
 * Create Chat Context
 */
const ChatContext = createContext<ChatContextType | undefined>(undefined);

/**
 * Chat Provider Props
 */
interface ChatProviderProps {
  children: ReactNode;
}

/**
 * Chat Provider Component
 * 
 * Manages chat state and provides:
 * - Message history management
 * - Automatic persistence to localStorage
 * - Automatic sync with backend
 * - Session management
 * - State restoration on page reload
 */
type SessionDataEntry = { extractedData: ExtractedData | null; currentFile: TypesFileInfo | null; raw_content: string | null };

const DEFAULT_CHAT_MODEL: ChatModelSelection = { provider: 'openai', model: 'gpt-4o-mini' };
const DEFAULT_EMBEDDING_MODEL: ChatModelSelection = { provider: 'openai', model: 'text-embedding-3-small' };
const CHAT_MODEL_STORAGE_KEY = 'global_chat_model';
const EMBEDDING_MODEL_STORAGE_KEY = 'global_embedding_model';

export const ChatProvider: React.FC<ChatProviderProps> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [extractedData, setExtractedData] = useState<ExtractedData | null>(null);
  const [currentFile, setCurrentFile] = useState<TypesFileInfo | null>(null);
  const [rawFileContent, setRawFileContent] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [chatModel, setChatModelState] = useState<ChatModelSelection>(DEFAULT_CHAT_MODEL);
  const [embeddingModel, setEmbeddingModelState] = useState<ChatModelSelection>(DEFAULT_EMBEDDING_MODEL);

  const sessionDataCacheRef = useRef<Record<string, SessionDataEntry>>({});
  const processingSessionIdRef = useRef<string | null>(null);
  const sessionIdRef = useRef(sessionId);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const setProcessingSessionId = useCallback((id: string | null) => {
    processingSessionIdRef.current = id;
  }, []);

  const setChatModel = useCallback((provider: string, model: string) => {
    setChatModelState({ provider, model });
    try {
      localStorage.setItem(CHAT_MODEL_STORAGE_KEY, JSON.stringify({ provider, model }));
    } catch {
      // ignore
    }
  }, []);

  const setEmbeddingModel = useCallback((provider: string, model: string) => {
    setEmbeddingModelState({ provider, model });
    try {
      localStorage.setItem(EMBEDDING_MODEL_STORAGE_KEY, JSON.stringify({ provider, model }));
    } catch {
      // ignore
    }
  }, []);

  // Restore global model settings once on mount (not per-session)
  useEffect(() => {
    try {
      const raw = localStorage.getItem(CHAT_MODEL_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { provider?: string; model?: string };
        if (parsed?.provider && parsed?.model) {
          setChatModelState({ provider: parsed.provider, model: parsed.model });
          return;
        }
      }
    } catch {
      // ignore
    }
    setChatModelState(DEFAULT_CHAT_MODEL);
  }, []);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(EMBEDDING_MODEL_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { provider?: string; model?: string };
        if (parsed?.provider && parsed?.model) {
          setEmbeddingModelState({ provider: parsed.provider, model: parsed.model });
          return;
        }
      }
    } catch {
      // ignore
    }
    setEmbeddingModelState(DEFAULT_EMBEDDING_MODEL);
  }, []);

  // Keep per-session cache in sync when current session's data changes (raw_content is set via setSessionData only)
  useEffect(() => {
    if (!sessionId) return;
    const c = sessionDataCacheRef.current;
    const prev = c[sessionId];
    c[sessionId] = {
      extractedData: extractedData ?? null,
      currentFile: currentFile ?? null,
      raw_content: prev?.raw_content ?? null
    };
  }, [sessionId, extractedData, currentFile]);

  // Initialize or restore session ID
  useEffect(() => {
    const storedSessionId = localStorage.getItem('chat_session_id');
    if (storedSessionId) {
      setSessionId(storedSessionId);
    } else {
      const newSessionId = uuidv4();
      setSessionId(newSessionId);
      localStorage.setItem('chat_session_id', newSessionId);
    }
  }, []);

  // Load chat state from localStorage on mount
  useEffect(() => {
    if (!isAuthenticated) return;

    try {
      const storedMessages = localStorage.getItem('chat_messages');
      const storedExtractedData = localStorage.getItem('chat_extracted_data');
      const storedCurrentFile = localStorage.getItem('chat_current_file');

      if (storedMessages) {
        const parsed = JSON.parse(storedMessages);
        // Convert timestamp strings back to Date objects
        const messagesWithDates = parsed.map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp)
        }));
        setMessages(messagesWithDates);
      }

      if (storedExtractedData) {
        setExtractedData(JSON.parse(storedExtractedData));
      }

      if (storedCurrentFile) {
        setCurrentFile(JSON.parse(storedCurrentFile));
      }

      console.log('✅ 从localStorage恢复聊天状态');
    } catch (error) {
      console.error('❌ 恢复聊天状态失败:', error);
    }
  }, [isAuthenticated]);

  // Save to localStorage whenever state changes
  useEffect(() => {
    if (!isAuthenticated) return;

    try {
      localStorage.setItem('chat_messages', JSON.stringify(messages));
      localStorage.setItem('chat_extracted_data', JSON.stringify(extractedData));
      localStorage.setItem('chat_current_file', JSON.stringify(currentFile));
    } catch (error) {
      console.error('❌ 保存聊天状态到localStorage失败:', error);
    }
  }, [messages, extractedData, currentFile, isAuthenticated]);

  /**
   * Load chat history from backend
   */
  const loadChatHistory = useCallback(async () => {
    if (!isAuthenticated || !sessionId) return;
    setIsLoading(true);
    try {
      const backendMessages = await api.getChatHistory(sessionId);
      
      // Convert backend format to frontend format
      const formattedMessages: Message[] = backendMessages.map((msg) => ({
        id: msg.id.toString(),
        type: msg.message_type as 'user' | 'bot',
        content: msg.content,
        timestamp: new Date(msg.created_at),
        fileInfo: msg.file_info || undefined
      }));

      setMessages(formattedMessages);
      console.log(`✅ 从后端加载 ${formattedMessages.length} 条消息`);
    } catch (error) {
      console.error('❌ 加载聊天历史失败:', error);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated, sessionId]);

  /**
   * Add a new message
   */
  const addMessage = useCallback((message: Message) => {
    const newMessage = {
      ...message,
      id: message.id || uuidv4(),
      timestamp: message.timestamp || new Date()
    };

    setMessages(prev => [...prev, newMessage]);

    // Skip saving placeholder (e.g. streaming bot message with empty content)
    if (newMessage.type === 'bot' && newMessage.content === '') return;
    // Save to backend asynchronously
    if (isAuthenticated && sessionId) {
      api.saveChatMessage({
        session_id: sessionId,
        message_type: newMessage.type,
        content: newMessage.content,
        case_id: currentFile?.case_id,
        file_info: newMessage.fileInfo
      }).catch(err => {
        console.error('❌ 保存消息到后端失败:', err);
      });
    }
  }, [isAuthenticated, sessionId, currentFile]);

  const updateMessageContent = useCallback((messageId: string, content: string, options?: { fileInfo?: any; saveToBackend?: boolean }) => {
    setMessages(prev => prev.map(m => m.id === messageId ? { ...m, content, ...(options?.fileInfo !== undefined && { fileInfo: options.fileInfo }) } : m));
    if (options?.saveToBackend && isAuthenticated && sessionId) {
      api.saveChatMessage({
        session_id: sessionId,
        message_type: 'bot',
        content,
        case_id: currentFile?.case_id,
        file_info: options?.fileInfo
      }).catch(err => {
        console.error('❌ 保存消息到后端失败:', err);
      });
    }
  }, [isAuthenticated, sessionId, currentFile]);

  const removeMessage = useCallback((messageId: string) => {
    setMessages(prev => prev.filter(m => m.id !== messageId));
  }, []);

  const saveMessageToSession = useCallback(async (targetSessionId: string, payload: SaveMessageToSessionPayload) => {
    if (!isAuthenticated || !targetSessionId) return;
    try {
      await api.saveChatMessage({
        session_id: targetSessionId,
        message_type: payload.message_type,
        content: payload.content,
        case_id: payload.case_id,
        file_info: payload.file_info
      });
    } catch (err) {
      console.error('❌ 保存消息到会话失败:', err);
    }
  }, [isAuthenticated]);

  const setSessionData = useCallback((targetSessionId: string, data: { extractedData?: ExtractedData | null; currentFile?: TypesFileInfo | null; raw_content?: string | null }) => {
    if (!targetSessionId) return;
    const c = sessionDataCacheRef.current;
    const prev = c[targetSessionId] ?? { extractedData: null, currentFile: null, raw_content: null };
    c[targetSessionId] = {
      extractedData: data.extractedData !== undefined ? data.extractedData : prev.extractedData,
      currentFile: data.currentFile !== undefined ? data.currentFile : prev.currentFile,
      raw_content: data.raw_content !== undefined ? data.raw_content : prev.raw_content
    };
  }, []);

  /**
   * Clear chat state and create a new session
   */
  const clearChat = useCallback(() => {
    setMessages([]);
    setExtractedData(null);
    setCurrentFile(null);
    setRawFileContent(null);

    // Clear localStorage
    localStorage.removeItem('chat_messages');
    localStorage.removeItem('chat_extracted_data');
    localStorage.removeItem('chat_current_file');

    // Generate new session ID
    const newSessionId = uuidv4();
    setSessionId(newSessionId);
    localStorage.setItem('chat_session_id', newSessionId);

    console.log('✅ 聊天记录已清空');
  }, []);

  /**
   * Create new session
   */
  const createSession = useCallback(async () => {
    // Clear local state first
    setMessages([]);
    setExtractedData(null);
    setCurrentFile(null);
    setRawFileContent(null);
    
    // Clear localStorage
    localStorage.removeItem('chat_messages');
    localStorage.removeItem('chat_extracted_data');
    localStorage.removeItem('chat_current_file');

    if (isAuthenticated) {
      try {
        const session = await api.createSession();
        const newSessionId = session.session_id;
        setSessionId(newSessionId);
        localStorage.setItem('chat_session_id', newSessionId);
        console.log('✅ 已创建新会话:', newSessionId);
      } catch (error) {
        console.error('❌ 创建会话失败，回退到本地会话:', error);
        // Fallback to local ID if API fails
        const newSessionId = uuidv4();
        setSessionId(newSessionId);
        localStorage.setItem('chat_session_id', newSessionId);
      }
    } else {
      // Guest mode
      const newSessionId = uuidv4();
      setSessionId(newSessionId);
      localStorage.setItem('chat_session_id', newSessionId);
    }
  }, [isAuthenticated]);

  /**
   * Switch to another session: clear local state, set sessionId, load its history
   */
  const switchSession = useCallback(async (newSessionId: string) => {
    setMessages([]);
    setExtractedData(null);
    setCurrentFile(null);
    setRawFileContent(null);
    localStorage.removeItem('chat_messages');
    localStorage.removeItem('chat_extracted_data');
    localStorage.removeItem('chat_current_file');
    setSessionId(newSessionId);
    localStorage.setItem('chat_session_id', newSessionId);

    const cached = sessionDataCacheRef.current[newSessionId];
    if (cached) {
      setExtractedData(cached.extractedData ?? null);
      setCurrentFile(cached.currentFile ?? null);
      setRawFileContent(cached.raw_content ?? null);
    }

    if (!isAuthenticated) return;
    setIsLoading(true);
    let clearLoadingInFinally = true;
    try {
      const backendMessages = await api.getChatHistory(newSessionId);
      const formattedMessages: Message[] = backendMessages.map((msg) => ({
        id: msg.id.toString(),
        type: msg.message_type as 'user' | 'bot',
        content: msg.content,
        timestamp: new Date(msg.created_at),
        fileInfo: msg.file_info || undefined
      }));
      setMessages(formattedMessages);
      console.log(`✅ 已切换到会话，加载 ${formattedMessages.length} 条消息`);
    } catch (error) {
      console.error('❌ 加载会话历史失败:', error);
    } finally {
      if (clearLoadingInFinally) setIsLoading(false);
    }
  }, [isAuthenticated]);

  const value: ChatContextType = {
    messages,
    extractedData,
    currentFile,
    rawFileContent,
    sessionId,
    chatModel,
    setChatModel,
    embeddingModel,
    setEmbeddingModel,
    addMessage,
    updateMessageContent,
    removeMessage,
    setExtractedData,
    setCurrentFile,
    setRawFileContent,
    saveMessageToSession,
    setSessionData,
    clearChat,
    loadChatHistory,
    switchSession,
    createSession,
    isLoading,
    setProcessingSessionId
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
};

/**
 * Hook to use Chat Context
 * 
 * @throws Error if used outside ChatProvider
 */
export const useChat = (): ChatContextType => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
