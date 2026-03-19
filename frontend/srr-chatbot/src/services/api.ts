import axios from 'axios';
import { QueryRequest, RAGFile, RAGFileDetails, FilePreview, RAGFileUploadResponse } from '../types';

// Authentication related types
export interface User {
  phone_number: string;
  full_name: string;
  department: string;
  role: string;
  email: string;
}

export interface LoginRequest {
  phone_number: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface RegisterRequest {
  phone_number: string;
  password: string;
  full_name: string;
  department?: string;
  role?: string;
  email?: string;
}

export interface ChatMessageRequest {
  session_id: string;
  message_type: string;
  content: string;
  case_id?: number;
  file_info?: any;
}

export interface ChatMessage {
  id: number;
  user_phone: string;
  session_id: string;
  message_type: string;
  content: string;
  case_id?: number;
  file_info?: any;
  created_at: string;
}

export interface Session {
  session_id: string;
  message_count: number;
  last_message_time: string;
}

// Batch processing response type
export interface BatchProcessingResponse {
  total_files: number;
  successful: number;
  failed: number;
  skipped: number;  // 添加此字段
  results: Array<{
    case_id: string;
    main_file: string;
    email_file?: string | null;
    status: 'success' | 'error' | 'skipped';  // 添加 'skipped'
    message: string;
    structured_data?: any;  // 仅在 success 时存在
  }>;
}

// API base configuration
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8001';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 120 seconds timeout (2 minutes) - reserved for RCC OCR processing
});

// Stage 1 of token hardening: centralize token-clearing behavior.
// Stage 2 (planned): migrate to HttpOnly secure cookies and remove localStorage token usage.
const clearAuthState = () => {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  window.dispatchEvent(new Event('auth:unauthorized'));
};

// Request interceptor: automatically add token to headers
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor: handle 401 unauthorized errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearAuthState();
    }
    return Promise.reject(error);
  }
);

export interface ProcessFileStreamCallbacks {
  onExtracted?: (data: { structured_data: any; case_id: number | null; raw_content?: string }) => void;
  onSummaryChunk?: (text: string) => void;
  onSummaryFull?: (summary: string, success: boolean) => void;
  onSimilarCases?: (similar_cases: any[]) => void;
  onDone?: (result: { filename: string; case_id: number | null }) => void;
  onDuplicate?: (data: { filename: string; message: string; structured_data: any; case_id: number }) => void;
  onError?: (message: string) => void;
}

export interface CreateCaseCallbacks extends ProcessFileStreamCallbacks {
  onStepsDone?: (steps: string[]) => void;
}

export type UploadPrecheckResult = 'NOT_FOUND' | 'FOUND_SAME_HASH' | 'FOUND_SAME_NAME_DIFF_HASH';

export interface CaseUploadPrecheckData {
  result: UploadPrecheckResult;
  visible_to_user: boolean;
  existing_case_id: number | null;
  existing_filename: string | null;
  existing_case_number: string | null;
  uploaded_by: string | null;
  existing_created_at: string | null;
  message: string;
}

export interface KbUploadPrecheckData {
  result: UploadPrecheckResult;
  visible_to_user: boolean;
  existing_file_id: number | null;
  existing_filename: string | null;
  existing_category: string | null;
  uploaded_by: string | null;
  existing_upload_time: string | null;
  message: string;
}

export interface UserFeedbackRequest {
  case_id?: number | null;
  field_name: string;
  incorrect_value?: string;
  correct_value: string;
  note?: string;
  source_text?: string;
  scope?: 'global' | 'case';
}

const API_BASE_URL_EXPORT = process.env.REACT_APP_API_URL || 'http://localhost:8001';

const attachAuthHeader = (headers: Record<string, string> = {}): Record<string, string> => {
  const token = localStorage.getItem('token');
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
};

const fetchWithAuth = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
  const headers: Record<string, string> = attachAuthHeader((init.headers as Record<string, string>) || {});
  const response = await fetch(input, { ...init, headers });
  if (response.status === 401) {
    clearAuthState();
  }
  return response;
};

const toHex = (buffer: ArrayBuffer): string =>
  Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

export const calculateFileSha256 = async (file: File): Promise<string> => {
  const arrayBuffer = await file.arrayBuffer();
  const digest = await crypto.subtle.digest('SHA-256', arrayBuffer);
  return toHex(digest);
};

export const precheckCaseUpload = async (
  file: File,
  fileHash: string
): Promise<CaseUploadPrecheckData> => {
  const response = await apiClient.post<{ status: string; data: CaseUploadPrecheckData }>(
    '/api/cases/precheck-upload',
    {
      filename: file.name,
      file_hash: fileHash
    }
  );
  return response.data.data;
};

