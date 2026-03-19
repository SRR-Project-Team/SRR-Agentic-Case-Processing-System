import React, { useState, useEffect } from 'react';
import './CaseDetailModal.css';
import { getCaseDetails, deleteConversationDraft } from '../services/api';
import {
  X,
  FileText,
  Clock,
  MessageSquare,
  Paperclip,
  Sparkles,
  Search,
  Trash2,
  Edit3
} from 'lucide-react';
import GradientButton from './GradientButton';
import CorrectionModal from './CorrectionModal';
import './CorrectionModal.css';

interface CaseDetailModalProps {
  caseId: number | null;
  onClose: () => void;
  /** Called when "Generate draft reply" is clicked. Passes caseId, filename, and the parsed case object. */
  onLoadForQuery?: (caseId: number, filename: string, caseData: any) => void;
}

const FIELD_LABELS: Record<string, string> = {
  A_date_received: 'Date received',
  B_source: 'Source',
  C_case_number: 'Case number',
  D_type: 'Type',
  E_caller_name: 'Caller name',
  F_contact_no: 'Contact no.',
  G_slope_no: 'Slope no.',
  H_location: 'Location',
  I_nature_of_request: 'Nature of request',
  J_subject_matter: 'Subject matter',
  K_10day_rule_due_date: '10-day rule due date',
  L_icc_interim_due: 'ICC interim due',
  M_icc_final_due: 'ICC final due',
  N_works_completion_due: 'Works completion due',
  O1_fax_to_contractor: 'Fax to contractor',
  O2_email_send_time: 'Email send time',
  P_fax_pages: 'Fax pages',
  Q_case_details: 'Case details'
};

