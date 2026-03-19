import React, { useState } from 'react';
import { FileText, Calendar, User, AlertCircle, X } from 'lucide-react';
import { ExtractedData, FileInfo } from '../types';
import ExtractedInfoDisplay from './ExtractedInfoDisplay';
import CorrectionModal from './CorrectionModal';

const FIELD_LABELS: Record<string, string> = {
  A_date_received: 'Date Received (A)',
  B_source: 'Source (B)',
  C_case_number: 'Case Number (C)',
  D_type: 'Case Type (D)',
  E_caller_name: 'Caller Name (E)',
  F_contact_no: 'Contact Number (F)',
  G_slope_no: 'Slope Number (G)',
  H_location: 'Location (H)',
  I_nature_of_request: 'Nature of Request (I)',
  J_subject_matter: 'Subject Matter (J)',
  K_10day_rule_due_date: '10-Day Rule Due Date (K)',
  L_icc_interim_due: 'ICC Interim Reply Due Date (L)',
  M_icc_final_due: 'ICC Final Reply Due Date (M)',
  N_works_completion_due: 'Works Completion Due Date (N)',
  O1_fax_to_contractor: 'Fax to Contractor Date (O1)',
  O2_email_send_time: 'Email Send Time (O2)',
  P_fax_pages: 'Fax Pages (P)',
  Q_case_details: 'Case Details (Q)',
};

interface FileInfoModalProps {
  isOpen: boolean;
  onClose: () => void;
  fileInfo: FileInfo | null;
  extractedData: ExtractedData | null;
  summaryResult?: any;
  similarCases?: any[];
  locationStatistics?: { total_cases?: number; is_frequent_location?: boolean; is_frequent_slope?: boolean; date_range?: string | { earliest: string; latest: string } } | null;
}