export const precheckKnowledgeBaseUpload = async (
  file: File,
  fileHash: string
): Promise<KbUploadPrecheckData> => {
  const response = await apiClient.post<{ status: string; data: KbUploadPrecheckData }>(
    '/api/knowledge-base/precheck-upload',
    {
      filename: file.name,
      file_hash: fileHash,
      file_size: file.size
    }
  );
  return response.data.data;
};

export const processFileStream = async (
  file: File,
  options?: { forceReprocess?: boolean; embedding_provider?: string; embedding_model?: string },
  callbacks?: ProcessFileStreamCallbacks
): Promise<void> => {
  const formData = new FormData();
  formData.append('file', file);
  if (options?.forceReprocess) {
    formData.append('force_reprocess', 'true');
  }
  if (options?.embedding_provider) {
    formData.append('embedding_provider', options.embedding_provider);
  }
  if (options?.embedding_model) {
    formData.append('embedding_model', options.embedding_model);
  }
  const res = await fetchWithAuth(`${API_BASE_URL_EXPORT}/api/process-srr-file`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    callbacks?.onError?.(text || `Request failed: ${res.status}`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks?.onError?.('No response body');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';

  const parseLine = (line: string): void => {
    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7).trim();
      return;
    }
    if (line.startsWith('data: ')) {
      const payload = line.slice(6);
      try {
        const data = JSON.parse(payload);
        switch (currentEvent) {
          case 'duplicate':
            callbacks?.onDuplicate?.({
              filename: data.filename,
              message: data.message,
              structured_data: data.structured_data,
              case_id: data.case_id,
            });
            break;
          case 'extracted':
            callbacks?.onExtracted?.({
              structured_data: data.structured_data,
              case_id: data.case_id ?? null,
              raw_content: data.raw_content,
            });
            break;
          case 'summary':
            if (data.summary != null) callbacks?.onSummaryFull?.(data.summary, data.success !== false);
            break;
          case 'summary_chunk':
            if (typeof data.text === 'string') callbacks?.onSummaryChunk?.(data.text);
            break;
          case 'summary_end':
            if (data.summary != null) callbacks?.onSummaryFull?.(data.summary, data.success !== false);
            else if (data.error) callbacks?.onSummaryFull?.('', false);
            break;
          case 'similar_cases':
            callbacks?.onSimilarCases?.(data.similar_cases ?? []);
            break;
          case 'done':
            callbacks?.onDone?.({ filename: data.filename, case_id: data.case_id ?? null });
            break;
          case 'error':
            callbacks?.onError?.(data.error ?? 'Unknown error');
            break;
          default:
            break;
        }
      } catch {
        // ignore parse errors for non-JSON lines
      }
      currentEvent = '';
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      parseLine(line);
    }
  }
  if (buffer) {
    for (const line of buffer.split('\n')) {
      parseLine(line);
    }
  }
};

/** Agent-style create case stream (POST /api/cases/create). */
export const createCase = async (
  file: File,
  options?: { forceReprocess?: boolean; embedding_provider?: string; embedding_model?: string },
  callbacks?: CreateCaseCallbacks
): Promise<void> => {
  const formData = new FormData();
  formData.append('file', file);
  if (options?.forceReprocess) {
    formData.append('force_reprocess', 'true');
  }
  if (options?.embedding_provider) {
    formData.append('embedding_provider', options.embedding_provider);
  }
  if (options?.embedding_model) {
    formData.append('embedding_model', options.embedding_model);
  }
  const res = await fetchWithAuth(`${API_BASE_URL_EXPORT}/api/cases/create`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    callbacks?.onError?.(text || `Request failed: ${res.status}`);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks?.onError?.('No response body');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';

  const parseLine = (line: string): void => {
    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7).trim();
      return;
    }
    if (line.startsWith('data: ')) {
      const payload = line.slice(6);
      try {
        const data = JSON.parse(payload);
        switch (currentEvent) {
          case 'duplicate':
            callbacks?.onDuplicate?.({
              filename: data.filename,
              message: data.message ?? 'File already processed',
              structured_data: data.fields ?? data.structured_data,
              case_id: data.case_id,
            });
            if (data.steps_done) callbacks?.onStepsDone?.(data.steps_done);
            break;
          case 'extracted':
            callbacks?.onExtracted?.({
              structured_data: data.fields ?? data.structured_data,
              case_id: data.case_id ?? null,
              raw_content: data.raw_content,
            });
            if (data.steps_done) callbacks?.onStepsDone?.(data.steps_done);
            break;
          case 'external_data':
          case 'department_routing':
            if (data.steps_done) callbacks?.onStepsDone?.(data.steps_done);
            break;
          case 'summary':
            if (data.summary != null) callbacks?.onSummaryFull?.(data.summary, data.success !== false);
            break;
          case 'summary_chunk':
            if (typeof data.text === 'string') callbacks?.onSummaryChunk?.(data.text);
            break;
          case 'summary_end':
            if (data.summary != null) callbacks?.onSummaryFull?.(data.summary, data.success !== false);
            else if (data.error) callbacks?.onSummaryFull?.('', false);
            break;
          case 'similar_cases':
            callbacks?.onSimilarCases?.(data.similar_cases ?? []);
            break;
          case 'done':
            if (data.steps_done) callbacks?.onStepsDone?.(data.steps_done);
            callbacks?.onDone?.({
              filename: data.filename,
              case_id: data.case_id ?? null,
            });
            break;
          case 'error':
            callbacks?.onError?.(data.error ?? 'Unknown error');
            break;
          default:
            break;
        }
      } catch {
        // ignore parse errors for non-JSON lines
      }
      currentEvent = '';
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      parseLine(line);
    }
  }
  if (buffer) {
    for (const line of buffer.split('\n')) {
      parseLine(line);
    }
  }
};

