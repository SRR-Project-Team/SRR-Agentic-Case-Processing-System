// Message types
export interface Message {
  id: string;
  type: 'user' | 'bot';
  content: string;
  timestamp: Date;
  fileInfo?: FileInfo;
}

// File information
export interface FileInfo {
  name: string;
  size: number;
  type: string;
  summary?: FileSummary;  // Added summary field
  case_id?: number;  // Added for linking to processed case
}

// Extracted case data
export interface ExtractedData {
  A_date_received: string;
  B_source: string;
  C_case_number: string;
  D_type: string;
  E_caller_name: string;
  F_contact_no: string;
  G_slope_no: string;
  H_location: string;
  I_nature_of_request: string;
  J_subject_matter: string;
  K_10day_rule_due_date: string;
  L_icc_interim_due: string;
  M_icc_final_due: string;
  N_works_completion_due: string;
  O1_fax_to_contractor: string;
  O2_email_send_time: string;
  P_fax_pages: string;
  Q_case_details: string;
}

// Add summary related types
export interface FileSummary {
  success: boolean;
  summary?: string;
  filename?: string;
  source?: string;
  error?: string;
}

// API response types
export interface ApiResponse {
  filename: string;
  status: 'success' | 'error' | 'duplicate';
  message: string;
  data?: ExtractedData;
  error?: string;
  summary?: FileSummary;  // Added summary field
  raw_content?: string; // raw content of the file
  case_id?: number; // Case ID from database
  similar_cases?: Array<{ case: any; similarity_score: number; is_potential_duplicate?: boolean; data_source?: string }>; // 相似歷史案件
}

// Chat state
export interface ChatState {
  messages: Message[];
  isLoading: boolean;
  extractedData: ExtractedData | null;
  currentFile: FileInfo | null; // metadata
  rawFileContent?: string;
}

// Query types
export interface QueryRequest {
  query: string;
  context?: ExtractedData;
  raw_content?: string;
  provider?: string;
  model?: string;
  session_id?: string;
  embedding_provider?: string;
  embedding_model?: string;
}

// Authentication related interfaces (re-export from api.ts for convenience)
export interface User {
  phone_number: string;
  full_name: string;
  department: string;
  role: string;
  email: string;
}

export interface RegisterRequest {
  phone_number: string;
  password: string;
  full_name: string;
  department?: string;
  role?: string;
  email?: string;
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

// Conversation and Reply Draft types
export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  language: string;
}

export interface ReplyDraftResponse {
  status: string;
  conversation_id: number;
  message: string;
  is_question: boolean;
  draft_reply?: string;
  language: string;
}

export interface Conversation {
  id: number;
  case_id: number;
  conversation_type: string;
  messages: ConversationMessage[];
  language: string;
  draft_reply?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

// RAG Knowledge Base File types
export interface RAGFile {
  id: number;
  filename: string;
  file_type: string;
  file_size: number;
  upload_time: string;
  processed: boolean;
  chunk_count: number;
  processing_error?: string;
}

export interface RAGFileDetails extends RAGFile {
  file_path: string;
  mime_type: string;
  preview_text: string | null;
  metadata: Record<string, any>;
}

export interface FilePreview {
  filename: string;
  file_type: string;
  preview_content: string;
  total_length: number;
}

export interface RAGFileUploadResponse {
  status: string;
  message: string;
  data: RAGFile;
}

/** Agent-style task state for create_case flow. */
export interface TaskState {
  task_id?: string;
  task_type?: string;
  source_type?: string;
  fields: Record<string, unknown>;
  missing_fields?: string[];
  steps_done?: string[];
  steps_todo?: string[];
  quality_score?: number;
  validation_errors?: string[];
  summary?: string;
  similar_cases?: Array<{ case: unknown; similarity_score: number; is_potential_duplicate?: boolean }>;
  department_routing?: Record<string, unknown>;
}