const CaseDetailModal: React.FC<CaseDetailModalProps> = ({
  caseId,
  onClose,
  onLoadForQuery
}) => {
  const [details, setDetails] = useState<{
    case: any;
    conversations: any[];
    attachments: { name: string; type: string; note: string }[];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [correctionField, setCorrectionField] = useState<{ fieldName: string; fieldLabel: string; incorrectValue: string } | null>(null);

  useEffect(() => {
    if (!caseId) return;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getCaseDetails(caseId);
        setDetails(data);
      } catch (err) {
        setError('Failed to load case details');
        console.error('Load case details error:', err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [caseId, refreshKey]);

  const formatFileType = (fileType: string) => {
    const typeMap: { [key: string]: string } = {
      txt: 'TXT',
      tmo: 'TMO PDF',
      rcc: 'RCC PDF'
    };
    return typeMap[fileType] || fileType.toUpperCase();
  };

  const getConversationTypeLabel = (type: string) => {
    if (type?.includes('interim')) return 'Interim reply';
    if (type?.includes('final')) return 'Final reply';
    if (type?.includes('wrong_referral')) return 'Wrong referral reply';
    return type || '-';
  };

  if (!caseId) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content case-detail-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Case details</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {loading && (
            <div className="detail-loading">
              <div className="spinner"></div>
              <p>Loading...</p>
            </div>
          )}

          {error && (
            <div className="detail-error">
              <p>{error}</p>
            </div>
          )}

          {!loading && !error && details && (
            <>
              <section className="detail-section">
                <h3 className="section-title">
                  <FileText size={18} />
                  Case information
                </h3>
                <div className="detail-grid">
                  {Object.entries(FIELD_LABELS).map(([key, label]) => {
                    const value = details.case[key];
                    if (value == null || value === '') return null;
                    return (
                      <div key={key} className="detail-item">
                        <span className="detail-label">{label}:</span>
                        <span className="detail-value">
                          {String(value)}
                          <button
                            type="button"
                            className="correction-btn"
                            onClick={() => setCorrectionField({ fieldName: key, fieldLabel: label, incorrectValue: String(value) })}
                            title="Report correction"
                          >
                            <Edit3 size={12} style={{ display: 'inline', marginRight: '2px' }} />
                            Correct
                          </button>
                        </span>
                      </div>
                    );
                  })}
                </div>
              </section>

              {details.case.ai_summary && (
                <section className="detail-section">
                  <h3 className="section-title">
                    <Sparkles size={18} />
                    AI summary
                  </h3>
                  <div className="ai-summary-content">
                    {details.case.ai_summary}
                  </div>
                </section>
              )}

              {details.case.similar_historical_cases &&
                Array.isArray(details.case.similar_historical_cases) &&
                details.case.similar_historical_cases.length > 0 && (
                  <section className="detail-section">
                    <h3 className="section-title">
                      <Search size={18} />
                      Similar historical cases
                    </h3>
                    <div className="similar-cases-list">
                      {details.case.similar_historical_cases.map(
                        (item: any, idx: number) => {
                          const c = item.case || item;
                          const score = item.similarity_score != null
                            ? (item.similarity_score * 100).toFixed(1)
                            : '-';
                          const source = item.data_source || c.data_source || 'Unknown';
                          const isDup = item.is_potential_duplicate;
                          return (
                            <div
                              key={idx}
                              className={`similar-case-card ${isDup ? 'potential-duplicate' : ''}`}
                            >
                              <div className="similar-case-header">
                                <span className="similar-case-title">
                                  [{source}] Case #{c.C_case_number || 'N/A'} ({score}% similar)
                                </span>
                                {isDup && (
                                  <span className="dup-badge">Potential duplicate</span>
                                )}
                              </div>
                              <div className="similar-case-body">
                                {c.A_date_received && (
                                  <div><span className="sc-label">Date: </span>{c.A_date_received}</div>
                                )}
                                {c.H_location && (
                                  <div><span className="sc-label">Location: </span>{c.H_location}</div>
                                )}
                                {c.G_slope_no && (
                                  <div><span className="sc-label">Slope: </span>{c.G_slope_no}</div>
                                )}
                                {c.J_subject_matter && (
                                  <div><span className="sc-label">Subject: </span>{c.J_subject_matter}</div>
                                )}
                                {c.I_nature_of_request && (
                                  <div className="sc-nature">
                                    <span className="sc-label">Content: </span>
                                    {String(c.I_nature_of_request).length > 200
                                      ? String(c.I_nature_of_request).slice(0, 200) + '...'
                                      : c.I_nature_of_request}
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        }
                      )}
                    </div>
                  </section>
                )}

              {details.case.similar_historical_cases &&
                Array.isArray(details.case.similar_historical_cases) &&
                details.case.similar_historical_cases.length === 0 && (
                  <section className="detail-section">
                    <h3 className="section-title">
                      <Search size={18} />
                      Similar historical cases
                    </h3>
                    <div className="similar-cases-empty">
                      No similar historical cases found; this case appears to be standalone.
                    </div>
                  </section>
                )}

              {details.case.location_statistics && typeof details.case.location_statistics === 'object' && (
                <section className="detail-section">
                  <h3 className="section-title">
                    <FileText size={18} />
                    Location Statistics
                  </h3>
                  <div className="detail-grid processing-grid">
                    <div className="detail-item">
                      <span className="detail-label">Total cases (historical):</span>
                      <span className="detail-value">{details.case.location_statistics.total_cases ?? 0}</span>
                    </div>
                    {details.case.location_statistics.date_range && (() => {
                      const dr = details.case.location_statistics.date_range;
                      const dateRangeStr = typeof dr === 'object' && dr !== null && 'earliest' in dr && 'latest' in dr
                        ? `${(dr as { earliest: string; latest: string }).earliest} – ${(dr as { earliest: string; latest: string }).latest}`
                        : String(dr);
                      return (
                      <div className="detail-item">
                        <span className="detail-label">Date range:</span>
                        <span className="detail-value">{dateRangeStr}</span>
                      </div>
                    );})()}
                    <div className="detail-item">
                      <span className="detail-label">Frequent complaint location:</span>
                      <span className="detail-value">
                        {(details.case.location_statistics.is_frequent_location || details.case.location_statistics.is_frequent_slope) ? 'Yes' : 'No'}
                      </span>
                    </div>
                  </div>
                </section>
              )}

              <section className="detail-section">
                <h3 className="section-title">
                  <Clock size={18} />
                  Processing
                </h3>
                <div className="detail-grid processing-grid">
                  <div className="detail-item">
                    <span className="detail-label">Filename:</span>
                    <span className="detail-value">{details.case.original_filename || '-'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">File type:</span>
                    <span className="detail-value">
                      {formatFileType(details.case.file_type || '')}
                    </span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Processing time:</span>
                    <span className="detail-value">{details.case.processing_time || '-'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Created at:</span>
                    <span className="detail-value">{details.case.created_at || '-'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="detail-label">Updated at:</span>
                    <span className="detail-value">{details.case.updated_at || '-'}</span>
                  </div>
                </div>
              </section>

              {details.conversations && details.conversations.length > 0 && (
                <section className="detail-section">
                  <h3 className="section-title">
                    <MessageSquare size={18} />
                    Processing result
                  </h3>
                  <div className="conversations-list">
                    {details.conversations.map((conv) => (
                      <div key={conv.id} className="conversation-card">
                        <div className="conversation-header">
                          <span className="conv-type-badge">
                            {getConversationTypeLabel(conv.conversation_type)}
                          </span>
                          <span className="conv-time">{conv.updated_at || conv.created_at}</span>
                          {conv.draft_reply && (
                            <button
                              type="button"
                              className="conv-delete-draft"
                              onClick={async () => {
                                setDeletingId(conv.id);
                                try {
                                  await deleteConversationDraft(conv.id);
                                  setRefreshKey((k) => k + 1);
                                } catch (e) {
                                  console.error('Delete draft failed:', e);
                                } finally {
                                  setDeletingId(null);
                                }
                              }}
                              disabled={deletingId === conv.id}
                              title="刪除草稿 / Delete draft"
                              aria-label="Delete draft"
                            >
                              <Trash2 size={14} />
                              {deletingId === conv.id ? '…' : '刪除草稿'}
                            </button>
                          )}
                        </div>
                        {conv.draft_reply && (
                          <div className="draft-reply-content">{conv.draft_reply}</div>
                        )}
                        {conv.status && (
                          <span className={`status-badge status-${conv.status}`}>{conv.status}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {details.attachments && details.attachments.length > 0 && (
                <section className="detail-section">
                  <h3 className="section-title">
                    <Paperclip size={18} />
                    Attachments
                  </h3>
                  <div className="attachments-list">
                    {details.attachments.map((att, idx) => (
                      <div key={idx} className="attachment-item">
                        <FileText size={16} />
                        <span className="att-name">{att.name || 'Unnamed'}</span>
                        <span className="att-type">({formatFileType(att.type || '')})</span>
                        {att.note && <span className="att-note">{att.note}</span>}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </div>

        {correctionField && (
          <CorrectionModal
            isOpen={!!correctionField}
            onClose={() => setCorrectionField(null)}
            onSuccess={() => { setCorrectionField(null); setRefreshKey((k) => k + 1); }}
            fieldName={correctionField.fieldName}
            fieldLabel={correctionField.fieldLabel}
            incorrectValue={correctionField.incorrectValue}
            caseId={caseId}
          />
        )}
        <div className="modal-footer">
          <GradientButton variant="outline" size="sm" onClick={onClose}>
            Close
          </GradientButton>
          {onLoadForQuery && details?.case && (
            <GradientButton
              variant="primary"
              size="sm"
              onClick={() => {
                onLoadForQuery(caseId, details.case.original_filename || '', details.case);
                onClose();
              }}
            >
              Generate draft reply / 生成草稿回覆
            </GradientButton>
          )}
        </div>
      </div>
    </div>
  );
};

export default CaseDetailModal;
