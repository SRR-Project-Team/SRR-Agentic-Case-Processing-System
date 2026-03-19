import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Send, Upload, FileText, Cpu, Trash2 } from 'lucide-react';
import { Message, FileSummary, ExtractedData } from '../types';
import { useChat } from '../contexts/ChatContext';
import {
  createCase,
  createCaseFromFolder,
  processMultipleFiles,
  queryCaseStream,
  getCaseStatistics,
  generateReplyDraft,
  generateReplyDraftStream,
  deleteConversationDraft,
  updateConversationDraft,
  approveDraftToKB,
  RAGEvalData,
  ThinkingStepEvent,
  BatchProcessingResponse,
  getLlmModels,
  getEmbeddingConfig,
} from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import logoImage from '../images/system_logo.png'; 
import universityLogo from '../images/university_logo.png';
import FileUploadModal from './FileUploadModal';
import FileInfoModal from './FileInfoModal';
import CaseDetailModal from './CaseDetailModal';
import SuggestedQuestions from './SuggestedQuestions';
import ThinkingChain from './ThinkingChain';
import RAGEvalPanel from './RAGEvalPanel';
import botIcon from '../images/bot_icon.jpeg';  
import userIcon from '../images/user_icon.jpeg';
import './ChatbotInterface.css';  

const INPUT_HISTORY_KEY = 'chat_input_history';
const INPUT_HISTORY_MAX = 10;

const EXTRACTED_KEYS: (keyof ExtractedData)[] = [
  'A_date_received', 'B_source', 'C_case_number', 'D_type', 'E_caller_name',
  'F_contact_no', 'G_slope_no', 'H_location', 'I_nature_of_request', 'J_subject_matter',
  'K_10day_rule_due_date', 'L_icc_interim_due', 'M_icc_final_due', 'N_works_completion_due',
  'O1_fax_to_contractor', 'O2_email_send_time', 'P_fax_pages', 'Q_case_details',
];

function toExtractedData(raw: Record<string, string>): ExtractedData {
  const out = {} as ExtractedData;
  for (const k of EXTRACTED_KEYS) {
    out[k] = (raw[k] ?? '') as string;
  }
  return out;
}

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  type: 'bot',
  content: 'Hello! I am the SRR case processing assistant. Upload PDF, TXT, DOCX, JPG/PNG (location maps, site photos), or ZIP. Supports multi-file batch and folder processing with Vision parsing.',
  timestamp: new Date(),
};

const SimilarCasesItem: React.FC<{ item: any; index: number }> = ({ item, index }) => {
  const c = item.case ?? item;
  const score = ((item.similarity_score ?? 0) * 100).toFixed(1);
  const isDup = item.is_potential_duplicate;
  const source = item.data_source || 'Unknown';
  const hasComplaintDetails = c.I_nature_of_request && c.I_nature_of_request !== 'N/A' && c.I_nature_of_request.trim();
  return (
    <div className="similar-case-item">
      <div className="similar-case-title">
        <strong>{index + 1}. [{source}] Case #{c.C_case_number || 'N/A'}</strong> ({score}% match)
        {isDup && <span className="similar-case-dup"> 🔴 POTENTIAL DUPLICATE</span>}
      </div>
      <div className="similar-case-meta">
        <span>📅 Date: {c.A_date_received || 'N/A'}</span>
        <span>📍 Location: {c.H_location || 'N/A'}</span>
        <span>🏗️ Slope: {c.G_slope_no || 'N/A'}</span>
        <span>📝 Subject: {c.J_subject_matter || 'N/A'}</span>
        {c.E_caller_name && <span>👤 Caller: {c.E_caller_name}</span>}
        {c.F_contact_no && <span>📞 Phone: {c.F_contact_no}</span>}
        {c.tree_id && <span>🌳 Tree ID: {c.tree_id}</span>}
        {c.tree_count != null && <span>🌲 Number of Trees: {c.tree_count}</span>}
      </div>
      {hasComplaintDetails && (
        <details className="similar-case-details">
          <summary>📄 Complaint Details</summary>
          <div className="similar-case-details-content">{c.I_nature_of_request}</div>
        </details>
      )}
      {c.inspector_remarks && (
        <div className="similar-case-remarks">🔍 Inspector Remarks: {c.inspector_remarks}</div>
      )}
    </div>
  );
};

/** Renders similar cases as one collapsible block (collapsed: header + case #1 preview). */
const SimilarCasesBlock: React.FC<{ cases: any[] }> = ({ cases }) => {
  const [expanded, setExpanded] = useState(false);
  const previewCase = cases[0] ?? null;
  return (
    <div className="similar-cases-block">
      <button
        type="button"
        className="similar-cases-toggle"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
      >
        <span className={`similar-cases-chevron ${expanded ? 'open' : ''}`}>▶</span>
        <span>📚 <strong>Found {cases.length} Similar Historical Cases</strong></span>
      </button>
      {expanded ? (
        <div className="similar-cases-list">
          {cases.map((item: any, index: number) => (
            <SimilarCasesItem key={index} item={item} index={index} />
          ))}
        </div>
      ) : (
        previewCase && (
          <div className="similar-cases-preview">
            <SimilarCasesItem item={previewCase} index={0} />
          </div>
        )
      )}
    </div>
  );
};

const PROCESSING_FILE_INFO_TYPES = new Set([
  'parsed-success',
  'summary',
  'summary-error',
  'similar-cases',
  'similar-cases-empty',
  'location-stats',
]);

type ProcessingCardSections = {
  parsed?: any;
  summary?: any;
  summaryError?: any;
  similarCases?: any;
  similarCasesEmpty?: any;
  locationStats?: any;
};

const collectLatestProcessingCard = (
  list: any[],
): { start: number; end: number; sections: ProcessingCardSections } | null => {
  let runStart = -1;
  let runEnd = -1;
  let latestStart = -1;
  let latestEnd = -1;
  for (let i = 0; i < list.length; i += 1) {
    const msg = list[i] as any;
    const t = msg?.fileInfo?.type;
    const inProcessingSet = msg?.type === 'bot' && typeof t === 'string' && PROCESSING_FILE_INFO_TYPES.has(t);
    if (inProcessingSet) {
      if (runStart === -1) runStart = i;
      runEnd = i;
    } else if (runStart !== -1) {
      latestStart = runStart;
      latestEnd = runEnd;
      runStart = -1;
      runEnd = -1;
    }
  }
  if (runStart !== -1 && runEnd !== -1) {
    latestStart = runStart;
    latestEnd = runEnd;
  }
  if (latestStart === -1 || latestEnd === -1) return null;

  const sections: ProcessingCardSections = {};
  for (let i = latestStart; i <= latestEnd; i += 1) {
    const msg = list[i] as any;
    const t = msg?.fileInfo?.type;
    if (!t) continue;
    if (t === 'parsed-success' && !sections.parsed) sections.parsed = msg;
    if (t === 'summary' && !sections.summary) sections.summary = msg;
    if (t === 'summary-error' && !sections.summaryError) sections.summaryError = msg;
    if (t === 'similar-cases' && !sections.similarCases) sections.similarCases = msg;
    if (t === 'similar-cases-empty' && !sections.similarCasesEmpty) sections.similarCasesEmpty = msg;
    if (t === 'location-stats' && !sections.locationStats) sections.locationStats = msg;
  }

  if (!sections.parsed) return null;

  return { start: latestStart, end: latestEnd, sections };
};