/** Create case from folder (multiple files or ZIP). Supports location maps, site photos, ZIP. */
export interface CreateCaseFromFolderResponse {
  status: 'success' | 'duplicate';
  case_id: number;
  fields?: Record<string, string>;
  summary?: string;
  similar_cases?: any[];
  manifest?: { total_files: number; processed: number; skipped: number; from_zip?: string[] };
  message?: string;
}

export const createCaseFromFolder = async (files: File[]): Promise<CreateCaseFromFolderResponse> => {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const res = await fetchWithAuth(`${API_BASE_URL_EXPORT}/api/cases/create-from-folder`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.message || err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
};

// Multi-file batch processing API (SSE stream)
export interface ProcessMultipleFilesStreamCallbacks {
  onFileResult?: (result: BatchProcessingResponse['results'][0]) => void;
  onBatchDone?: (summary: { total_files: number; successful: number; failed: number; skipped: number }) => void;
  onError?: (message: string) => void;
}

export const processMultipleFilesStream = async (
  files: File[],
  callbacks?: ProcessMultipleFilesStreamCallbacks
): Promise<BatchProcessingResponse> => {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  const res = await fetchWithAuth(`${API_BASE_URL_EXPORT}/api/process-multiple-files/stream`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    const msg = text || `Request failed: ${res.status}`;
    callbacks?.onError?.(msg);
    throw new Error(msg);
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks?.onError?.('No response body');
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';
  const results: BatchProcessingResponse['results'] = [];
  let batchDone: BatchProcessingResponse | null = null;
  let streamError: string | null = null;

  const parseLine = (line: string): void => {
    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7).trim();
      return;
    }
    if (line.startsWith('data: ')) {
      const payload = line.slice(6);
      try {
        const data = JSON.parse(payload);
        if (currentEvent === 'file_result') {
          results.push(data);
          callbacks?.onFileResult?.(data);
        } else if (currentEvent === 'batch_done') {
          batchDone = {
            total_files: data.total_files ?? 0,
            successful: data.successful ?? 0,
            failed: data.failed ?? 0,
            skipped: data.skipped ?? 0,
            results: data.results ?? results,
          };
          callbacks?.onBatchDone?.({
            total_files: batchDone.total_files,
            successful: batchDone.successful,
            failed: batchDone.failed,
            skipped: batchDone.skipped,
          });
        } else if (currentEvent === 'error') {
          streamError = data.error ?? 'Unknown error';
          callbacks?.onError?.(data.error ?? 'Unknown error');
        }
      } catch (_) {
        // ignore JSON parse errors for non-event lines
      }
      currentEvent = '';
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) parseLine(line);
  }
  if (buffer) {
    for (const line of buffer.split('\n')) parseLine(line);
  }

  if (streamError) throw new Error(streamError);
  if (batchDone) return batchDone;
  return {
    total_files: files.length,
    successful: results.filter((r) => r.status === 'success').length,
    failed: results.filter((r) => r.status === 'error').length,
    skipped: results.filter((r) => r.status === 'skipped').length,
    results,
  };
};