const FileInfoModal: React.FC<FileInfoModalProps> = ({
  isOpen,
  onClose,
  fileInfo,
  extractedData,
  summaryResult,
  similarCases,
  locationStatistics
}) => {
  const [correctionField, setCorrectionField] = useState<{ fieldName: string; fieldLabel: string; incorrectValue: string } | null>(null);

  if (!isOpen) return null;

  const formatFileSize = (bytes: number) => {
    return `${(bytes / 1024).toFixed(1)} KB`;
  };

  const getFileTypeIcon = (type: string) => {
    return type.includes('pdf') ? '📄' : '📝';
  };

  const getProcessingStatus = () => {
    if (extractedData) {
      const filledFields = Object.values(extractedData).filter(value => value && value !== 'N/A').length;
      const totalFields = Object.keys(extractedData).length;
      const completionRate = Math.round((filledFields / totalFields) * 100);

      if (completionRate >= 80) return { status: 'excellent', rate: completionRate, color: '#10b981' };
      if (completionRate >= 60) return { status: 'good', rate: completionRate, color: '#f59e0b' };
      if (completionRate >= 40) return { status: 'fair', rate: completionRate, color: '#ef4444' };
      return { status: 'poor', rate: completionRate, color: '#dc2626' };
    }
    return { status: 'unknown', rate: 0, color: '#6b7280' };
  };

  const processingStatus = getProcessingStatus();

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content file-info-modal" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-title">
            <FileText size={18} className="modal-icon" />
            File Processing Details
          </div>
          <button className="modal-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {/* File Information Section */}
          {fileInfo && (
            <div className="detail-section">
              <h3 className="section-title">
                <FileText size={16} />
                File Information
              </h3>
              <div className="file-info-grid">
                <div className="info-item">
                  <div className="info-label">File Name</div>
                  <div className="info-value">
                    <span className="file-icon">{getFileTypeIcon(fileInfo.type)}</span>
                    {fileInfo.name}
                  </div>
                </div>
                <div className="info-item">
                  <div className="info-label">File Size</div>
                  <div className="info-value">{formatFileSize(fileInfo.size)}</div>
                </div>
                <div className="info-item">
                  <div className="info-label">File Type</div>
                  <div className="info-value">{fileInfo.type}</div>
                </div>
                <div className="info-item">
                  <div className="info-label">Upload Time</div>
                  <div className="info-value">
                    {new Date().toLocaleString()}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Processing Status Section */}
          {extractedData && (
            <div className="detail-section">
              <h3 className="section-title">
                <AlertCircle size={16} />
                Processing Status
              </h3>
              <div className="processing-status">
                <div className="status-item">
                  <span className="status-label">Data Completion:</span>
                  <div className="status-bar">
                    <div
                      className="status-fill"
                      style={{
                        width: `${processingStatus.rate}%`,
                        backgroundColor: processingStatus.color
                      }}
                    ></div>
                  </div>
                  <span className="status-rate" style={{ color: processingStatus.color }}>
                    {processingStatus.rate}%
                  </span>
                </div>
                <div className="status-item">
                  <span className="status-label">Processing Quality:</span>
                  <span className={`status-badge ${processingStatus.status}`}>
                    {processingStatus.status.toUpperCase()}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* AI Summary Section */}
          {summaryResult && (
            <div className="detail-section">
              <h3 className="section-title">
                <Calendar size={16} />
                AI Summary
              </h3>
              <div className="summary-content">
                {summaryResult.summary ? (
                  <div className="summary-success">
                    <div className="summary-text">
                      "{summaryResult.summary}"
                    </div>
                    <div className="summary-meta">
                      <span className="summary-source">
                        Generated by AI • {summaryResult.confidence || 'High'} confidence
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="summary-error">
                    <AlertCircle size={16} className="error-icon" />
                    <span>
                      AI summary generation failed: {
                        summaryResult.error && summaryResult.error.trim()
                          ? summaryResult.error
                          : "Unable to generate summary. Please try again later."
                      }
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Similar Historical Cases Section */}
          {similarCases && similarCases.length > 0 && (
            <div className="detail-section">
              <h3 className="section-title">
                <FileText size={16} />
                Similar Historical Cases
              </h3>
              <div className="file-info-grid" style={{ flexDirection: 'column', gap: '12px' }}>
                {similarCases.map((item: any, idx: number) => {
                  const c = item.case || item;
                  const score = item.similarity_score != null ? (item.similarity_score * 100).toFixed(1) : '-';
                  const source = item.data_source || 'Unknown';
                  const isDup = item.is_potential_duplicate;
                  return (
                    <div key={idx} className="info-item" style={{ flexDirection: 'column', alignItems: 'stretch', padding: '10px', border: '1px solid var(--border, #e5e7eb)', borderRadius: '8px' }}>
                      <div className="info-value" style={{ marginBottom: '6px' }}>
                        [{source}] Case #{c.C_case_number || 'N/A'} ({score}% match)
                        {isDup && <span style={{ marginLeft: '8px', color: '#dc2626', fontSize: '12px' }}>Potential duplicate</span>}
                      </div>
                      <div style={{ fontSize: '13px', color: 'var(--muted-foreground, #6b7280)' }}>
                        {c.A_date_received && <div>Date: {c.A_date_received}</div>}
                        {c.H_location && <div>Location: {c.H_location}</div>}
                        {c.G_slope_no && <div>Slope: {c.G_slope_no}</div>}
                        {c.J_subject_matter && <div>Subject: {c.J_subject_matter}</div>}
                        {c.I_nature_of_request && <div>Complaint: {String(c.I_nature_of_request).length > 150 ? String(c.I_nature_of_request).slice(0, 150) + '...' : c.I_nature_of_request}</div>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Location Statistics Section */}
          {locationStatistics != null && (
            <div className="detail-section">
              <h3 className="section-title">
                <FileText size={16} />
                Location Statistics
              </h3>
              <div className="file-info-grid">
                <div className="info-item">
                  <div className="info-label">Total cases (historical)</div>
                  <div className="info-value">{locationStatistics.total_cases ?? 0}</div>
                </div>
                {locationStatistics.date_range && (() => {
                  const dr = locationStatistics.date_range;
                  const dateRangeStr = typeof dr === 'object' && dr !== null && 'earliest' in dr && 'latest' in dr
                    ? `${(dr as { earliest: string; latest: string }).earliest} – ${(dr as { earliest: string; latest: string }).latest}`
                    : String(dr);
                  return (
                  <div className="info-item">
                    <div className="info-label">Date range</div>
                    <div className="info-value">{dateRangeStr}</div>
                  </div>
                );})()}
                <div className="info-item">
                  <div className="info-label">Frequent complaint location</div>
                  <div className="info-value">{(locationStatistics.is_frequent_location || locationStatistics.is_frequent_slope) ? 'Yes' : 'No'}</div>
                </div>
              </div>
            </div>
          )}

          {/* Extracted Data Section */}
          {extractedData && (
            <div className="detail-section">
              <h3 className="section-title">
                <User size={16} />
                Extracted Case Data
              </h3>
              <ExtractedInfoDisplay
                data={extractedData}
                caseId={fileInfo?.case_id}
                onCorrectField={(fieldName, incorrectValue) => {
                  setCorrectionField({
                    fieldName,
                    fieldLabel: FIELD_LABELS[fieldName] || fieldName,
                    incorrectValue,
                  });
                }}
              />
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
          {extractedData && fileInfo && (
            <button className="btn-primary" onClick={() => {
              const exportData = {
                fileInfo: {
                  name: fileInfo.name,
                  size: fileInfo.size,
                  type: fileInfo.type,
                  uploadTime: new Date().toISOString()
                },
                extractedData,
                summaryResult,
                processingStatus: processingStatus,
                exportTime: new Date().toISOString()
              };

              const dataStr = JSON.stringify(exportData, null, 2);
              const dataBlob = new Blob([dataStr], { type: 'application/json' });
              const url = URL.createObjectURL(dataBlob);
              const link = document.createElement('a');
              link.href = url;
              link.download = `srr_case_${fileInfo.name.replace(/\.[^/.]+$/, '')}_${new Date().toISOString().split('T')[0]}.json`;
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
              URL.revokeObjectURL(url);
            }}>
              Export Data
            </button>
          )}
        </div>
      </div>
      {correctionField && (
        <CorrectionModal
          isOpen={!!correctionField}
          onClose={() => setCorrectionField(null)}
          onSuccess={() => setCorrectionField(null)}
          fieldName={correctionField.fieldName}
          fieldLabel={correctionField.fieldLabel}
          incorrectValue={correctionField.incorrectValue}
          caseId={fileInfo?.case_id}
        />
      )}
    </div>
  );
};

export default FileInfoModal;
