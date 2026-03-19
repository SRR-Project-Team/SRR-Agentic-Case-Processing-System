import React, { useState, useEffect, useRef } from 'react';
import './KnowledgeBasePanel.css';
import {
  getRAGFiles,
  deleteRAGFile,
  downloadRAGFile,
  getPendingKBApprovals,
  approveKnowledgeDoc,
  getTemplateSlots,
  uploadTemplateFile,
  type TemplateSlotType,
  type TemplateSlotsResponse
} from '../services/api';
import { RAGFile } from '../types/index';
import KBFileUploadModal from './KBFileUploadModal';
import KBFilePreviewModal from './KBFilePreviewModal';
import GradientButton from './GradientButton';

interface KnowledgeBasePanelProps {
  searchQuery?: string;
}

const KnowledgeBasePanel: React.FC<KnowledgeBasePanelProps> = ({ searchQuery = '' }) => {
  const [files, setFiles] = useState<RAGFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<Array<{ id: number; doc_type: string; filename: string; content_preview: string }>>([]);
  const [approvingDoc, setApprovingDoc] = useState<string | null>(null);
  const [templateSlots, setTemplateSlots] = useState<TemplateSlotsResponse | null>(null);
  const [templateUploading, setTemplateUploading] = useState<TemplateSlotType | null>(null);
  const templateFileInputRefs = useRef<{ [K in TemplateSlotType]: HTMLInputElement | null }>({
    interim: null,
    final: null,
    wrong_referral: null
  });

  const loadTemplateSlots = async () => {
    try {
      const data = await getTemplateSlots();
      setTemplateSlots(data);
    } catch {
      setTemplateSlots(null);
    }
  };

  const loadPendingApprovals = async () => {
    try {
      const items = await getPendingKBApprovals();
      setPendingApprovals(items);
    } catch {
      setPendingApprovals([]);
    }
  };

  const loadFiles = async () => {
    try {
      setLoading(true);
      const response = await getRAGFiles();
      setFiles(response);
      setError(null);
    } catch (err) {
      setError('Failed to load file list');
      console.error('Load files error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFiles();
    loadPendingApprovals();
    loadTemplateSlots();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = async (fileId: number, filename: string) => {
    if (!window.confirm(`Delete file "${filename}"?`)) {
      return;
    }

    try {
      await deleteRAGFile(fileId);
      setFiles(files.filter(f => f.id !== fileId));
      alert('File deleted successfully');
    } catch (err) {
      alert('Failed to delete file');
      console.error('Delete file error:', err);
    }
  };

  const handleDownload = async (fileId: number, filename: string) => {
    try {
      await downloadRAGFile(fileId, filename);
    } catch (err) {
      alert('Failed to download file');
      console.error('Download file error:', err);
    }
  };

  const handlePreview = (fileId: number) => {
    setSelectedFileId(fileId);
    setPreviewModalOpen(true);
  };

  const handleUploadSuccess = () => {
    setUploadModalOpen(false);
    loadFiles();
  };

  const handleTemplateUpload = async (slot: TemplateSlotType, file: File) => {
    if (!file.name.toLowerCase().endsWith('.docx')) {
      alert('Template must be a .docx file');
      return;
    }
    setTemplateUploading(slot);
    try {
      await uploadTemplateFile(file, slot);
      await loadTemplateSlots();
      await loadFiles();
      alert('Template uploaded successfully');
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Template upload failed');
    } finally {
      setTemplateUploading(null);
      const input = templateFileInputRefs.current[slot];
      if (input) input.value = '';
    }
  };

  const slotLabels: Record<TemplateSlotType, string> = {
    interim: 'Interim Reply',
    final: 'Final Reply',
    wrong_referral: 'Wrong Referral Reply'
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const formatFileType = (fileType: string): string => {
    const typeMap: { [key: string]: string } = {
      'excel': 'Excel',
      'word': 'Word',
      'powerpoint': 'PowerPoint',
      'pdf': 'PDF',
      'txt': 'TXT',
      'csv': 'CSV',
      'image': 'Image'
    };
    return typeMap[fileType] || fileType;
  };

  const q = searchQuery.trim().toLowerCase();
  const filteredFiles = q
    ? files.filter(
        (f) =>
          (f.filename || '').toLowerCase().includes(q) ||
          (f.file_type || '').toLowerCase().includes(q)
      )
    : files;

  const getFileTypeColor = (fileType: string): string => {
    const colorMap: { [key: string]: string } = {
      'excel': '#217346',
      'word': '#2b579a',
      'powerpoint': '#d24726',
      'pdf': '#dc3545',
      'txt': '#6c757d',
      'csv': '#28a745',
      'image': '#17a2b8'
    };
    return colorMap[fileType] || '#6c757d';
  };

  if (loading) {
    return (
      <div className="knowledge-base-panel">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="knowledge-base-panel">
        <div className="error-state">
          <p>{error}</p>
          <GradientButton onClick={loadFiles} size="sm" variant="primary">
            Retry
          </GradientButton>
        </div>
      </div>
    );
  }

  return (
    <div className="knowledge-base-panel">
      <div className="panel-header">
        <div>
          <h2>Knowledge Base Files</h2>
          <p className="panel-description">
            Manage RAG knowledge base files
          </p>
        </div>
        <GradientButton
            className="upload-button"
            onClick={() => setUploadModalOpen(true)}
            size="md"
            variant="primary"
          >
            <span className="button-icon">⬆️</span>
            Upload file
          </GradientButton>
      </div>

      <div className="reply-templates-section">
        <h3>Reply Templates</h3>
        <p className="section-desc">Fixed slots for draft reply templates. Upload .docx to overwrite.</p>
        <div className="template-slots-grid">
          {(['interim', 'final', 'wrong_referral'] as TemplateSlotType[]).map((slot) => {
            const slotData = templateSlots?.[slot];
            const isUploading = templateUploading === slot;
            return (
              <div key={slot} className="template-slot-card">
                <div className="template-slot-header">
                  <h4>{slotLabels[slot]}</h4>
                  <span className="template-slot-badge">{slot}</span>
                </div>
                <div className="template-slot-body">
                  {slotData ? (
                    <>
                      <p className="template-filename" title={slotData.filename || ''}>
                        {slotData.filename || '—'}
                      </p>
                      <p className="template-upload-time">
                        {slotData.upload_time
                          ? new Date(slotData.upload_time).toLocaleString()
                          : '—'}
                      </p>
                    </>
                  ) : (
                    <p className="template-empty">No template uploaded</p>
                  )}
                </div>
                <div className="template-slot-actions">
                  <input
                    ref={(el) => { templateFileInputRefs.current[slot] = el; }}
                    type="file"
                    accept=".docx"
                    style={{ display: 'none' }}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleTemplateUpload(slot, f);
                    }}
                  />
                  <GradientButton
                    size="sm"
                    variant="primary"
                    disabled={isUploading}
                    onClick={() => templateFileInputRefs.current[slot]?.click()}
                  >
                    {isUploading ? 'Uploading...' : slotData ? 'Replace' : 'Upload'}
                  </GradientButton>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {pendingApprovals.length > 0 && (
        <div className="pending-approval-section">
          <h3>Reply templates (pending approval)</h3>
          <p className="section-desc">Confirm these as knowledge base sources for RAG retrieval.</p>
          <div className="pending-approval-list">
            {pendingApprovals.map((doc) => (
              <div key={`${doc.doc_type}-${doc.filename}`} className="pending-approval-item">
                <div className="pending-approval-info">
                  <strong>{doc.filename}</strong>
                  <span className="doc-type">{doc.doc_type}</span>
                  <p className="content-preview">{doc.content_preview}…</p>
                </div>
                <button
                  type="button"
                  className="action-button approve"
                  disabled={approvingDoc === `${doc.doc_type}:${doc.filename}`}
                  onClick={async () => {
                    setApprovingDoc(`${doc.doc_type}:${doc.filename}`);
                    try {
                      await approveKnowledgeDoc(doc.doc_type, doc.filename);
                      setPendingApprovals((prev) => prev.filter((d) => d.doc_type !== doc.doc_type || d.filename !== doc.filename));
                    } catch (err) {
                      alert('Failed to approve');
                    } finally {
                      setApprovingDoc(null);
                    }
                  }}
                >
                  {approvingDoc === `${doc.doc_type}:${doc.filename}` ? 'Approving...' : '✓ Confirm as KB source'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {filteredFiles.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📚</div>
          <h3>{files.length === 0 ? 'No knowledge base files' : 'No matching files'}</h3>
          <p>{files.length === 0 ? 'Click "Upload file" to add knowledge base files' : `No results for "${searchQuery}"`}</p>
          {files.length === 0 && (
            <GradientButton
              className="upload-button-large"
              onClick={() => setUploadModalOpen(true)}
              size="lg"
              variant="primary"
            >
              Upload first file
            </GradientButton>
          )}
        </div>
      ) : (
        <div className="files-grid">
          {filteredFiles.map((file) => (
            <div key={file.id} className="file-card">
              <div className="file-card-header">
                <div 
                  className="file-type-icon" 
                  style={{ backgroundColor: getFileTypeColor(file.file_type) }}
                >
                  {formatFileType(file.file_type)}
                </div>
                <div className="file-status">
                  {file.processed ? (
                    <span className="status-badge success">✓ Processed</span>
                  ) : (
                    <span className="status-badge warning">⏳ Processing</span>
                  )}
                </div>
              </div>

              <div className="file-card-body">
                <h3 className="file-name" title={file.filename}>
                  {file.filename}
                </h3>
                <div className="file-meta">
                  <div className="meta-item">
                    <span className="meta-label">Size: </span>
                    <span className="meta-value">{formatFileSize(file.file_size)}</span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">Chunks: </span>
                    <span className="meta-value">{file.processed ? file.chunk_count : '—'}</span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">Uploaded: </span>
                    <span className="meta-value">
                      {new Date(file.upload_time).toLocaleDateString('zh-CN')}
                    </span>
                  </div>
                </div>

                {file.processing_error && (
                  <div className="error-message">
                    <span>⚠️ {file.processing_error}</span>
                  </div>
                )}
              </div>

              <div className="file-card-actions">
                <button 
                  className="action-button preview"
                  onClick={() => handlePreview(file.id)}
                  title="Preview"
                >
                  👁️ Preview
                </button>
                <button 
                  className="action-button download"
                  onClick={() => handleDownload(file.id, file.filename)}
                  title="Download"
                >
                  ⬇️ Download
                </button>
                <button 
                  className="action-button delete"
                  onClick={() => handleDelete(file.id, file.filename)}
                  title="Delete"
                >
                  🗑️ Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="panel-footer">
        <p>{filteredFiles.length === files.length ? `${files.length} knowledge base file(s)` : `${filteredFiles.length} of ${files.length} file(s)`}</p>
      </div>

      {uploadModalOpen && (
        <KBFileUploadModal
          onClose={() => setUploadModalOpen(false)}
          onSuccess={handleUploadSuccess}
        />
      )}

      {previewModalOpen && selectedFileId && (
        <KBFilePreviewModal
          fileId={selectedFileId}
          onClose={() => {
            setPreviewModalOpen(false);
            setSelectedFileId(null);
          }}
        />
      )}
    </div>
  );
};

export default KnowledgeBasePanel;