// Legacy non-streaming batch (uses stream under the hood, for compatibility)
export const processMultipleFiles = async (files: File[]): Promise<BatchProcessingResponse> => {
  try {
    return await processMultipleFilesStream(files);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Batch file processing failed');
    }
    throw new Error(error instanceof Error ? error.message : 'Network connection failed');
  }
};

export interface LlmModelsResponse {
  openai: string[];
  ollama: string[];
}

export const getLlmModels = async (): Promise<LlmModelsResponse> => {
  const res = await fetchWithAuth(`${API_BASE_URL}/api/llm-models`);
  if (!res.ok) throw new Error(`Failed to fetch LLM models: ${res.status}`);
  return res.json();
};

export interface EmbeddingConfigResponse {
  provider: string;
  model: string;
  openai: string[];
  ollama: string[];
}

export const getEmbeddingConfig = async (): Promise<EmbeddingConfigResponse> => {
  const res = await fetchWithAuth(`${API_BASE_URL}/api/embedding-config`);
  if (!res.ok) throw new Error(`Failed to fetch embedding config: ${res.status}`);
  return res.json();
};

// Health check API
export const healthCheck = async (): Promise<{ status: string; message: string }> => {
  try {
    const response = await apiClient.get('/health');
    return response.data;
  } catch (error) {
    throw new Error('API service unavailable');
  }
};

/**
 * Stream chat response via SSE. Calls onChunk for each text chunk, returns full text.
 */
export interface ThinkingStepEvent {
  step_id: number;
  title: string;
  content: string;
  step_type: 'intent' | 'decompose' | 'retrieve' | 'synthesize' | 'evaluate';
  duration_ms?: number;
  metadata?: Record<string, unknown>;
}

export interface RetrievalMetric {
  source: string;
  doc_id: string;
  doc_title?: string;
  similarity_score: number;
  relevance_score: number;
  used_in_answer?: boolean;
  snippet?: string;
}

export interface RAGEvalData {
  retrieval_metrics?: RetrievalMetric[];
  context_relevance?: number;
  answer_faithfulness?: number;
  answer_coverage?: number;
  faithfulness_matched?: string[];
  faithfulness_total?: number;
  coverage_matched?: string[];
  coverage_missed?: string[];
  retrieval_latency_ms?: number;
  generation_latency_ms?: number;
  total_latency_ms?: number;
  total_docs_retrieved?: number;
  total_docs_used?: number;
  quality_score?: number;
}

export interface QueryStreamCallbacks {
  onTextChunk?: (text: string) => void;
  onThinkingStep?: (step: ThinkingStepEvent) => void;
  onRagEval?: (phase: 'retrieval' | 'answer', data: RAGEvalData) => void;
  onDone?: (fullText: string) => void;
}

export const queryCaseStream = async (
  request: QueryRequest,
  handlers?: ((text: string) => void) | QueryStreamCallbacks
): Promise<string> => {
  const { query, context, raw_content, provider, model, session_id, embedding_provider, embedding_model } = request;
  const callbackObj: QueryStreamCallbacks =
    typeof handlers === 'function' ? { onTextChunk: handlers } : (handlers ?? {});
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  attachAuthHeader(headers);

  const body: Record<string, unknown> = {
    query,
    context: context || {},
    raw_content: raw_content || '',
  };
  if (provider != null) body.provider = provider;
  if (model != null) body.model = model;
  if (session_id != null) body.session_id = session_id;
  if (embedding_provider != null) body.embedding_provider = embedding_provider;
  if (embedding_model != null) body.embedding_model = embedding_model;

  const res = await fetchWithAuth(`${API_BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errBody = await res.text();
    throw new Error(errBody || `Request failed: ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const payload = line.slice(6);
        if (payload === '[DONE]') continue;
        try {
          const data = JSON.parse(payload);
          if (data.error) throw new Error(data.error);
          if (data.type === 'thinking_step' && data.step) {
            callbackObj.onThinkingStep?.(data.step as ThinkingStepEvent);
            continue;
          }
          if (data.type === 'rag_eval') {
            const phase = data.phase === 'answer' ? 'answer' : 'retrieval';
            callbackObj.onRagEval?.(phase, (data.data ?? {}) as RAGEvalData);
            continue;
          }
          if (typeof data.text === 'string') {
            fullText += data.text;
            callbackObj.onTextChunk?.(data.text);
          }
        } catch (e) {
          if (e instanceof Error && e.message !== 'Unexpected end of JSON input') throw e;
        }
      }
    }
  }
  if (buffer.startsWith('data: ')) {
    try {
      const data = JSON.parse(buffer.slice(6));
      if (data.error) throw new Error(data.error);
      if (data.type === 'thinking_step' && data.step) {
        callbackObj.onThinkingStep?.(data.step as ThinkingStepEvent);
      } else if (data.type === 'rag_eval') {
        const phase = data.phase === 'answer' ? 'answer' : 'retrieval';
        callbackObj.onRagEval?.(phase, (data.data ?? {}) as RAGEvalData);
      } else if (typeof data.text === 'string') {
        fullText += data.text;
        callbackObj.onTextChunk?.(data.text);
      }
    } catch {
      /* ignore trailing parse */
    }
  }
  callbackObj.onDone?.(fullText);
  return fullText;
};

