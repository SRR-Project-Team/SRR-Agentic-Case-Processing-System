import React, { useState, useEffect } from 'react';
import * as XLSX from 'xlsx';
import './KBFilePreviewModal.css';
import { downloadRAGFile, getRAGFileBlob, getRAGFileDetails, getRAGFilePreviewPdf } from '../services/api';
import { RAGFileDetails } from '../types/index';

interface ExcelSheet {
  name: string;
  html: string;
}

interface KBFilePreviewModalProps {
  fileId: number;
  onClose: () => void;
}

const KBFilePreviewModal: React.FC<KBFilePreviewModalProps> = ({ fileId, onClose }) => {
  const [details, setDetails] = useState<RAGFileDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'info' | 'preview'>('info');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewLoaded, setPreviewLoaded] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string>('');
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [officePdfAvailable, setOfficePdfAvailable] = useState(false);
  const [excelSheets, setExcelSheets] = useState<ExcelSheet[]>([]);
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);

  useEffect(() => {
    loadFileData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId]); // Only reload when fileId changes

  useEffect(() => {
    if (activeTab === 'preview' && details && !previewLoaded && !previewLoading) {
      loadPreviewContent(details);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, details, previewLoaded, previewLoading]);

  useEffect(() => {
    return () => {
      if (previewBlobUrl) {
        URL.revokeObjectURL(previewBlobUrl);
      }
    };
  }, [previewBlobUrl]);

  const loadFileData = async () => {
    try {
      setLoading(true);
      setPreviewLoaded(false);
      setPreviewError(null);
      setPreviewText('');
      setExcelSheets([]);
      setActiveSheetIndex(0);
      if (previewBlobUrl) {
        URL.revokeObjectURL(previewBlobUrl);
        setPreviewBlobUrl(null);
      }
      const detailsData = await getRAGFileDetails(fileId);
      setDetails(detailsData);
      setError(null);
    } catch (err) {
      setError('Failed to load file info');
      console.error('Load file data error:', err);
    } finally {
      setLoading(false);
    }
  };

  const isOfficeType = (ft: string) => ['excel', 'word', 'powerpoint'].includes(ft);

  const loadPreviewContent = async (fileDetails: RAGFileDetails) => {
    try {
      setPreviewLoading(true);
      setPreviewError(null);
      setPreviewText('');
      setOfficePdfAvailable(false);
      setExcelSheets([]);
      setActiveSheetIndex(0);
      if (previewBlobUrl) {
        URL.revokeObjectURL(previewBlobUrl);
        setPreviewBlobUrl(null);
      }

      const fileType = (fileDetails.file_type || '').toLowerCase();

      if (fileType === 'excel') {
        const blob = await getRAGFileBlob(fileDetails.id);
        const buf = await blob.arrayBuffer();
        const wb = XLSX.read(buf, { type: 'array' });
        const sheets: ExcelSheet[] = [];
        wb.SheetNames.forEach((name) => {
          const ws = wb.Sheets[name];
          const html = XLSX.utils.sheet_to_html(ws, { id: `sheet-${name}`, editable: false });
          sheets.push({ name, html });
        });
        setExcelSheets(sheets);
        setPreviewLoaded(true);
        return;
      }

      if (fileType === 'word' || fileType === 'powerpoint') {
        try {
          const pdfBlob = await getRAGFilePreviewPdf(fileDetails.id);
          const objectUrl = URL.createObjectURL(pdfBlob);
          setPreviewBlobUrl(objectUrl);
          setOfficePdfAvailable(true);
          setPreviewLoaded(true);
          return;
        } catch {
          setOfficePdfAvailable(false);
        }
      }

      if (fileType === 'txt' || fileType === 'csv') {
        const blob = await getRAGFileBlob(fileDetails.id);
        const text = await blob.text();
        setPreviewText(text || '');
      } else if (fileType === 'pdf' || fileType === 'image') {
        const blob = await getRAGFileBlob(fileDetails.id);
        const objectUrl = URL.createObjectURL(blob);
        setPreviewBlobUrl(objectUrl);
      }

      setPreviewLoaded(true);
    } catch (err) {
      console.error('Load preview content error:', err);
      setPreviewError('Failed to load preview content');
      setPreviewLoaded(true);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!details) return;
    try {
      await downloadRAGFile(details.id, details.filename);
    } catch (err) {
      console.error('Download from preview error:', err);
      setPreviewError('Failed to download file');
    }
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

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content preview-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>File preview</h2>
            <button className="close-button" onClick={onClose}>×</button>
          </div>
          <div className="modal-body">
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Loading...</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !details) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content preview-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>File preview</h2>
            <button className="close-button" onClick={onClose}>×</button>
          </div>
          <div className="modal-body">
            <div className="error-state">
              <p>{error}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content preview-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{details.filename}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <div className="preview-tabs">
          <button
            className={`preview-tab ${activeTab === 'info' ? 'active' : ''}`}
            onClick={() => setActiveTab('info')}
          >
            File info
          </button>
          <button
            className={`preview-tab ${activeTab === 'preview' ? 'active' : ''}`}
            onClick={() => setActiveTab('preview')}
          >
            Content preview
          </button>
        </div>

        <div className="modal-body">
          {activeTab === 'info' ? (
            <div className="file-info-section">
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">File type: </span>
                  <span className="info-value">{formatFileType(details.file_type)}</span>
                </div>

                <div className="info-item">
                  <span className="info-label">File size: </span>
                  <span className="info-value">{formatFileSize(details.file_size)}</span>
                </div>

                <div className="info-item">
                  <span className="info-label">Upload time: </span>
                  <span className="info-value">
                    {new Date(details.upload_time).toLocaleString('zh-CN')}
                  </span>
                </div>

                <div className="info-item">
                  <span className="info-label">Processing status: </span>
                  <span className="info-value">
                    {details.processed ? (
                      <span className="status-badge success">✓ Processed</span>
                    ) : (
                      <span className="status-badge warning">⏳ Processing</span>
                    )}
                  </span>
                </div>

                <div className="info-item">
                  <span className="info-label">Chunk count: </span>
                  <span className="info-value">{details.chunk_count}</span>
                </div>

                <div className="info-item">
                  <span className="info-label">MIME type: </span>
                  <span className="info-value">{details.mime_type}</span>
                </div>
              </div>

              {details.processing_error && (
                <div className="error-message">
                  <h3>Processing error</h3>
                  <p>{details.processing_error}</p>
                </div>
              )}

              {details.metadata && Object.keys(details.metadata).length > 0 && (
                <div className="metadata-section">
                  <h3>File metadata</h3>
                  <div className="metadata-grid">
                    {Object.entries(details.metadata).map(([key, value]) => (
                      <div key={key} className="metadata-item">
                        <span className="metadata-label">{key}:</span>
                        <span className="metadata-value">
                          {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="preview-section">
              {previewLoading ? (
                <div className="loading-state">
                  <div className="spinner"></div>
                  <p>Loading preview...</p>
                </div>
              ) : previewError ? (
                <div className="error-state">
                  <p>{previewError}</p>
                </div>
              ) : details.file_type === 'excel' && excelSheets.length > 0 ? (
                <div className="excel-preview-wrap">
                  {excelSheets.length > 1 && (
                    <div className="excel-sheet-tabs">
                      {excelSheets.map((s, i) => (
                        <button
                          key={s.name}
                          className={`excel-sheet-tab ${i === activeSheetIndex ? 'active' : ''}`}
                          onClick={() => setActiveSheetIndex(i)}
                        >
                          {s.name}
                        </button>
                      ))}
                    </div>
                  )}
                  <div
                    className="excel-table-wrap"
                    dangerouslySetInnerHTML={{ __html: excelSheets[activeSheetIndex]?.html ?? '' }}
                  />
                </div>
              ) : details.file_type === 'pdf' && previewBlobUrl ? (
                <iframe
                  className="native-file-viewer"
                  src={`${previewBlobUrl}#view=FitH`}
                  title="PDF Preview"
                />
              ) : details.file_type === 'image' && previewBlobUrl ? (
                <div className="image-preview-wrap">
                  <img src={previewBlobUrl} alt={details.filename} className="native-image-viewer" />
                </div>
              ) : (details.file_type === 'txt' || details.file_type === 'csv') ? (
                <>
                  <div className="preview-info">
                    <p>Showing original text content</p>
                  </div>
                  <div className="preview-content">
                    <pre>{previewText || 'No text content available'}</pre>
                  </div>
                </>
              ) : isOfficeType(details.file_type) && officePdfAvailable && previewBlobUrl ? (
                <iframe
                  className="native-file-viewer"
                  src={`${previewBlobUrl}#view=FitH`}
                  title="Office PDF Preview"
                />
              ) : isOfficeType(details.file_type) ? (
                <div className="empty-preview">
                  <p>
                    LibreOffice is not installed on the server. Download the file to open with the original app.
                  </p>
                  <button className="preview-action-btn" onClick={handleDownload}>
                    Download original file
                  </button>
                </div>
              ) : (
                <div className="empty-preview">
                  <p>Preview is not supported for this file type</p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="close-button-footer" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default KBFilePreviewModal;