const ChatbotInterface: React.FC = () => {
  const { user } = useAuth();
  const {
    messages,
    extractedData,
    currentFile,
    chatModel,
    setChatModel,
    embeddingModel,
    setEmbeddingModel,
    addMessage: contextAddMessage,
    updateMessageContent,
    removeMessage,
    setExtractedData,
    setCurrentFile,
    saveMessageToSession,
    setSessionData,
    setProcessingSessionId,
    rawFileContent,
    setRawFileContent,
    isLoading: sessionLoading,
    sessionId,
  } = useChat();
  const [isProcessing, setIsProcessing] = useState(false);
  const [createCaseSteps, setCreateCaseSteps] = useState<string[]>([]);

  const [inputMessage, setInputMessage] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  // Input history: last 10 entries, ArrowUp/Down to cycle (index -1 = not browsing)
  const [inputHistory, setInputHistory] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(INPUT_HISTORY_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as string[];
        return Array.isArray(parsed) ? parsed.slice(0, INPUT_HISTORY_MAX) : [];
      }
    } catch {
      /* ignore */
    }
    return [];
  });
  const [historyIndex, setHistoryIndex] = useState(-1);
  const inputBeforeHistoryRef = useRef('');
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingDisplayLength, setStreamingDisplayLength] = useState(0);
  const streamingContentRef = useRef<string>('');
  const streamingRevealRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [streamEnded, setStreamEnded] = useState(false);
  const pendingFinalTextRef = useRef<string | null>(null);
  const streamingSessionIdRef = useRef<string | null>(null);
  /** When set, the stream-end effect adds the bot message with this fileInfo (e.g. file summary) */
  const pendingStreamFileInfoRef = useRef<any>(null);
  /** Id of the bot message used for chat-query streaming (single-message update); null when not streaming that way */
  const streamingMessageIdRef = useRef<string | null>(null);
  const [streamThinkingSteps, setStreamThinkingSteps] = useState<ThinkingStepEvent[]>([]);
  const [streamRagEval, setStreamRagEval] = useState<RAGEvalData | null>(null);
  const pendingStreamThinkingRef = useRef<ThinkingStepEvent[]>([]);
  const pendingStreamRagEvalRef = useRef<RAGEvalData | null>(null);
  const prevStreamingRef = useRef<string | null>(null);
  const streamMessageAddedRef = useRef(false);
  /** When true, hide streaming bubble immediately so we don't show bubble + new message in same/next frame */
  const streamBubbleHiddenRef = useRef(false);
  streamingContentRef.current = streamingContent ?? '';
  const [summaryResult, setSummaryResult] = useState<FileSummary | null>(null);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isFileInfoModalOpen, setIsFileInfoModalOpen] = useState(false);
  const [currentCaseId, setCurrentCaseId] = useState<number | null>(null);
  const [replyDraftState, setReplyDraftState] = useState<{ conversationId: number; replyType: string } | null>(null);
  const [suggestedActionsDismissed, setSuggestedActionsDismissed] = useState(false);
  const [caseDetailModalId, setCaseDetailModalId] = useState<number | null>(null);
  const [draftEdits, setDraftEdits] = useState<Record<string, string>>({});
  const [approvedDraftIds, setApprovedDraftIds] = useState<Set<number>>(new Set());
  const [approvingDraftId, setApprovingDraftId] = useState<number | null>(null);
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null);
  const [savingDraftMessageId, setSavingDraftMessageId] = useState<string | null>(null);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const modelDropdownRef = useRef<HTMLDivElement>(null);
  /** Stores the file from duplicate upload for reuse by the Reprocess button */
  const reprocessFileRef = useRef<File | null>(null);

  const OPENAI_MODELS_DEFAULT = ['gpt-4o-mini', 'gpt-4o'];
  const OPENAI_EMBED_DEFAULT = ['text-embedding-3-small', 'text-embedding-3-large', 'text-embedding-ada-002'];
  const OLLAMA_EMBED_DEFAULT = ['bge-m3', 'nomic-embed-text', 'mxbai-embed-large'];
  const OLLAMA_MODELS_DEFAULT = ['llama3.2', 'llama3.1', 'qwen2.5:7b', 'mistral'];
  const [fetchedModels, setFetchedModels] = useState<{ openai: string[]; ollama: string[] } | null>(null);
  const [fetchedEmbeddingModels, setFetchedEmbeddingModels] = useState<{ openai: string[]; ollama: string[] } | null>(null);
  const openaiModels = (fetchedModels?.openai?.length ? fetchedModels.openai : OPENAI_MODELS_DEFAULT);
  const ollamaModels = (fetchedModels?.ollama?.length ? fetchedModels.ollama : OLLAMA_MODELS_DEFAULT);
  const currentModels = chatModel.provider === 'ollama' ? ollamaModels : openaiModels;
  const openaiEmbedModels = (fetchedEmbeddingModels?.openai?.length ? fetchedEmbeddingModels.openai : OPENAI_EMBED_DEFAULT);
  const ollamaEmbedModels = (fetchedEmbeddingModels?.ollama?.length ? fetchedEmbeddingModels.ollama : OLLAMA_EMBED_DEFAULT);
  const currentEmbedModels = embeddingModel.provider === 'ollama' ? ollamaEmbedModels : openaiEmbedModels;
  /** Latest extracted case data during current file processing (for similar cases + stats) */
  const processingCaseDataRef = useRef<any>(null);
  // Track current session for async guards: ignore results if user switched session mid-request
  const sessionIdRef = useRef(sessionId);
  /** Session that started the current processing; only that session may show the Processing UI */
  const processingSessionIdRef = useRef<string | null>(null);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const displayMessages = useMemo(
    () => (sessionLoading ? [] : (messages.length === 0 ? [WELCOME_MESSAGE] : messages)),
    [sessionLoading, messages]
  );
  const showProcessingUI = isProcessing && sessionIdRef.current === processingSessionIdRef.current;
  const isLoading = sessionLoading || showProcessingUI;
  const latestProcessingCard = useMemo(
    () => collectLatestProcessingCard(displayMessages),
    [displayMessages],
  );
  const hasLatestUnifiedProcessingCard =
    latestProcessingCard != null &&
    latestProcessingCard.end === displayMessages.length - 1;
  const shouldShowStreamingSummaryInCard =
    hasLatestUnifiedProcessingCard &&
    streamingContent !== null &&
    streamingMessageIdRef.current === null &&
    !streamBubbleHiddenRef.current;

  // Reset local UI/flow state when switching session so the new session doesn't show the previous one's state
  useEffect(() => {
    setSelectedFiles([]);
    setIsProcessing(false);
    setStreamingContent(null);
    setSummaryResult(null);
    setReplyDraftState(null);
    setSuggestedActionsDismissed(false);
    setCurrentCaseId(null);
    setDraftEdits({});
    setEditingDraftId(null);
    setSavingDraftMessageId(null);
    pendingFinalTextRef.current = null;
    streamingSessionIdRef.current = null;
    streamingMessageIdRef.current = null;
    pendingStreamThinkingRef.current = [];
    pendingStreamRagEvalRef.current = null;
    setStreamThinkingSteps([]);
    setStreamRagEval(null);
    processingSessionIdRef.current = null;
  }, [sessionId]);

  // If current model was removed from list (e.g. gpt-4o-nano), fall back to first available
  useEffect(() => {
    if (currentModels.length && !currentModels.includes(chatModel.model)) {
      setChatModel(chatModel.provider, currentModels[0]);
    }
  }, [currentModels, chatModel.provider, chatModel.model, setChatModel]);

  const effectiveCaseId = currentCaseId ?? (currentFile as { case_id?: number })?.case_id ?? null;

  useEffect(() => {
    if (!extractedData) {
      setCurrentCaseId(null);
      setReplyDraftState(null);
      setSuggestedActionsDismissed(false);
    } else if (currentFile && (currentFile as { case_id?: number }).case_id) {
      setCurrentCaseId((currentFile as { case_id: number }).case_id);
    }
  }, [currentFile, extractedData]);

  const scrollToBottom = (instant = false) => {
    messagesEndRef.current?.scrollIntoView({ behavior: instant ? 'auto' : 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [displayMessages]);

  useEffect(() => {
    if (!modelDropdownOpen) return;
    const onDocClick = (e: MouseEvent) => {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target as Node)) {
        setModelDropdownOpen(false);
      }
    };
    document.addEventListener('click', onDocClick);
    return () => document.removeEventListener('click', onDocClick);
  }, [modelDropdownOpen]);

  useEffect(() => {
    if (modelDropdownOpen) {
      Promise.all([
        getLlmModels().catch(() => null),
        getEmbeddingConfig().catch(() => null),
      ]).then(([llm, embed]) => {
        if (llm) setFetchedModels(llm);
        if (embed) setFetchedEmbeddingModels({ openai: embed.openai, ollama: embed.ollama });
      });
    }
  }, [modelDropdownOpen]);

  // Typewriter reveal: gradually show streaming content char-by-char for "逐字蹦出來" effect
  useEffect(() => {
    if (streamingContent === null) {
      setStreamingDisplayLength(0);
      setStreamEnded(false);
      pendingFinalTextRef.current = null;
      prevStreamingRef.current = null;
      streamMessageAddedRef.current = false;
      streamBubbleHiddenRef.current = false;
      setStreamThinkingSteps([]);
      setStreamRagEval(null);
      pendingStreamThinkingRef.current = [];
      pendingStreamRagEvalRef.current = null;
      if (streamingRevealRef.current) {
        clearInterval(streamingRevealRef.current);
        streamingRevealRef.current = null;
      }
      return;
    }
    if (prevStreamingRef.current === null) setStreamingDisplayLength(0);
    prevStreamingRef.current = streamingContent;
    if (!streamingRevealRef.current) {
      const interval = setInterval(() => {
        const targetLen = streamingContentRef.current.length;
        setStreamingDisplayLength((prev) => Math.min(prev + 2, targetLen));
      }, 25);
      streamingRevealRef.current = interval;
    }
    return () => {
      if (streamingRevealRef.current) {
        clearInterval(streamingRevealRef.current);
        streamingRevealRef.current = null;
      }
    };
  }, [streamingContent]);

  // When stream has ended, wait for typewriter to finish revealing, then add final message (only if still same session)
  useEffect(() => {
    if (!streamEnded || streamingContent === null) return;
    if (streamingSessionIdRef.current !== null && sessionIdRef.current !== streamingSessionIdRef.current) {
      if (streamingMessageIdRef.current) {
        removeMessage(streamingMessageIdRef.current);
        streamingMessageIdRef.current = null;
      }
      setStreamingContent(null);
      setStreamEnded(false);
      pendingFinalTextRef.current = null;
      pendingStreamFileInfoRef.current = null;
      pendingStreamThinkingRef.current = [];
      pendingStreamRagEvalRef.current = null;
      setStreamThinkingSteps([]);
      setStreamRagEval(null);
      streamingSessionIdRef.current = null;
      setIsProcessing(false);
      streamMessageAddedRef.current = false;
      streamBubbleHiddenRef.current = false;
      return;
    }
    const targetLen = streamingContent.length;
    if (streamingDisplayLength < targetLen) return;
    if (streamMessageAddedRef.current) return;
    streamMessageAddedRef.current = true;
    const finalText = pendingFinalTextRef.current ?? streamingContent;
    const baseFileInfo = pendingStreamFileInfoRef.current ?? undefined;
    const thinkingPayload = pendingStreamThinkingRef.current;
    const ragPayload = pendingStreamRagEvalRef.current;
    const qualityFileInfo = (thinkingPayload.length > 0 || ragPayload)
      ? {
          ...(baseFileInfo || {}),
          ...(thinkingPayload.length > 0 ? { thinkingSteps: thinkingPayload } : {}),
          ...(ragPayload ? { ragEvaluation: ragPayload } : {}),
        }
      : baseFileInfo;
    const displayText = (baseFileInfo?.type === 'summary' && (baseFileInfo?.summary?.summary != null))
      ? `🤖 AI Summary:\n\n"${baseFileInfo.summary.summary}"`
      : (finalText || 'No response received.');
    setStreamingContent(null);
    setStreamEnded(false);
    pendingFinalTextRef.current = null;
    pendingStreamFileInfoRef.current = null;
    pendingStreamThinkingRef.current = [];
    pendingStreamRagEvalRef.current = null;
    setStreamThinkingSteps([]);
    setStreamRagEval(null);
    streamingSessionIdRef.current = null;
    setIsProcessing(false);
    streamBubbleHiddenRef.current = true;
    const sid = streamingMessageIdRef.current;
    if (baseFileInfo === undefined && sid) {
      // Chat query: update the single streaming message (no second message)
      updateMessageContent(sid, displayText, { fileInfo: qualityFileInfo, saveToBackend: true });
      streamingMessageIdRef.current = null;
    } else {
      contextAddMessage({
        type: 'bot',
        content: displayText,
        timestamp: new Date(),
        fileInfo: qualityFileInfo,
      });
    }
  }, [
    contextAddMessage,
    removeMessage,
    streamEnded,
    streamingContent,
    streamingDisplayLength,
    updateMessageContent,
  ]);

  const streamingDisplayText = streamingContent === null ? '' : streamingContent.slice(0, streamingDisplayLength);

  // Auto-scroll during streaming; use instant scroll so content doesn't lag
  useEffect(() => {
    if (streamingContent !== null) scrollToBottom(true);
  }, [streamingContent, streamingDisplayLength]);

  const addMessage = (type: 'user' | 'bot', content: string, fileInfo?: any) => {
    contextAddMessage({
      type,
      content,
      timestamp: new Date(),
      fileInfo,
    });
  };

  const applyUserSignaturePlaceholders = (draftText: string): string => {
    if (!draftText) return draftText;
    const fullName = user?.full_name?.trim() || '-';
    const position = user?.department?.trim() || user?.role?.trim() || '-';
    const contact = [
      user?.phone_number ? `Tel: ${user.phone_number}` : null,
      user?.email ? `Email: ${user.email}` : null,
    ].filter(Boolean).join(' | ') || '-';
    const today = new Date().toLocaleDateString('en-GB', {
      year: 'numeric',
      month: 'long',
      day: '2-digit',
    });
    return draftText
      .replace(/\[\s*Your\s*Name\s*\]/gi, fullName)
      .replace(/\[\s*Your\s*Position\s*\]/gi, position)
      .replace(/\[\s*Contact\s*Information\s*\]/gi, contact)
      .replace(/\[\s*Date\s*\]/gi, today);
  };

  const buildDraftMessageContent = (replyType: string, draftText: string): string =>
    `📝 **Draft Reply (${replyType})**\n\n${draftText}`;

  const parseDraftMessage = (content: string): { isDraft: boolean; header: string; body: string } => {
    const match = content.match(/^(📝\s*\*\*(?:Draft Reply|回覆草稿)\s*\([^)]+\)\*\*)\s*\n\n?/);
    if (!match) {
      return { isDraft: false, header: '', body: content };
    }
    return {
      isDraft: true,
      header: match[1],
      body: content.slice(match[0].length),
    };
  };

  // Handle file selection (not immediate processing, just file selection)
  const handleFileSelection = (files: File[]) => {
    if (files.length === 0) return;

    // Validate file types and sizes
    const allowedTypes = [
      'text/plain',
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
      'image/jpeg',
      'image/png',
      'application/zip',
      'application/x-zip-compressed',
      'application/vnd.ms-excel', // .xls
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // .xlsx
    ];
    const maxSize = 10 * 1024 * 1024; // 10MB limit
    
    const invalidFiles = files.filter(file => 
      !allowedTypes.includes(file.type) || file.size > maxSize
    );
    
    if (invalidFiles.length > 0) {
      const errorMsg = invalidFiles.map(file => {
        if (!allowedTypes.includes(file.type)) {
          return `${file.name}: Unsupported file type`;
        }
        if (file.size > maxSize) {
          return `${file.name}: File size exceeds 10MB limit`;
        }
        return `${file.name}: Unknown error`;
      }).join('\n');
      
      addMessage('bot', `The following files cannot be processed:\n${errorMsg}\n\nSupported: TXT, PDF, DOCX, JPG/PNG (location maps, site photos), ZIP (max 10MB each).`);
      
      // Filter out invalid files
      const validFiles = files.filter(file => 
        allowedTypes.includes(file.type) && file.size <= maxSize
      );
      
      if (validFiles.length === 0) return;
      files = validFiles;
    }

    // Add to existing file list (avoid duplicates)
    const newFiles = files.filter(newFile => 
      !selectedFiles.some(existingFile => 
        existingFile.name === newFile.name && existingFile.size === newFile.size
      )
    );
    
    if (newFiles.length === 0) {
      addMessage('bot', 'Selected files already exist in the list.');
      return;
    }
    
    setSelectedFiles(prev => [...prev, ...newFiles]);
    
    // Display file selection message in chat
    if (newFiles.length === 1) {
      addMessage('user', `📁 Added file: ${newFiles[0].name}`, {
        name: newFiles[0].name,
        size: newFiles[0].size,
        type: newFiles[0].type,
      });
    } else {
      const fileNames = newFiles.map(f => f.name).join(', ');
      addMessage('user', `📁 Added ${newFiles.length} files: ${fileNames}`);
    }
    
    // Display current total file count
    const totalFiles = selectedFiles.length + newFiles.length;
    addMessage('bot', `✅ Files added successfully! Total: ${totalFiles} file${totalFiles > 1 ? 's' : ''}.\n\nClick the "📁 Upload Files" button to view and manage your files, or click "Process Files" to start processing.`);
  };

  const handleRemoveFile = (index: number) => {
    const newFiles = selectedFiles.filter((_, i) => i !== index);
    setSelectedFiles(newFiles);
    if (newFiles.length === 0) {
      addMessage('bot', 'All files removed from selection.');
    } else {
      addMessage('bot', `File removed. ${newFiles.length} file${newFiles.length > 1 ? 's' : ''} remaining.`);
    }
  };

  const handleClearAllFiles = () => {
    setSelectedFiles([]);
    addMessage('bot', 'All files cleared from selection.');
  };

  // Handle file upload (actual processing of selected files)
  // When reprocessOverride is provided, process that file with force_reprocess to bypass duplicate check
  const handleFileUpload = async (reprocessOverride?: { file: File }) => {
    setIsUploadModalOpen(false);
    let files = reprocessOverride ? [reprocessOverride.file] : selectedFiles;
    const forceReprocess = !!reprocessOverride;
    if (files.length === 0) {
      addMessage('bot', 'Please select files to process first.');
      return;
    }

    // Folder flow: multiple files, single ZIP, or single image (supports location maps, site photos)
    const singleFile = files[0];
    const isZip = singleFile.name.toLowerCase().endsWith('.zip');
    const isImage = singleFile.type.startsWith('image/');
    const useFolderFlow = files.length > 1 || (files.length === 1 && (isZip || isImage));
    if (useFolderFlow) {
      const fileNames = files.map((f) => f.name).join(', ');
      addMessage('user', `Upload ${files.length} file(s): ${fileNames}`);
      addMessage('bot', 'Processing folder (core doc + location maps / site photos / ZIP)...');
      const sessionIdAtStart = sessionIdRef.current;
      processingSessionIdRef.current = sessionIdAtStart;
      setProcessingSessionId(sessionIdAtStart);
      setIsProcessing(true);
      setCurrentFile({ name: fileNames, size: 0, type: '' });
      processingCaseDataRef.current = null;
      setCreateCaseSteps([]);
      const buildExtractedMessage = (d: any) => `✅ File Processing Successful!

📋 Extracted Case Information:

📅 Date Received: ${d.A_date_received || 'N/A'}
📋 Source: ${d.B_source || 'N/A'}
🔢 Case Number: ${d.C_case_number || 'N/A'}
⚡ Type: ${d.D_type || 'N/A'}
👤 Caller: ${d.E_caller_name || 'N/A'}
📞 Contact: ${d.F_contact_no || 'N/A'}
🏗️ Slope Number: ${d.G_slope_no || 'N/A'}
📍 Location: ${d.H_location || 'N/A'}
📝 Nature of Request: ${d.I_nature_of_request || 'N/A'}
🏷️ Subject Matter: ${d.J_subject_matter || 'N/A'}
⏰ 10-day Due: ${d.K_10day_rule_due_date || 'N/A'}
⏰ ICC Interim Due: ${d.L_icc_interim_due || 'N/A'}
⏰ ICC Final Due: ${d.M_icc_final_due || 'N/A'}`;
      try {
        const result = await createCaseFromFolder(files);
        if (sessionIdRef.current !== sessionIdAtStart) return;
        const fields = toExtractedData(result.fields || {});
        if (result.status === 'duplicate') {
          addMessage('bot', result.message || 'File already processed.');
          if (result.case_id != null) setCurrentCaseId(result.case_id);
          setSessionData(sessionIdAtStart, { extractedData: fields, currentFile: { name: fileNames, size: 0, type: '' } });
          setExtractedData(fields);
          setSelectedFiles([]);
        } else {
          setExtractedData(fields);
          if (result.case_id != null) setCurrentCaseId(result.case_id);
          processingCaseDataRef.current = fields;
          setSessionData(sessionIdAtStart, { extractedData: fields, currentFile: { name: fileNames, size: 0, type: '' } });
          addMessage('bot', buildExtractedMessage(fields), { type: 'parsed-success' });
          if (result.summary) {
            addMessage('bot', `🤖 AI Summary:\n\n"${result.summary}"`, { type: 'summary', summary: { success: true, summary: result.summary } });
          }
          const similarCases = result.similar_cases || [];
          if (similarCases.length > 0) {
            const msg = similarCases.map((item: any, i: number) => {
              const c = item.case ?? item;
              const score = ((item.similarity_score ?? 0) * 100).toFixed(1);
              return `**${i + 1}. Case #${c.C_case_number || 'N/A'}** (${score}% match)\n   📍 ${c.H_location || 'N/A'}\n   🏗️ ${c.G_slope_no || 'N/A'}`;
            }).join('\n\n');
            addMessage('bot', `📚 **Similar Historical Cases:**\n\n${msg}`, { type: 'similar-cases', cases: similarCases });
          } else {
            addMessage('bot', '✅ No similar historical cases found.');
          }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Unknown error';
        addMessage('bot', `❌ Processing failed: ${msg}`);
      } finally {
        setIsProcessing(false);
        setProcessingSessionId(null);
        setSelectedFiles([]);
      }
      return;
    }

    // Single file processing (SSE stream)
    if (files.length === 1) {
      const file = files[0];
      const fileInfo = {
        name: file.name,
        size: file.size,
        type: file.type,
      };

      addMessage('user', `Upload file: ${file.name}`, fileInfo);

      let processingMessage = 'Processing your file, please wait...';
      if (file.name.toLowerCase().startsWith('rcc') && file.type === 'application/pdf') {
        processingMessage = 'Processing RCC PDF file, OCR recognition may take 1-2 minutes, please be patient...';
      } else if (file.type === 'application/pdf') {
        processingMessage = 'Processing PDF file, please wait...';
      }
      addMessage('bot', processingMessage);

      const sessionIdAtStart = sessionIdRef.current;
      processingSessionIdRef.current = sessionIdAtStart;
      setProcessingSessionId(sessionIdAtStart);
      setIsProcessing(true);
      setCurrentFile(fileInfo);
      processingCaseDataRef.current = null;
      setCreateCaseSteps([]);

      const buildExtractedMessage = (d: any) => `✅ File Processing Successful!

📋 Extracted Case Information:

📅 Date Received: ${d.A_date_received || 'N/A'}
📋 Source: ${d.B_source || 'N/A'}
🔢 Case Number: ${d.C_case_number || 'N/A'}
⚡ Type: ${d.D_type || 'N/A'}
👤 Caller: ${d.E_caller_name || 'N/A'}
📞 Contact: ${d.F_contact_no || 'N/A'}
🏗️ Slope Number: ${d.G_slope_no || 'N/A'}
📍 Location: ${d.H_location || 'N/A'}
📝 Nature of Request: ${d.I_nature_of_request || 'N/A'}
🏷️ Subject Matter: ${d.J_subject_matter || 'N/A'}
⏰ 10-day Due: ${d.K_10day_rule_due_date || 'N/A'}
⏰ ICC Interim Due: ${d.L_icc_interim_due || 'N/A'}
⏰ ICC Final Due: ${d.M_icc_final_due || 'N/A'}`;

      createCase(
        file,
        {
          ...(forceReprocess ? { forceReprocess: true } : {}),
          embedding_provider: embeddingModel.provider,
          embedding_model: embeddingModel.model,
        },
        {
          onStepsDone: (steps) => {
            if (sessionIdRef.current === sessionIdAtStart) setCreateCaseSteps(steps ?? []);
          },
          onExtracted: (data) => {
            const sd = data.structured_data;
            const switched = sessionIdRef.current !== sessionIdAtStart;
            if (switched) {
              setSessionData(sessionIdAtStart, { extractedData: sd, currentFile: fileInfo, raw_content: data.raw_content ?? null });
              saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content: buildExtractedMessage(sd), file_info: { type: 'parsed-success' } }).catch(() => {});
              return;
            }
            setExtractedData(sd);
            const rawContent = data.raw_content ?? undefined;
            setRawFileContent(rawContent ?? null);
            if (data.case_id != null) setCurrentCaseId(data.case_id);
            processingCaseDataRef.current = sd;
            setSessionData(sessionIdAtStart, { extractedData: sd, currentFile: fileInfo, raw_content: rawContent ?? null });
            addMessage('bot', buildExtractedMessage(sd), { type: 'parsed-success' });
          },
          onSummaryChunk: (text) => {
            if (sessionIdRef.current !== sessionIdAtStart) return;
            streamingSessionIdRef.current = sessionIdAtStart;
            setStreamingContent((prev) => (prev ?? '') + text);
          },
          onSummaryFull: (summary, success) => {
            const switched = sessionIdRef.current !== sessionIdAtStart;
            if (switched) {
              const content = success && summary ? `🤖 AI Summary:\n\n"${summary}"` : `⚠️ AI summary generation failed: ${summary || 'Unknown error'}`;
              saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content, file_info: success ? { type: 'summary', summary: { success, summary } } : { type: 'summary-error' } }).catch(() => {});
              return;
            }
            setSummaryResult({ success, summary: success ? summary : undefined, error: success ? undefined : summary });
            if (streamingContentRef.current === '' || streamingContentRef.current === null) {
              if (success && summary) {
                addMessage('bot', `🤖 AI Summary:\n\n"${summary}"`, { type: 'summary', summary: { success, summary } });
              } else {
                addMessage('bot', `⚠️ AI summary generation failed: ${summary || 'Unknown error'}`, { type: 'summary-error' });
              }
            } else {
              if (!success) {
                pendingFinalTextRef.current = `⚠️ AI summary generation failed: ${summary || 'Unknown error'}`;
              }
              setStreamEnded(true);
              pendingStreamFileInfoRef.current = success
                ? { type: 'summary', summary: { success, summary: success ? summary : undefined } }
                : { type: 'summary-error' };
            }
          },
          onSimilarCases: async (similar_cases: any[]) => {
            const caseData = processingCaseDataRef.current;
            const cases = similar_cases ?? [];
            const buildSimilarCasesMessage = (inputCases: any[]) => {
              let message = `📚 **Found ${inputCases.length} Similar Historical Cases:**\n\n`;
              inputCases.forEach((item: any, index: number) => {
                const c = item.case ?? item;
                const score = ((item.similarity_score ?? 0) * 100).toFixed(1);
                const isDup = item.is_potential_duplicate ? ' 🔴 **POTENTIAL DUPLICATE**' : '';
                const source = item.data_source || 'Unknown';
                message += `**${index + 1}. [${source}] Case #${c.C_case_number || 'N/A'}** (${score}% match)${isDup}\n`;
                message += `   📅 Date: ${c.A_date_received || 'N/A'}\n`;
                message += `   📍 Location: ${c.H_location || 'N/A'}\n`;
                message += `   🏗️ Slope: ${c.G_slope_no || 'N/A'}\n`;
                message += `   📝 Subject: ${c.J_subject_matter || 'N/A'}\n`;
                if (c.E_caller_name || c.F_contact_no) {
                  message += `   👤 Caller: ${c.E_caller_name || 'N/A'}\n`;
                  message += `   📞 Phone: ${c.F_contact_no || 'N/A'}\n`;
                }
                if (c.tree_id || c.tree_count) {
                  if (c.tree_id) message += `   🌳 Tree ID: ${c.tree_id}\n`;
                  if (c.tree_count) message += `   🌲 Number of Trees: ${c.tree_count}\n`;
                }
                if (c.I_nature_of_request && c.I_nature_of_request !== 'N/A' && c.I_nature_of_request.trim()) {
                  const nature = c.I_nature_of_request.length > 150 ? c.I_nature_of_request.substring(0, 150) + '...' : c.I_nature_of_request;
                  message += `   📄 Complaint Details: ${nature}\n`;
                }
                if (c.inspector_remarks) message += `   🔍 Inspector Remarks: ${c.inspector_remarks}\n`;
                message += '\n';
              });
              return message;
            };
            const buildLocationStatsMessage = (stats: any) => {
              const isFrequent = stats.is_frequent_complaint;
              let statsMessage = `📊 **Location Statistics:**\n\n📍 Location: ${caseData.H_location}\n📈 Total Cases: ${stats.total_cases}\n⚠️ Frequent Complaint: ${isFrequent ? 'YES 🔴' : 'NO ✅'}\n\n`;
              if (isFrequent) statsMessage += `⚠️ **This location has received ${stats.total_cases} complaints, indicating a recurring issue that may require attention.**`;
              return statsMessage;
            };

            const switchedSimilar = sessionIdRef.current !== sessionIdAtStart;
            if (switchedSimilar) {
              let similarCasesSaved = false;
              try {
                if (cases.length > 0) {
                  await saveMessageToSession(sessionIdAtStart, {
                    message_type: 'bot',
                    content: buildSimilarCasesMessage(cases),
                    file_info: { type: 'similar-cases', cases },
                  });
                } else {
                  await saveMessageToSession(sessionIdAtStart, {
                    message_type: 'bot',
                    content: '✅ No similar historical cases found. This appears to be a unique case.',
                    file_info: { type: 'similar-cases-empty' },
                  });
                }
                similarCasesSaved = true;
              } catch (err) {
                console.error('Similar case display error:', err);
              }
              if (!similarCasesSaved) {
                await saveMessageToSession(sessionIdAtStart, {
                  message_type: 'bot',
                  content: '⚠️ Unable to show similar cases, but file processing was successful.',
                });
                return;
              }
              if (caseData?.H_location) {
                try {
                  const statsResult = await getCaseStatistics({ location: caseData.H_location });
                  if (statsResult.status === 'success' && statsResult.statistics) {
                    await saveMessageToSession(sessionIdAtStart, {
                      message_type: 'bot',
                      content: buildLocationStatsMessage(statsResult.statistics),
                      file_info: { type: 'location-stats' },
                    });
                  }
                } catch (err) {
                  console.error('Location statistics error:', err);
                }
              }
              return;
            }

            let similarCasesRendered = false;
            try {
              if (cases.length > 0) {
                addMessage('bot', buildSimilarCasesMessage(cases), { type: 'similar-cases', cases });
              } else {
                addMessage('bot', '✅ No similar historical cases found. This appears to be a unique case.', { type: 'similar-cases-empty' });
              }
              similarCasesRendered = true;
            } catch (err) {
              console.error('Similar case display error:', err);
            }
            if (!similarCasesRendered) {
              addMessage('bot', '⚠️ Unable to show similar cases, but file processing was successful.');
              return;
            }
            if (caseData?.H_location) {
              try {
                const statsResult = await getCaseStatistics({ location: caseData.H_location });
                if (sessionIdRef.current !== sessionIdAtStart) return;
                if (statsResult.status === 'success' && statsResult.statistics) {
                  addMessage('bot', buildLocationStatsMessage(statsResult.statistics), { type: 'location-stats' });
                }
              } catch (err) {
                console.error('Location statistics error:', err);
              }
            }
          },
          onDone: (result) => {
            if (sessionIdRef.current !== sessionIdAtStart) return;
            if (result.case_id != null) setCurrentCaseId(result.case_id);
            setCreateCaseSteps([]);
            setIsProcessing(false);
            setProcessingSessionId(null);
            if (!forceReprocess) setSelectedFiles([]);
            setIsUploadModalOpen(false);
          },
          onDuplicate: (data) => {
            reprocessFileRef.current = file;
            setCreateCaseSteps([]);
            if (sessionIdRef.current !== sessionIdAtStart) {
              setProcessingSessionId(null);
              saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content: data.message, file_info: { duplicateCaseId: data.case_id } }).catch(() => {});
              return;
            }
            setIsProcessing(false);
            setProcessingSessionId(null);
            setStreamingContent(null);
            setSessionData(sessionIdAtStart, { extractedData: data.structured_data, currentFile: fileInfo });
            addMessage('bot', data.message, { duplicateCaseId: data.case_id });
            if (!forceReprocess) setSelectedFiles([]);
            setIsUploadModalOpen(false);
          },
          onError: (message) => {
            setCreateCaseSteps([]);
            if (sessionIdRef.current !== sessionIdAtStart) {
              setProcessingSessionId(null);
              saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content: message }).catch(() => {});
              return;
            }
            setIsProcessing(false);
            setProcessingSessionId(null);
            setStreamingContent(null);
            addMessage('bot', message);
            setSelectedFiles([]);
            setIsUploadModalOpen(false);
          },
        }
      ).catch((error) => {
        if (sessionIdRef.current !== sessionIdAtStart) {
          setProcessingSessionId(null);
          saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content: `Error processing file: ${error instanceof Error ? error.message : 'Unknown error'}` }).catch(() => {});
          return;
        }
        setIsProcessing(false);
        setProcessingSessionId(null);
        setStreamingContent(null);
        addMessage('bot', `Error processing file: ${error instanceof Error ? error.message : 'Unknown error'}`);
        setSelectedFiles([]);
        setIsUploadModalOpen(false);
      });
    } 
    // Multi-file batch processing
    else {
      const fileNames = files.map(f => f.name).join(', ');
      addMessage('user', `Batch upload ${files.length} files: ${fileNames}`);
      
      addMessage('bot', `Processing ${files.length} files in batch, please wait...
      ${files.some(f => f.name.toLowerCase().startsWith('rcc')) ? 
      '⚠️ RCC files detected, OCR processing may take longer time.' : ''}`);

      const sessionIdAtStartBatch = sessionIdRef.current;
      processingSessionIdRef.current = sessionIdAtStartBatch;
      setIsProcessing(true);
      setCurrentFile({ name: `${files.length} files`, size: 0, type: 'batch' } as any);

      try {
        const result: BatchProcessingResponse = await processMultipleFiles(files);
        if (sessionIdRef.current !== sessionIdAtStartBatch) {
          setIsProcessing(false);
          setStreamingContent(null);
          const successFiles = result.results.filter((r: { status: string }) => r.status === 'success');
          const failedFiles = result.results.filter((r: { status: string }) => r.status === 'error');
          const skippedFiles = result.results.filter((r: { status: string }) => r.status === 'skipped');
          let resultMessage = `📊 Batch processing completed!

📈 Processing Statistics:
• Total files: ${result.total_files}
• Successfully processed: ${result.successful}
• Processing failed: ${result.failed}
• Skipped files: ${result.skipped}`;
          if (successFiles.length > 0) {
            resultMessage += `\n\n✅ Successfully processed files (${successFiles.length}):`;
            successFiles.forEach((f: any, index: number) => {
              resultMessage += `\n\n${index + 1}. ${f.main_file}`;
              if (f.email_file) resultMessage += ` (paired with ${f.email_file})`;
              resultMessage += `\n   Case ID: ${f.case_id || 'N/A'}\n   Status: ${f.message}`;
              if (f.structured_data) resultMessage += `\n   📋 Extracted: Date=${f.structured_data.A_date_received || 'N/A'}, Case=${f.structured_data.C_case_number || 'N/A'}, Location=${f.structured_data.H_location || 'N/A'}`;
            });
          }
          if (failedFiles.length > 0) {
            resultMessage += `\n\n❌ Failed to process files (${failedFiles.length}):`;
            failedFiles.forEach((f: any, index: number) => {
              resultMessage += `\n${index + 1}. ${f.main_file}\n   Case ID: ${f.case_id || 'N/A'}\n   Error: ${f.message}`;
            });
          }
          if (skippedFiles.length > 0) {
            resultMessage += `\n\n⏭️ Skipped files (${skippedFiles.length}):`;
            skippedFiles.forEach((f: any, index: number) => {
              resultMessage += `\n${index + 1}. ${f.main_file}\n   Case ID: ${f.case_id || 'N/A'}\n   Reason: ${f.message}`;
            });
          }
          if (successFiles.length > 0) {
            resultMessage += `\n\n💡 Note: The right information panel shows the last successfully processed file (${successFiles[successFiles.length - 1].main_file}).`;
            resultMessage += `\n   All ${successFiles.length} files have been processed successfully.`;
            resultMessage += `\n   You can ask questions about any of the processed cases.`;
            const lastSuccessFile = successFiles[successFiles.length - 1];
            if (lastSuccessFile.structured_data) {
              setSessionData(sessionIdAtStartBatch, { extractedData: lastSuccessFile.structured_data, currentFile: { name: `${result.total_files} files`, size: 0, type: 'batch' } as any });
            }
          }
          saveMessageToSession(sessionIdAtStartBatch, { message_type: 'bot', content: resultMessage }).catch(() => {});
          return;
        }
        
        setIsProcessing(false);

        // Display batch processing results - 显示所有文件的结果，包括跳过的
        const successFiles = result.results.filter(r => r.status === 'success');
        const failedFiles = result.results.filter(r => r.status === 'error');
        const skippedFiles = result.results.filter(r => r.status === 'skipped');  // 新增
        
        let resultMessage = `📊 Batch processing completed!

📈 Processing Statistics:
• Total files: ${result.total_files}
• Successfully processed: ${result.successful}
• Processing failed: ${result.failed}
• Skipped files: ${result.skipped}`;  // 添加跳过统计

        // 显示成功文件（包含详细信息）
        if (successFiles.length > 0) {
          resultMessage += `\n\n✅ Successfully processed files (${successFiles.length}):`;
          successFiles.forEach((f, index) => {
            resultMessage += `\n\n${index + 1}. ${f.main_file}`;
            if (f.email_file) {
              resultMessage += ` (paired with ${f.email_file})`;
            }
            resultMessage += `\n   Case ID: ${f.case_id || 'N/A'}`;
            resultMessage += `\n   Status: ${f.message}`;
            if (f.structured_data) {
              resultMessage += `\n   📋 Extracted: Date=${f.structured_data.A_date_received || 'N/A'}, Case=${f.structured_data.C_case_number || 'N/A'}, Location=${f.structured_data.H_location || 'N/A'}`;
            }
          });
        }

        // 显示失败文件
        if (failedFiles.length > 0) {
          resultMessage += `\n\n❌ Failed to process files (${failedFiles.length}):`;
          failedFiles.forEach((f, index) => {
            resultMessage += `\n${index + 1}. ${f.main_file}`;
            resultMessage += `\n   Case ID: ${f.case_id || 'N/A'}`;
            resultMessage += `\n   Error: ${f.message}`;
          });
        }

        // 显示跳过的文件（新增）
        if (skippedFiles.length > 0) {
          resultMessage += `\n\n⏭️ Skipped files (${skippedFiles.length}):`;
          skippedFiles.forEach((f, index) => {
            resultMessage += `\n${index + 1}. ${f.main_file}`;
            resultMessage += `\n   Case ID: ${f.case_id || 'N/A'}`;
            resultMessage += `\n   Reason: ${f.message}`;
          });
        }

        if (successFiles.length > 0) {
          resultMessage += `\n\n💡 Note: The right information panel shows the last successfully processed file (${successFiles[successFiles.length - 1].main_file}).`;
          resultMessage += `\n   All ${successFiles.length} files have been processed successfully.`;
          resultMessage += `\n   You can ask questions about any of the processed cases.`;
          
          // 设置最后一个成功文件的数据到右侧面板
          const lastSuccessFile = successFiles[successFiles.length - 1];
          if (lastSuccessFile.structured_data) {
            setExtractedData(lastSuccessFile.structured_data);
          }
          // Batch processing does not save to DB, so case_id is string (filename). No numeric case_id for reply draft.
        }

        addMessage('bot', resultMessage);
        
        // Clear file list after batch processing
        setSelectedFiles([]);
        setIsUploadModalOpen(false);
        
      } catch (error) {
        if (sessionIdRef.current !== sessionIdAtStartBatch) {
          setIsProcessing(false);
          setStreamingContent(null);
          saveMessageToSession(sessionIdAtStartBatch, { message_type: 'bot', content: `Error in batch processing files: ${error instanceof Error ? error.message : 'Unknown error'}` }).catch(() => {});
          return;
        }
        setIsProcessing(false);
        addMessage('bot', `Error in batch processing files: ${error instanceof Error ? error.message : 'Unknown error'}`);
        
        // Clear file list on error
        setSelectedFiles([]);
        setIsUploadModalOpen(false);
      }
    }
  };

  const handleLoadCaseForDraft = async (caseId: number, filename: string, caseData: any) => {
    try {
      const extracted: ExtractedData = {
        A_date_received: caseData.A_date_received ?? '',
        B_source: caseData.B_source ?? '',
        C_case_number: caseData.C_case_number ?? '',
        D_type: caseData.D_type ?? '',
        E_caller_name: caseData.E_caller_name ?? '',
        F_contact_no: caseData.F_contact_no ?? '',
        G_slope_no: caseData.G_slope_no ?? '',
        H_location: caseData.H_location ?? '',
        I_nature_of_request: caseData.I_nature_of_request ?? '',
        J_subject_matter: caseData.J_subject_matter ?? '',
        K_10day_rule_due_date: caseData.K_10day_rule_due_date ?? '',
        L_icc_interim_due: caseData.L_icc_interim_due ?? '',
        M_icc_final_due: caseData.M_icc_final_due ?? '',
        N_works_completion_due: caseData.N_works_completion_due ?? '',
        O1_fax_to_contractor: caseData.O1_fax_to_contractor ?? '',
        O2_email_send_time: caseData.O2_email_send_time ?? '',
        P_fax_pages: caseData.P_fax_pages ?? '',
        Q_case_details: caseData.Q_case_details ?? ''
      };
      setExtractedData(extracted);
      setCurrentFile({ name: filename, size: 0, type: '', case_id: caseId });
      setCurrentCaseId(caseId);
      setCaseDetailModalId(null);
    } catch (err) {
      console.error('Load case for draft error:', err);
      addMessage('bot', `Failed to load case: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  const handleReplyTemplateClick = async (replyType: string, skipQuestions: boolean) => {
    const cid = effectiveCaseId;
    if (cid == null || typeof cid !== 'number') {
      addMessage('bot', '⚠️ Cannot generate draft reply: please process a single file first, or load a case from the case list.');
      return;
    }
    const sessionIdAtStart = sessionIdRef.current;
    processingSessionIdRef.current = sessionIdAtStart;
    setIsProcessing(true);
    addMessage('user', skipQuestions ? `Generate ${replyType} reply directly` : `Draft ${replyType} reply`);
    try {
      if (skipQuestions) {
        setStreamingContent('');
        const { fullText, conversation_id } = await generateReplyDraftStream(
          { case_id: cid, reply_type: replyType, is_initial: true, skip_questions: true },
          (chunk) => {
            if (sessionIdRef.current === sessionIdAtStart) {
              setStreamingContent((prev) => (prev ?? '') + chunk);
            }
          }
        );
        if (sessionIdRef.current !== sessionIdAtStart) {
          setStreamingContent(null);
          setIsProcessing(false);
          const draftText = fullText ? applyUserSignaturePlaceholders(fullText) : '';
          saveMessageToSession(
            sessionIdAtStart,
            { message_type: 'bot', content: draftText ? buildDraftMessageContent(replyType, draftText) : 'Draft reply generated.' }
          ).catch(() => {});
          return;
        }
        setStreamingContent(null);
        setIsProcessing(false);
        const draftText = fullText ? applyUserSignaturePlaceholders(fullText) : '';
        if (draftText && conversation_id) {
          updateConversationDraft(conversation_id, draftText).catch(() => {});
        }
        addMessage(
          'bot',
          draftText ? buildDraftMessageContent(replyType, draftText) : 'Draft reply generated.',
          { type: 'draft-reply', conversationId: conversation_id }
        );
      } else {
        const res = await generateReplyDraft({
          case_id: cid,
          reply_type: replyType,
          is_initial: true,
          skip_questions: false
        });
        if (sessionIdRef.current !== sessionIdAtStart) {
          setIsProcessing(false);
          const normalizedDraft = res.draft_reply ? applyUserSignaturePlaceholders(res.draft_reply) : '';
          const content = res.is_question ? res.message : (normalizedDraft ? buildDraftMessageContent(replyType, normalizedDraft) : (res.message || 'Draft reply generated.'));
          saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content }).catch(() => {});
          return;
        }
        setIsProcessing(false);
        if (res.is_question) {
          setReplyDraftState({ conversationId: res.conversation_id, replyType });
          addMessage('bot', res.message);
        } else if (res.draft_reply) {
          const normalizedDraft = applyUserSignaturePlaceholders(res.draft_reply);
          if (normalizedDraft && res.conversation_id) {
            updateConversationDraft(res.conversation_id, normalizedDraft).catch(() => {});
          }
          addMessage('bot', buildDraftMessageContent(replyType, normalizedDraft), { type: 'draft-reply', conversationId: res.conversation_id });
        } else {
          addMessage('bot', res.message || 'Draft reply generated.');
        }
      }
    } catch (err) {
      if (sessionIdRef.current !== sessionIdAtStart) {
        setStreamingContent(null);
        setIsProcessing(false);
        saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content: `Draft reply generation failed: ${err instanceof Error ? err.message : 'Unknown error'}` }).catch(() => {});
        return;
      }
      setStreamingContent(null);
      setIsProcessing(false);
      addMessage('bot', `Draft reply generation failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  // Handle user queries
  const handleQuery = async () => {
    if (!inputMessage.trim()) return;

    const userQuery = inputMessage.trim();
    setInputMessage('');
    setHistoryIndex(-1);

    // If replying to a draft question, route to generateReplyDraftStream (streaming)
    if (replyDraftState) {
      const { conversationId, replyType } = replyDraftState;
      const sessionIdAtStart = sessionIdRef.current;
      processingSessionIdRef.current = sessionIdAtStart;
      setReplyDraftState(null);
      addMessage('user', userQuery);
      setIsProcessing(true);
      setStreamingContent('');
      try {
        const { fullText, conversation_id } = await generateReplyDraftStream(
          {
            case_id: effectiveCaseId!,
            reply_type: replyType,
            conversation_id: conversationId,
            user_message: userQuery,
            is_initial: false,
            skip_questions: false
          },
          (chunk) => {
            if (sessionIdRef.current === sessionIdAtStart) {
              setStreamingContent((prev) => (prev ?? '') + chunk);
            }
          }
        );
        if (sessionIdRef.current !== sessionIdAtStart) {
          setStreamingContent(null);
          setIsProcessing(false);
          const normalizedDraft = fullText ? applyUserSignaturePlaceholders(fullText) : '';
          const finalContent = normalizedDraft ? buildDraftMessageContent(replyType, normalizedDraft) : 'Done.';
          saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content: finalContent }).catch(() => {});
          return;
        }
        const normalizedDraft = fullText ? applyUserSignaturePlaceholders(fullText) : '';
        if (normalizedDraft && conversation_id) {
          updateConversationDraft(conversation_id, normalizedDraft).catch(() => {});
        }
        const finalContent = normalizedDraft ? buildDraftMessageContent(replyType, normalizedDraft) : 'Done.';
        setIsProcessing(false);
        pendingFinalTextRef.current = finalContent;
        pendingStreamFileInfoRef.current = { type: 'draft-reply', conversationId: conversation_id };
        streamingSessionIdRef.current = sessionIdAtStart;
        setStreamEnded(true);
      } catch (err) {
        if (sessionIdRef.current !== sessionIdAtStart) {
          setStreamingContent(null);
          setIsProcessing(false);
          saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content: `Draft reply generation failed: ${err instanceof Error ? err.message : 'Unknown error'}` }).catch(() => {});
          return;
        }
        setStreamingContent(null);
        setIsProcessing(false);
        addMessage('bot', `Draft reply generation failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
      }
      return;
    }

    // Append to input history (avoid duplicate with latest, keep last 10)
    if (userQuery && (inputHistory.length === 0 || inputHistory[0] !== userQuery)) {
      const nextHistory = [userQuery, ...inputHistory].slice(0, INPUT_HISTORY_MAX);
      setInputHistory(nextHistory);
      try {
        localStorage.setItem(INPUT_HISTORY_KEY, JSON.stringify(nextHistory));
      } catch {
        /* ignore */
      }
    }

    addMessage('user', userQuery);

    const streamingId = `streaming-${Date.now()}`;
    streamingMessageIdRef.current = streamingId;
    contextAddMessage({ id: streamingId, type: 'bot', content: '', timestamp: new Date() });
    const sessionIdAtStart = sessionIdRef.current;
    processingSessionIdRef.current = sessionIdAtStart;
    setIsProcessing(true);
    setStreamingContent('');
    pendingStreamThinkingRef.current = [];
    pendingStreamRagEvalRef.current = null;
    setStreamThinkingSteps([]);
    setStreamRagEval(null);

    try {
      const effectiveModel = currentModels.includes(chatModel.model) ? chatModel.model : currentModels[0];
      const fullText = await queryCaseStream(
        {
          query: userQuery,
          context: extractedData || undefined,
          raw_content: rawFileContent ?? undefined,
          session_id: sessionIdAtStart,
          provider: chatModel.provider,
          model: effectiveModel,
          embedding_provider: embeddingModel.provider,
          embedding_model: embeddingModel.model,
        },
        {
          onTextChunk: (chunk) => {
            if (sessionIdRef.current === sessionIdAtStart) {
              setStreamingContent((prev) => (prev ?? '') + chunk);
            }
          },
          onThinkingStep: (step) => {
            if (sessionIdRef.current !== sessionIdAtStart) return;
            setStreamThinkingSteps((prev) => {
              const exists = prev.some((item) => item.step_id === step.step_id);
              const next = exists
                ? prev.map((item) => (item.step_id === step.step_id ? step : item))
                : [...prev, step];
              pendingStreamThinkingRef.current = next;
              return next;
            });
          },
          onRagEval: (_phase, data) => {
            if (sessionIdRef.current !== sessionIdAtStart) return;
            setStreamRagEval((prev) => {
              const next = { ...(prev || {}), ...(data || {}) };
              pendingStreamRagEvalRef.current = next;
              return next;
            });
          }
        },
      );

      if (sessionIdRef.current !== sessionIdAtStart) {
        if (streamingMessageIdRef.current) {
          removeMessage(streamingMessageIdRef.current);
          streamingMessageIdRef.current = null;
        }
        setStreamingContent(null);
        setIsProcessing(false);
        saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content: fullText || 'No response received.' }).catch(() => {});
        return;
      }
      // Ensure streaming state has the full text before ending, so effect uses correct length and no race with batched chunk updates
      const finalTextForQuery = fullText || 'No response received.';
      setIsProcessing(false);
      pendingFinalTextRef.current = finalTextForQuery;
      streamingSessionIdRef.current = sessionIdAtStart;
      setStreamingContent(finalTextForQuery);
      setStreamEnded(true);
    } catch (error) {
      if (sessionIdRef.current !== sessionIdAtStart) {
        if (streamingMessageIdRef.current) {
          removeMessage(streamingMessageIdRef.current);
          streamingMessageIdRef.current = null;
        }
        setStreamingContent(null);
        setIsProcessing(false);
        saveMessageToSession(sessionIdAtStart, { message_type: 'bot', content: `Query failed: ${error instanceof Error ? error.message : 'Unknown error'}` }).catch(() => {});
        return;
      }
      setStreamingContent(null);
      setIsProcessing(false);
      const errMsg = `Query failed: ${error instanceof Error ? error.message : 'Unknown error'}`;
      if (streamingMessageIdRef.current) {
        updateMessageContent(streamingMessageIdRef.current, errMsg, { saveToBackend: true });
        streamingMessageIdRef.current = null;
      } else {
        addMessage('bot', errMsg);
      }
    }
  };

  // Handle keyboard: Enter to send; ArrowUp/ArrowDown to cycle input history
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      // 输入法候选框时按 Enter 用于选字，不发送
      if (e.nativeEvent.isComposing) return;
      e.preventDefault();
      handleQuery();
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (inputHistory.length === 0) return;
      if (historyIndex === -1) inputBeforeHistoryRef.current = inputMessage;
      const nextIndex = historyIndex === -1 ? inputHistory.length - 1 : Math.min(historyIndex + 1, inputHistory.length - 1);
      setHistoryIndex(nextIndex);
      setInputMessage(inputHistory[nextIndex]);
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIndex <= 0) {
        setHistoryIndex(-1);
        setInputMessage(inputBeforeHistoryRef.current);
        return;
      }
      const nextIndex = historyIndex - 1;
      setHistoryIndex(nextIndex);
      setInputMessage(inputHistory[nextIndex]);
    }
  };

  // Note: Drag and drop functionality is now handled in FileUploadModal component

  return (
    <div className="chatbot-container">
      {/* Single integrated chat area */}
      <div className="chat-section-full">
        <div className="chat-header">
          <div className="header-content">
            <img src={universityLogo} alt="SRR Logo" className="header-logo" />
            <img src={logoImage} alt="SRR Logo" className="header-logo" />
            <div className="header-text">
              <h1>SRR Case Processing Assistant</h1>
              <p>Intelligent File Processing & Case Query System</p>
            </div>
          </div>
        </div>

        <div className="chat-messages">
          {sessionLoading && (
            <div className="message bot">
              <div className="message-avatar">
                <img src={botIcon} alt="Bot" className="avatar-image" />
              </div>
              <div className="message-content">
                <div className="loading">
                  <div className="confetti-dots">
                    <span></span><span></span><span></span><span></span><span></span>
                  </div>
                  Loading session...
                </div>
              </div>
            </div>
          )}
          {displayMessages.map((message, index) => {
            const messageKey = message.id ?? `msg-${index}`;
            const fileInfo = (message.fileInfo as { type?: string; conversationId?: number; duplicateCaseId?: number; cases?: any[] } | undefined);
            if (latestProcessingCard && index > latestProcessingCard.start && index <= latestProcessingCard.end) {
              return null;
            }
            if (latestProcessingCard && index === latestProcessingCard.start) {
              const sections = latestProcessingCard.sections;
              const summaryText = sections.summary?.content as string | undefined;
              const summaryErrorText = sections.summaryError?.content as string | undefined;
              const similarCases = (sections.similarCases?.fileInfo as { cases?: any[] } | undefined)?.cases ?? [];
              const similarCasesEmptyText = sections.similarCasesEmpty?.content as string | undefined;
              const locationStatsText = sections.locationStats?.content as string | undefined;
              return (
                <div key={`processing-card-${messageKey}`} className="message bot message--processing-card">
                  <div className="message-avatar">
                    <img src={botIcon} alt="Bot" className="avatar-image" />
                  </div>
                  <div className="message-content">
                    <div className="processing-card-title">🧾 File processing report</div>
                    <div className="processing-card-layout">
                      <div className="processing-card-top">
                        {sections.parsed?.content && (
                          <div className="processing-card-section processing-card-section--compact processing-card-section--parsed">
                            <div className="processing-card-section-title">Parsed case data</div>
                            <div className="message-text">{sections.parsed.content}</div>
                          </div>
                        )}
                        <div className="processing-card-right-col">
                          {(summaryText || summaryErrorText || shouldShowStreamingSummaryInCard) && (
                            <div className="processing-card-section processing-card-section--compact processing-card-section--summary">
                              <div className="processing-card-section-title">AI summary</div>
                              <div className="message-text">
                                {summaryText
                                  ? summaryText
                                  : summaryErrorText
                                    ? summaryErrorText
                                    : (
                                      <>
                                        {streamingDisplayText}
                                        <span className="streaming-cursor">▌</span>
                                      </>
                                    )}
                              </div>
                            </div>
                          )}
                          {extractedData && effectiveCaseId != null && typeof effectiveCaseId === 'number' && !suggestedActionsDismissed && (
                            <div className="processing-card-section processing-card-section--actions processing-card-section--compact processing-card-section--draft">
                              <SuggestedQuestions
                                onQuestionClick={(type, skipQuestions) => { void handleReplyTemplateClick(type, skipQuestions ?? false); }}
                                disabled={isLoading}
                                embedded
                                compact
                                showEndButton={true}
                                onEndDraft={() => { setReplyDraftState(null); setSuggestedActionsDismissed(true); }}
                              />
                            </div>
                          )}
                        </div>
                      </div>

                      {(similarCases.length > 0 || similarCasesEmptyText) && (
                        <div className="processing-card-section processing-card-section--bottom processing-card-section--similar">
                          <div className="processing-card-section-title">Similar historical cases</div>
                          {similarCases.length > 0 ? (
                            <SimilarCasesBlock cases={similarCases} />
                          ) : (
                            <div className="message-text">{similarCasesEmptyText}</div>
                          )}
                        </div>
                      )}

                      {locationStatsText && (
                        <div className="processing-card-section processing-card-section--compact">
                          <div className="processing-card-section-title">Location statistics</div>
                          <div className="message-text">{locationStatsText}</div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            }
            const parsedDraft = parseDraftMessage(message.content);
            const isDraftMessage = fileInfo?.type === 'draft-reply' || parsedDraft.isDraft;
            const isEditingThisDraft = isDraftMessage && editingDraftId === messageKey;
            const editedDraftBody = draftEdits[messageKey] ?? parsedDraft.body;
            return (
            <div key={messageKey} className={`message ${message.type}${isDraftMessage ? ' message--draft' : ''}`}>
              {message.type === 'bot' && (
                <div className="message-avatar">
                  <img src={botIcon} alt="Bot" className="avatar-image" />
                </div>
              )}
              <div className="message-content">
                {message.type === 'bot' && (() => {
                  const fileInfoAny = (message.fileInfo ?? {}) as {
                    thinkingSteps?: ThinkingStepEvent[];
                    ragEvaluation?: RAGEvalData;
                  };
                  const thinkingSteps =
                    message.id === streamingMessageIdRef.current
                      ? streamThinkingSteps
                      : (fileInfoAny.thinkingSteps ?? []);
                  const ragEval =
                    message.id === streamingMessageIdRef.current
                      ? streamRagEval
                      : fileInfoAny.ragEvaluation;
                  const isThinkingStreaming =
                    message.id === streamingMessageIdRef.current && isProcessing;
                  if (thinkingSteps.length === 0 && !ragEval) return null;
                  return (
                    <div className="eval-panels-row">
                      {thinkingSteps.length > 0 && (
                        <ThinkingChain steps={thinkingSteps} isStreaming={isThinkingStreaming} />
                      )}
                      {ragEval && <RAGEvalPanel data={ragEval} />}
                    </div>
                  );
                })()}
                {message.fileInfo && message.fileInfo.size != null && (() => {
                  const fi = message.fileInfo as { name?: string; filename?: string; size: number };
                  const label = fi.name ?? fi.filename ?? 'File';
                  return (
                    <div className="message-file-info-inline">
                      <FileText size={22} aria-hidden />
                      <span>{label} ({(fi.size / 1024).toFixed(1)} KB)</span>
                    </div>
                  );
                })()}

                <div className="message-text">
                  {message.id === streamingMessageIdRef.current && streamingContent !== null ? (
                    <>
                      {streamingDisplayText}
                      <span className="streaming-cursor">▌</span>
                    </>
                  ) : isEditingThisDraft ? (
                    <div className="draft-editor-block">
                      {parsedDraft.header ? (
                        <div className="draft-editor-title">{parsedDraft.header.replace(/\*\*/g, '')}</div>
                      ) : null}
                      <textarea
                        className="draft-editor-textarea"
                        value={editedDraftBody}
                        onChange={(e) => {
                          setDraftEdits((prev) => ({ ...prev, [messageKey]: e.target.value }));
                        }}
                        placeholder="Draft content..."
                      />
                    </div>
                  ) : fileInfo?.type === 'similar-cases' && Array.isArray(fileInfo?.cases) ? (
                    <SimilarCasesBlock cases={fileInfo.cases} />
                  ) : (
                    message.content
                  )}
                </div>
                {isDraftMessage && (
                  <div className="message-actions">
                    {!isEditingThisDraft && (
                      <button
                        type="button"
                        className="message-edit-draft"
                        onClick={() => {
                          setDraftEdits((prev) => ({ ...prev, [messageKey]: parsedDraft.body }));
                          setEditingDraftId(messageKey);
                        }}
                      >
                        <span>Edit draft</span>
                      </button>
                    )}
                    {!isEditingThisDraft && fileInfo?.conversationId != null && !approvedDraftIds.has(fileInfo.conversationId) && (
                      <button
                        type="button"
                        className="message-add-to-kb"
                        disabled={approvingDraftId === fileInfo.conversationId}
                        onClick={async () => {
                          const cid = fileInfo.conversationId!;
                          setApprovingDraftId(cid);
                          try {
                            const res = await approveDraftToKB(cid);
                            setApprovedDraftIds((prev) => new Set(prev).add(cid));
                            addMessage('bot', res.already_approved ? '✓ Already in knowledge base.' : '✓ Draft added to knowledge base for RAG retrieval.');
                          } catch (err) {
                            addMessage('bot', `Failed to add to KB: ${err instanceof Error ? err.message : 'Unknown error'}`);
                          } finally {
                            setApprovingDraftId(null);
                          }
                        }}
                        title="Add to Knowledge Base"
                        aria-label="Add to Knowledge Base"
                      >
                        <span>{approvingDraftId === fileInfo.conversationId ? 'Adding...' : 'Add to Knowledge Base'}</span>
                      </button>
                    )}
                    {isEditingThisDraft && (
                      <>
                        <button
                          type="button"
                          className="message-save-draft"
                          disabled={savingDraftMessageId === messageKey}
                          onClick={async () => {
                            const cid = fileInfo?.conversationId;
                            if (!cid) {
                              addMessage('bot', 'Cannot save draft: missing conversation ID.');
                              return;
                            }
                            const draftBody = (draftEdits[messageKey] ?? parsedDraft.body).trim();
                            if (!draftBody) {
                              addMessage('bot', 'Draft cannot be empty.');
                              return;
                            }
                            const normalizedDraft = applyUserSignaturePlaceholders(draftBody);
                            const nextMessageContent = parsedDraft.header
                              ? `${parsedDraft.header}\n\n${normalizedDraft}`
                              : buildDraftMessageContent('Custom', normalizedDraft);
                            setSavingDraftMessageId(messageKey);
                            try {
                              await updateConversationDraft(cid, normalizedDraft);
                              if (message.id) {
                                updateMessageContent(message.id, nextMessageContent, { saveToBackend: true });
                              }
                              setDraftEdits((prev) => ({ ...prev, [messageKey]: normalizedDraft }));
                              setEditingDraftId(null);
                            } catch (err) {
                              addMessage('bot', `Save draft failed: ${err instanceof Error ? err.message : 'Unknown error'}`);
                            } finally {
                              setSavingDraftMessageId(null);
                            }
                          }}
                        >
                          <span>{savingDraftMessageId === messageKey ? 'Saving...' : 'Save draft'}</span>
                        </button>
                        <button
                          type="button"
                          className="message-cancel-draft"
                          disabled={savingDraftMessageId === messageKey}
                          onClick={() => {
                            setDraftEdits((prev) => ({ ...prev, [messageKey]: parsedDraft.body }));
                            setEditingDraftId(null);
                          }}
                        >
                          <span>Cancel</span>
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      className="message-delete-draft"
                      onClick={() => {
                        if (message.id) removeMessage(message.id);
                        if (editingDraftId === messageKey) setEditingDraftId(null);
                        const cid = fileInfo?.conversationId;
                        if (cid != null) deleteConversationDraft(cid).catch(() => {});
                      }}
                      title="Delete draft"
                      aria-label="Delete draft"
                    >
                      <Trash2 size={16} />
                      <span>Delete draft</span>
                    </button>
                  </div>
                )}
                {fileInfo?.duplicateCaseId != null && (
                  <div className="message-case-link">
                    <button
                      type="button"
                      className="message-case-detail-link"
                      onClick={() => setCaseDetailModalId(fileInfo.duplicateCaseId!)}
                    >
                      View case details
                    </button>
                    <button
                      type="button"
                      className="message-case-detail-link reprocess"
                      onClick={() => {
                        const f = reprocessFileRef.current;
                        if (f) handleFileUpload({ file: f });
                      }}
                    >
                      Reprocess
                    </button>
                  </div>
                )}
              </div>
              {message.type === 'user' && (
                <div className="message-avatar">
                  <img src={userIcon} alt="User" className="avatar-image" />
                </div>
              )}
            </div>
          );})}

          {streamingContent !== null && !streamBubbleHiddenRef.current && !shouldShowStreamingSummaryInCard && (streamingMessageIdRef.current === null || displayMessages[displayMessages.length - 1]?.id !== streamingMessageIdRef.current) && (
            <div className="message bot">
              <div className="message-avatar">
                <img src={botIcon} alt="Bot" className="avatar-image" />
              </div>
              <div className="message-content">
                <div className="eval-panels-row">
                  {streamThinkingSteps.length > 0 && (
                    <ThinkingChain steps={streamThinkingSteps} isStreaming={isProcessing} />
                  )}
                  {streamRagEval && <RAGEvalPanel data={streamRagEval} />}
                </div>
                <div className="message-text">
                  {streamingDisplayText}
                  <span className="streaming-cursor">▌</span>
                </div>
              </div>
            </div>
          )}
          
          {showProcessingUI && streamingContent === null && !sessionLoading && (
            <div className="message bot">
              <div className="message-avatar">
                <img src={botIcon} alt="Bot" className="avatar-image" />
              </div>
              <div className="message-content">
                <div className="loading">
                  <div className="confetti-dots">
                    <span></span><span></span><span></span><span></span><span></span>
                  </div>
                  Processing...
                  {createCaseSteps.length > 0 && (
                    <div className="create-case-steps">
                      {createCaseSteps.map((s) => s.replace(/_/g, ' ')).join(' ✓ → ')} ✓
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {extractedData && effectiveCaseId != null && typeof effectiveCaseId === 'number' && !suggestedActionsDismissed && !latestProcessingCard && (
            <div className="message bot">
              <div className="message-avatar">
                <img src={botIcon} alt="Bot" className="avatar-image" />
              </div>
              <div className="message-content">
                <SuggestedQuestions
                  onQuestionClick={(type, skipQuestions) => { void handleReplyTemplateClick(type, skipQuestions ?? false); }}
                  disabled={isLoading}
                  embedded
                  showEndButton={true}
                  onEndDraft={() => { setReplyDraftState(null); setSuggestedActionsDismissed(true); }}
                />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="chat-bottom-area">
          <div className="chat-input">
          <div className="input-container">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isLoading 
                  ? "Processing..." 
                  : selectedFiles.length > 0 && !extractedData
                    ? "Click 'Process Files' to start processing or ask questions..."
                    : extractedData 
                      ? "Ask questions about the case..." 
                      : "Type your message or upload files to get started..."
              }
              disabled={isLoading}
            />
            
            <div className="input-actions">
              <button
                className="action-button upload-button"
                onClick={() => setIsUploadModalOpen(true)}
                disabled={isLoading}
                title={selectedFiles.length > 0 && !extractedData ? `Upload files (${selectedFiles.length} selected)` : 'Upload files'}
              >
                <Upload size={25} />
                {selectedFiles.length > 0 && !extractedData && (
                  <span className="upload-badge">{selectedFiles.length}</span>
                )}
              </button>

              {extractedData && (
                <button
                  className="action-button details-button"
                  onClick={() => setIsFileInfoModalOpen(true)}
                  title="View file details"
                >
                  <FileText size={22} />
                </button>
              )}

              <div className="model-select-wrapper" ref={modelDropdownRef}>
                <button
                  type="button"
                  className="action-button model-button"
                  onClick={() => setModelDropdownOpen((o) => !o)}
                  disabled={isLoading}
                  title={`Language Model: ${chatModel.provider}/${chatModel.model} · Embedding: ${embeddingModel.provider}/${embeddingModel.model}`}
                >
                  <Cpu size={22} />
                </button>
                {modelDropdownOpen && (
                  <div className="model-dropdown model-dropdown-unified">
                    <div className="model-dropdown-block">
                      <span className="model-dropdown-block-title">Language Model</span>
                      <div className="model-dropdown-section">
                        <span className="model-dropdown-label">Provider</span>
                        <button
                          type="button"
                          className={`model-dropdown-item ${chatModel.provider === 'openai' ? 'active' : ''}`}
                          onClick={() => setChatModel('openai', openaiModels.includes(chatModel.model) ? chatModel.model : openaiModels[0])}
                        >
                          OpenAI
                        </button>
                        <button
                          type="button"
                          className={`model-dropdown-item ${chatModel.provider === 'ollama' ? 'active' : ''}`}
                          onClick={() => setChatModel('ollama', ollamaModels.includes(chatModel.model) ? chatModel.model : ollamaModels[0])}
                        >
                          Ollama
                        </button>
                      </div>
                      <div className="model-dropdown-section">
                        <span className="model-dropdown-label">Model</span>
                        {currentModels.map((m) => (
                          <button
                            key={m}
                            type="button"
                            className={`model-dropdown-item ${chatModel.model === m ? 'active' : ''}`}
                            onClick={() => {
                              setChatModel(chatModel.provider, m);
                              setModelDropdownOpen(false);
                            }}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="model-dropdown-block">
                      <span className="model-dropdown-block-title">Embedding</span>
                      <div className="model-dropdown-section">
                        <span className="model-dropdown-label">Provider</span>
                        <button
                          type="button"
                          className={`model-dropdown-item ${embeddingModel.provider === 'openai' ? 'active' : ''}`}
                          onClick={() => setEmbeddingModel('openai', openaiEmbedModels.includes(embeddingModel.model) ? embeddingModel.model : openaiEmbedModels[0])}
                        >
                          OpenAI
                        </button>
                        <button
                          type="button"
                          className={`model-dropdown-item ${embeddingModel.provider === 'ollama' ? 'active' : ''}`}
                          onClick={() => setEmbeddingModel('ollama', ollamaEmbedModels.includes(embeddingModel.model) ? embeddingModel.model : ollamaEmbedModels[0])}
                        >
                          Ollama
                        </button>
                      </div>
                      <div className="model-dropdown-section">
                        <span className="model-dropdown-label">Model</span>
                        {currentEmbedModels.map((m) => (
                          <button
                            key={m}
                            type="button"
                            className={`model-dropdown-item ${embeddingModel.model === m ? 'active' : ''}`}
                            onClick={() => {
                              setEmbeddingModel(embeddingModel.provider, m);
                              setModelDropdownOpen(false);
                            }}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <button
                className="action-button send-button"
                onClick={handleQuery}
                disabled={!inputMessage.trim() || isLoading}
                title="Send message"
              >
                <Send size={25} />
              </button>
            </div>
          </div>
        </div>
        </div>
      </div>

      {/* File Upload Modal */}
      <FileUploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onFilesSelected={handleFileSelection}
        selectedFiles={selectedFiles}
        onRemoveFile={handleRemoveFile}
        onClearAll={handleClearAllFiles}
        onProcessFiles={handleFileUpload}
        isLoading={isLoading}
      />

      {/* File Info Modal */}
      <FileInfoModal
        isOpen={isFileInfoModalOpen}
        onClose={() => setIsFileInfoModalOpen(false)}
        fileInfo={currentFile}
        extractedData={extractedData}
        summaryResult={summaryResult}
      />

      {/* Case Detail Modal (e.g. from "already processed" link) */}
      <CaseDetailModal
        caseId={caseDetailModalId}
        onClose={() => setCaseDetailModalId(null)}
        onLoadForQuery={handleLoadCaseForDraft}
      />
    </div>
  );
};

export default ChatbotInterface;