// Find similar cases API
export const findSimilarCases = async (caseData: any, limit: number = 10, minSimilarity: number = 0.3): Promise<any> => {
  try {
    const response = await axios.post(`${API_BASE_URL}/api/find-similar-cases`, {
      ...caseData,
      limit,
      min_similarity: minSimilarity
    }, {
      timeout: 30000 // 30 seconds timeout
    });
    
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to find similar cases');
    }
    throw new Error('Network connection failed');
  }
};

// Get case statistics API
export const getCaseStatistics = async (filters: {
  location?: string;
  slope_no?: string;
  caller_name?: string;
}): Promise<any> => {
  try {
    const params = new URLSearchParams();
    if (filters.location) params.append('location', filters.location);
    if (filters.slope_no) params.append('slope_no', filters.slope_no);
    if (filters.caller_name) params.append('caller_name', filters.caller_name);
    
    const response = await axios.get(`${API_BASE_URL}/api/case-statistics?${params.toString()}`, {
      timeout: 30000
    });
    
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to get statistics');
    }
    throw new Error('Network connection failed');
  }
};

// Reply draft generation API
export const generateReplyDraft = async (request: {
  case_id: number;
  reply_type: string;
  conversation_id?: number;
  user_message?: string;
  is_initial: boolean;
  skip_questions?: boolean;
}): Promise<{
  status: string;
  conversation_id: number;
  message: string;
  is_question: boolean;
  draft_reply?: string;
  language: string;
  reply_slip_selections?: { ACK?: string[]; INT?: string[]; SUB?: string[] };
  deadline?: string;
}> => {
  try {
    const response = await apiClient.post('/api/generate-reply-draft', request, {
      timeout: 60000 // 60 seconds for LLM processing
    });
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to generate reply draft');
    }
    throw new Error('Network connection failed');
  }
};

