import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import './KBFileUploadModal.css';
import {
  calculateFileSha256,
  precheckKnowledgeBaseUpload,
  uploadRAGFile,
  uploadSlopeDataFile,
  uploadTreeInventoryFile
} from '../services/api';
import type { KbUploadPrecheckData } from '../services/api';
import GradientButton from './GradientButton';
import { useChat } from '../contexts/ChatContext';

type FileStatus = 'checking' | 'ready' | 'already_uploaded' | 'new_version';

interface KBFileUploadModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

const KBFileUploadModal: React.FC<KBFileUploadModalProps> = ({ onClose, onSuccess }) => {
  const { embeddingModel } = useChat();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadMode, setUploadMode] = useState<'general' | 'slope_data' | 'tree_inventory'>('general');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ [key: string]: number }>({});
  const [errors, setErrors] = useState<{ [key: string]: string }>({});
  const [fileStatuses, setFileStatuses] = useState<Record<string, FileStatus>>({});

  const acceptedFileTypes = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    'application/vnd.ms-excel': ['.xls'],
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
    'application/pdf': ['.pdf'],
    'text/plain': ['.txt'],
    'text/csv': ['.csv'],
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/png': ['.png'],
    'image/gif': ['.gif']
  };

  const maxFileSize = 100 * 1024 * 1024; // 100MB

  const fileKey = (f: File) => `${f.name}__${f.size}`;

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newFiles = acceptedFiles.filter(
      (file) => !selectedFiles.some((f) => f.name === file.name && f.size === file.size)
    );
    setSelectedFiles((prev) => [...prev, ...newFiles]);
    newFiles.forEach((f) => setFileStatuses((s) => ({ ...s, [fileKey(f)]: 'checking' })));
  }, [selectedFiles]);

  useEffect(() => {
    if (selectedFiles.length === 0) {
      setFileStatuses({});
      return;
    }
    const finalStatuses: FileStatus[] = ['ready', 'already_uploaded', 'new_version'];
    const toCheck = selectedFiles.filter((f) => !finalStatuses.includes(fileStatuses[fileKey(f)]));
    if (toCheck.length === 0) return;
    setFileStatuses((s) => {
      const next = { ...s };
      toCheck.forEach((f) => { next[fileKey(f)] = 'checking'; });
      return next;
    });
    let cancelled = false;
    const run = async () => {
      for (const file of toCheck) {
        if (cancelled) return;
        try {
          const hash = await calculateFileSha256(file);
          if (cancelled) return;
          const precheck: KbUploadPrecheckData = await precheckKnowledgeBaseUpload(file, hash);
          if (cancelled) return;
          const status: FileStatus =
            precheck.result === 'FOUND_SAME_HASH'
              ? 'already_uploaded'
              : precheck.result === 'FOUND_SAME_NAME_DIFF_HASH'
                ? 'new_version'
                : 'ready';
          setFileStatuses((s) => ({ ...s, [fileKey(file)]: status }));
        } catch {
          if (!cancelled) setFileStatuses((s) => ({ ...s, [fileKey(file)]: 'ready' }));
        }
      }
    };
    run();
    return () => { cancelled = true; };
  }, [selectedFiles]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: acceptedFileTypes,
    maxSize: maxFileSize,
    multiple: true
  });

  const removeFile = (index: number) => {
    const file = selectedFiles[index];
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    if (file) setFileStatuses((s) => { const n = { ...s }; delete n[fileKey(file)]; return n; });
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    setUploading(true);
    setErrors({});
    const newProgress: { [key: string]: number } = {};
    selectedFiles.forEach(file => {
      newProgress[file.name] = 0;
    });
    setUploadProgress(newProgress);

    let successCount = 0;
    let errorCount = 0;
    let skippedDuplicateCount = 0;

    try {
      for (const file of selectedFiles) {
        try {
          const fileHash = await calculateFileSha256(file);
          const precheck = await precheckKnowledgeBaseUpload(file, fileHash);
          if (precheck.result === 'FOUND_SAME_HASH') {
            const duplicateMessage = `Already exists in knowledge base: ${precheck.existing_filename || file.name}`;
            setErrors((prev) => ({
              ...prev,
              [file.name]: duplicateMessage
            }));
            setUploadProgress((prev) => ({
              ...prev,
              [file.name]: 100
            }));
            skippedDuplicateCount++;
            continue;
          }

          const onProgress = (progress: number) => {
            setUploadProgress((prev) => ({ ...prev, [file.name]: progress }));
          };

          let uploaded;
          if (uploadMode === 'slope_data') {
            uploaded = await uploadSlopeDataFile(file, onProgress);
          } else if (uploadMode === 'tree_inventory') {
            uploaded = await uploadTreeInventoryFile(file, onProgress);
          } else {
            uploaded = await uploadRAGFile(file, onProgress, embeddingModel.provider, embeddingModel.model);
          }
          setUploadProgress((prev) => ({
            ...prev,
            [file.name]: 100
          }));
          successCount++;
          // File may be processing in background (processed === false)
          if (!uploaded.processed) {
            console.log(`File ${file.name} queued for background processing`);
          }
        } catch (error: any) {
          setErrors((prev) => ({
            ...prev,
            [file.name]: error.message || 'Upload failed'
          }));
          errorCount++;
        }
      }

      if (errorCount === 0) {
        if (successCount > 0) {
          alert(
            successCount === 1
              ? 'File uploaded. Processing in background (chunking and embedding). Refresh the list later to see when it\'s ready.'
              : `Successfully uploaded ${successCount} file(s). Processing in background. Refresh the list later to see when ready.`
          );
          onSuccess();
        } else if (skippedDuplicateCount > 0) {
          alert(`No files uploaded: ${skippedDuplicateCount} file(s) already exist in knowledge base.`);
        }
      } else {
        alert(
          `Upload complete: ${successCount} succeeded, ${errorCount} failed, ${skippedDuplicateCount} skipped (already exists)`
        );
      }
    } finally {
      setUploading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  const getFileIcon = (filename: string): string => {
    const ext = filename.split('.').pop()?.toLowerCase();
    const iconMap: { [key: string]: string } = {
      'xlsx': '📊',
      'xls': '📊',
      'docx': '📄',
      'pptx': '📽️',
      'pdf': '📕',
      'txt': '📝',
      'csv': '📋',
      'jpg': '🖼️',
      'jpeg': '🖼️',
      'png': '🖼️',
      'gif': '🖼️'
    };
    return iconMap[ext || ''] || '📎';
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content kb-upload-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Upload knowledge base files</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          <div style={{ marginBottom: '12px' }}>
            <label htmlFor="kb-upload-mode" style={{ display: 'block', marginBottom: '6px', fontWeight: 600 }}>
              Upload type
            </label>
            <select
              id="kb-upload-mode"
              value={uploadMode}
              onChange={(e) => setUploadMode(e.target.value as 'general' | 'slope_data' | 'tree_inventory')}
              disabled={uploading}
              style={{ width: '100%', padding: '8px' }}
            >
              <option value="general">General knowledge</option>
              <option value="slope_data">Slope data</option>
              <option value="tree_inventory">Tree inventory</option>
            </select>
          </div>

          <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''}`}>
            <input {...getInputProps()} />
            <div className="dropzone-content">
              <div className="dropzone-icon">📤</div>
              <p className="dropzone-text">
                {isDragActive ? 'Drop files to upload' : 'Drag files here or click to select'}
              </p>
              <p className="dropzone-hint">
                Supported: Excel, Word, PowerPoint, PDF, TXT, CSV, images
              </p>
              <p className="dropzone-hint">
                Max file size: 100MB
              </p>
            </div>
          </div>

          {selectedFiles.length > 0 && (
            <div className="selected-files">
              <h3>Selected files ({selectedFiles.length})</h3>
              <div className="files-list">
                {selectedFiles.map((file, index) => {
                  const status = fileStatuses[fileKey(file)];
                  const statusLabel =
                    status === 'already_uploaded'
                      ? 'Already uploaded'
                      : status === 'new_version'
                        ? 'New version'
                        : status === 'ready'
                          ? 'Ready'
                          : 'Checking...';
                  return (
                  <div key={index} className="file-item">
                    <div className="file-info">
                      <span className="file-icon">{getFileIcon(file.name)}</span>
                      <div className="file-details">
                        <div className="file-name">{file.name}</div>
                        <div className="file-size">{formatFileSize(file.size)}</div>
                      </div>
                      {!uploading && (
                        <span className={`file-status-badge file-status-${status || 'checking'}`}>
                          {status === 'checking' && <span className="status-spinner" />}
                          {statusLabel}
                        </span>
                      )}
                    </div>
                    
                    {uploading ? (
                      <div className="upload-progress">
                        <div 
                          className="progress-bar" 
                          style={{ width: `${uploadProgress[file.name] || 0}%` }}
                        />
                        <span className="progress-text">
                          {(uploadProgress[file.name] || 0) >= 100
                            ? 'Processing...'
                            : `${uploadProgress[file.name] || 0}%`}
                        </span>
                      </div>
                    ) : (
                      <button 
                        className="remove-button" 
                        onClick={() => removeFile(index)}
                        title="Remove"
                      >
                        ×
                      </button>
                    )}

                    {errors[file.name] && (
                      <div className="file-error">{errors[file.name]}</div>
                    )}
                  </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <GradientButton
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={uploading}
          >
            Cancel
          </GradientButton>
          <GradientButton
            variant="primary"
            size="sm"
            onClick={handleUpload}
            disabled={selectedFiles.length === 0 || uploading}
          >
            {uploading
              ? (Object.keys(uploadProgress).every((name) => (uploadProgress[name] || 0) >= 100)
                ? 'Processing...'
                : 'Uploading...')
              : `Upload ${selectedFiles.length} file(s)`}
          </GradientButton>
        </div>
      </div>
    </div>
  );
};

export default KBFileUploadModal;