/** Stream reply draft generation via SSE. Use when skip_questions=true or generating from user answer. */
export const generateReplyDraftStream = async (
  request: {
    case_id: number;
    reply_type: string;
    conversation_id?: number;
    user_message?: string;
    is_initial: boolean;
    skip_questions?: boolean;
  },
  onChunk: (text: string) => void
): Promise<{ conversation_id: number; fullText: string }> => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  attachAuthHeader(headers);
  const res = await fetchWithAuth(`${API_BASE_URL}/api/generate-reply-draft/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const errBody = await res.text();
    throw new Error(errBody || `Request failed: ${res.status}`);
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');
  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';
  let conversationId = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const payload = line.slice(6);
      try {
        const data = JSON.parse(payload);
        if (data.type === 'meta' && data.conversation_id != null) conversationId = data.conversation_id;
        else if (data.type === 'text' && typeof data.text === 'string') {
          fullText += data.text;
          onChunk(data.text);
        } else if (data.type === 'error') throw new Error(data.error || 'Stream error');
        else if (data.type === 'done' && data.conversation_id != null) conversationId = data.conversation_id;
      } catch (e) {
        if (e instanceof Error && e.message !== 'Unexpected end of JSON input') throw e;
      }
    }
  }
  if (buffer.startsWith('data: ')) {
    try {
      const data = JSON.parse(buffer.slice(6));
      if (data.type === 'text' && typeof data.text === 'string') {
        fullText += data.text;
        onChunk(data.text);
      } else if (data.type === 'error') throw new Error(data.error || 'Stream error');
    } catch {
      /* ignore */
    }
  }
  return { conversation_id: conversationId, fullText };
};

// Get conversation history API
export const getConversation = async (conversationId: number): Promise<{
  status: string;
  conversation: any;
}> => {
  try {
    const response = await apiClient.get(`/api/conversation/${conversationId}`);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to get conversation');
    }
    throw new Error('Network connection failed');
  }
};

// Delete draft reply for a conversation (clears draft_reply on server)
export const deleteConversationDraft = async (conversationId: number): Promise<void> => {
  try {
    await apiClient.delete(`/api/conversation/${conversationId}/draft`);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to delete draft');
    }
    throw new Error('Network connection failed');
  }
};

export const saveUserFeedback = async (request: UserFeedbackRequest): Promise<{ status: string; feedback: any }> => {
  try {
    const response = await apiClient.post('/api/user-feedback', request);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to save user feedback');
    }
    throw new Error('Network connection failed');
  }
};

// Save draft reply for a conversation
export const updateConversationDraft = async (
  conversationId: number,
  draftReply: string
): Promise<void> => {
  try {
    await apiClient.put(`/api/conversation/${conversationId}/draft`, {
      draft_reply: draftReply,
    });
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to save draft');
    }
    throw new Error('Network connection failed');
  }
};

// Approve draft reply as knowledge base source for RAG retrieval
export const approveDraftToKB = async (conversationId: number): Promise<{ already_approved?: boolean }> => {
  const response = await apiClient.post<{ status: string; message?: string; data?: { already_approved?: boolean } }>(
    `/api/conversation/${conversationId}/approve-draft-to-kb`
  );
  return response.data?.data ?? {};
};

// List knowledge docs (e.g. reply templates) awaiting approval for RAG retrieval
export const getPendingKBApprovals = async (): Promise<
  Array<{ id: number; doc_type: string; filename: string; content_preview: string; create_time?: string }>
> => {
  const response = await apiClient.get<{ status: string; data: unknown[] }>('/api/knowledge-base/pending-approval');
  return (response.data?.data ?? []) as Array<{ id: number; doc_type: string; filename: string; content_preview: string; create_time?: string }>;
};

// Approve a knowledge doc so it becomes available for RAG retrieval
export const approveKnowledgeDoc = async (docType: string, filename: string): Promise<void> => {
  await apiClient.post('/api/knowledge-base/approve', { doc_type: docType, filename });
};

// ============== RAG Knowledge Base File Management APIs ==============

// Upload RAG file
export const uploadRAGFile = async (
  file: File,
  onProgress?: (progress: number) => void,
  embeddingProvider?: string,
  embeddingModel?: string,
): Promise<RAGFile> => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    if (embeddingProvider) formData.append('embedding_provider', embeddingProvider);
    if (embeddingModel) formData.append('embedding_model', embeddingModel);

    const response = await apiClient.post<RAGFileUploadResponse>('/api/rag-files/upload', formData, {
      timeout: 60000, // 60s enough (processing is background; 202 returns quickly)
      validateStatus: (status) => (status >= 200 && status < 300) || status === 202,
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(progress);
        }
      }
    });

    // 200 or 202: success (202 = accepted, processing in background)
    return response.data.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'File upload failed');
    }
    throw new Error('Network connection failed');
  }
};

const uploadKnowledgeBaseFile = async (
  endpoint: '/api/knowledge-base/slope-data/upload' | '/api/knowledge-base/tree-inventory/upload',
  file: File,
  onProgress?: (progress: number) => void
): Promise<RAGFile> => {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<RAGFileUploadResponse>(endpoint, formData, {
      timeout: 60000,
      validateStatus: (status) => (status >= 200 && status < 300) || status === 202,
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(progress);
        }
      }
    });

    return response.data.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'File upload failed');
    }
    throw new Error('Network connection failed');
  }
};

export const uploadSlopeDataFile = async (
  file: File,
  onProgress?: (progress: number) => void
): Promise<RAGFile> => uploadKnowledgeBaseFile('/api/knowledge-base/slope-data/upload', file, onProgress);

export const uploadTreeInventoryFile = async (
  file: File,
  onProgress?: (progress: number) => void
): Promise<RAGFile> => uploadKnowledgeBaseFile('/api/knowledge-base/tree-inventory/upload', file, onProgress);

export type TemplateSlotType = 'interim' | 'final' | 'wrong_referral';

export interface TemplateSlotStatus {
  filename: string | null;
  upload_time: string | null;
  file_id: number | null;
}

export interface TemplateSlotsResponse {
  interim: TemplateSlotStatus | null;
  final: TemplateSlotStatus | null;
  wrong_referral: TemplateSlotStatus | null;
}

export const uploadTemplateFile = async (
  file: File,
  replyType: TemplateSlotType,
  onProgress?: (progress: number) => void
): Promise<RAGFile> => {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<RAGFileUploadResponse>(
      `/api/knowledge-base/template/upload?reply_type=${replyType}`,
      formData,
      {
        timeout: 60000,
        validateStatus: (status) => (status >= 200 && status < 300) || status === 202,
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total && onProgress) {
            const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            onProgress(progress);
          }
        }
      }
    );

    return response.data.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Template upload failed');
    }
    throw new Error('Network connection failed');
  }
};

export const getTemplateSlots = async (): Promise<TemplateSlotsResponse> => {
  try {
    const response = await apiClient.get<{ status: string; data: TemplateSlotsResponse }>(
      '/api/knowledge-base/templates'
    );
    return response.data.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to get template slots');
    }
    throw new Error('Network connection failed');
  }
};

// Get all RAG files
export const getRAGFiles = async (): Promise<RAGFile[]> => {
  try {
    const response = await apiClient.get<{ status: string; data: RAGFile[] }>('/api/rag-files');
    return response.data.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to get files');
    }
    throw new Error('Network connection failed');
  }
};

// Get RAG file details
export const getRAGFileDetails = async (fileId: number): Promise<RAGFileDetails> => {
  try {
    const response = await apiClient.get<{ status: string; data: RAGFileDetails }>(
      `/api/rag-files/${fileId}`
    );
    return response.data.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to get file details');
    }
    throw new Error('Network connection failed');
  }
};

// Download RAG file
export const downloadRAGFile = async (fileId: number, filename: string): Promise<void> => {
  try {
    const response = await apiClient.get(`/api/rag-files/${fileId}/download`, {
      responseType: 'blob'
    });

    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error('File download failed');
    }
    throw new Error('Network connection failed');
  }
};

// Get RAG file as blob (for in-app preview)
export const getRAGFileBlob = async (fileId: number): Promise<Blob> => {
  try {
    const response = await apiClient.get(`/api/rag-files/${fileId}/download`, {
      responseType: 'blob'
    });
    return response.data as Blob;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error('Failed to load file blob');
    }
    throw new Error('Network connection failed');
  }
};

// Get Office file converted to PDF blob (for in-app preview)
export const getRAGFilePreviewPdf = async (fileId: number): Promise<Blob> => {
  const response = await apiClient.get(`/api/rag-files/${fileId}/preview-pdf`, {
    responseType: 'blob',
    timeout: 120000,
    validateStatus: (status) => status >= 200 && status < 300,
  });
  return response.data as Blob;
};

// Delete RAG file
export const deleteRAGFile = async (fileId: number): Promise<void> => {
  try {
    await apiClient.delete(`/api/rag-files/${fileId}`);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to delete file');
    }
    throw new Error('Network connection failed');
  }
};

// Get RAG file preview (optional: full content or paginated via offset/limit)
export const getRAGFilePreview = async (
  fileId: number,
  options?: { full?: boolean; offset?: number; limit?: number }
): Promise<FilePreview> => {
  try {
    const params = new URLSearchParams();
    if (options?.full) params.set('full', 'true');
    if (options?.offset != null) params.set('offset', String(options.offset));
    if (options?.limit != null) params.set('limit', String(options.limit));
    const query = params.toString();
    const url = query ? `/api/rag-files/${fileId}/preview?${query}` : `/api/rag-files/${fileId}/preview`;
    const response = await apiClient.get<{ status: string; data: FilePreview }>(url);
    return response.data.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to get file preview');
    }
    throw new Error('Network connection failed');
  }
};

// Get all cases (for CaseFilesPanel)
export const getCases = async (limit: number = 100, offset: number = 0): Promise<any[]> => {
  try {
    const response = await apiClient.get(`/api/cases?limit=${limit}&offset=${offset}`);
    return response.data.cases || [];
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to get cases');
    }
    throw new Error('Network connection failed');
  }
};

// Get single case by ID (full extracted data for query / draft)
export const getCase = async (caseId: number): Promise<any> => {
  try {
    const response = await apiClient.get(`/api/cases/${caseId}`);
    if (response.data?.error) {
      throw new Error(response.data.error);
    }
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to get case');
    }
    throw new Error('Network connection failed');
  }
};

// Get case details (basic info, processing, conversations, attachments)
export const getCaseDetails = async (caseId: number): Promise<{
  case: any;
  conversations: any[];
  attachments: { name: string; type: string; note: string }[];
}> => {
  try {
    const response = await apiClient.get(`/api/cases/${caseId}/details`);
    if (response.data?.error) {
      throw new Error(response.data.error);
    }
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to get case details');
    }
    throw new Error('Network connection failed');
  }
};

// ============== Authentication APIs ==============

/**
 * User login
 */
export const login = async (phone: string, password: string): Promise<LoginResponse> => {
  try {
    const formData = new FormData();
    formData.append('username', phone);
    formData.append('password', password);

    const response = await apiClient.post('/api/auth/login', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 20000, // 20s so UI does not hang when backend is down
    });
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const msg = error.code === 'ECONNABORTED'
        ? 'Connection timed out. Is the backend running?'
        : (error.response?.data?.detail || error.message || 'Login failed');
      throw new Error(msg);
    }
    throw new Error('Network connection failed');
  }
};

/**
 * User registration
 */
export const register = async (userData: RegisterRequest): Promise<User> => {
  try {
    const response = await apiClient.post('/api/auth/register', userData);
    return response.data.user;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Registration failed');
    }
    throw new Error('Network connection failed');
  }
};

/**
 * Get current user info
 */
export const getCurrentUser = async (): Promise<User> => {
  try {
    const response = await apiClient.get('/api/auth/me');
    return response.data.user;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.detail || error.message || 'Failed to get user info');
    }
    throw new Error('Network connection failed');
  }
};

/**
 * User logout
 */
export const logout = async (): Promise<void> => {
  try {
    await apiClient.post('/api/auth/logout');
  } catch (error) {
    // Logout errors are not critical, just log them
    console.error('Logout API call failed:', error);
  }
};

// ============== Chat History APIs ==============

/**
 * Get chat history
 */
export const getChatHistory = async (sessionId?: string, limit: number = 100): Promise<ChatMessage[]> => {
  try {
    const params: any = { limit };
    if (sessionId) {
      params.session_id = sessionId;
    }

    const response = await apiClient.get('/api/chat-history', {
      params,
      timeout: 15000, // prevent UI loading state from hanging too long
    });
    return response.data.messages || [];
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (error.code === 'ECONNABORTED') {
        throw new Error('Load chat history timed out. Please check backend service.');
      }
      throw new Error(error.response?.data?.message || error.message || 'Failed to get chat history');
    }
    throw new Error('Network connection failed');
  }
};

/**
 * Create new session
 */
export const createSession = async (title?: string): Promise<any> => {
  try {
    const response = await apiClient.post('/api/chat-sessions', { title });
    return response.data.session;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to create session');
    }
    throw new Error('Network connection failed');
  }
};

/**
 * Delete session
 */
export const deleteSession = async (sessionId: string): Promise<void> => {
  try {
    await apiClient.delete(`/api/chat-sessions/${sessionId}`);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to delete session');
    }
    throw new Error('Network connection failed');
  }
};

/**
 * Save chat message
 */
export const saveChatMessage = async (message: ChatMessageRequest): Promise<number> => {
  try {
    const response = await apiClient.post('/api/chat-history', message);
    return response.data.message_id;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to save chat message');
    }
    throw new Error('Network connection failed');
  }
};

/**
 * Get user sessions
 */
export const getUserSessions = async (): Promise<Session[]> => {
  try {
    const response = await apiClient.get('/api/chat-sessions', {
      timeout: 15000, // prevent sidebar conversation loading from hanging indefinitely
    });
    return response.data.sessions || [];
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (error.code === 'ECONNABORTED') {
        throw new Error('Load sessions timed out. Please check backend service.');
      }
      throw new Error(error.response?.data?.message || error.message || 'Failed to get sessions');
    }
    throw new Error('Network connection failed');
  }
};

/**
 * Delete a chat session (removes all messages in that session for current user)
 */
export const deleteChatSession = async (sessionId: string): Promise<void> => {
  try {
    await apiClient.delete(`/api/chat-sessions/${encodeURIComponent(sessionId)}`);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(error.response?.data?.message || error.message || 'Failed to delete session');
    }
    throw new Error('Network connection failed');
  }
};

const apiService = {
  processFileStream,
  createCase,
  processMultipleFiles,
  calculateFileSha256,
  precheckCaseUpload,
  precheckKnowledgeBaseUpload,
  healthCheck,
  findSimilarCases,
  getCaseStatistics,
  generateReplyDraft,
  updateConversationDraft,
  getConversation,
  uploadRAGFile,
  uploadSlopeDataFile,
  uploadTreeInventoryFile,
  getRAGFiles,
  getRAGFileDetails,
  downloadRAGFile,
  getRAGFileBlob,
  getRAGFilePreviewPdf,
  deleteRAGFile,
  getRAGFilePreview,
  getCases,
  login,
  register,
  getCurrentUser,
  logout,
  getChatHistory,
  saveChatMessage,
  getUserSessions,
  deleteChatSession,
};

export default apiService;