import React, { useState, useEffect } from 'react';
import './CaseFilesPanel.css';
import { getCases } from '../services/api';
import { useChat } from '../contexts/ChatContext';
import type { ExtractedData } from '../types';
import CaseDetailModal from './CaseDetailModal';
import GradientButton from './GradientButton';

interface CaseFile {
  id: number;
  original_filename: string;
  file_type: string;
  processing_time: string;
  A_date_received: string;
  B_source: string;
  C_case_number: string;
  H_location: string;
}

interface CaseFilesPanelProps {
  onSwitchToChat?: () => void;
  searchQuery?: string;
}

const CaseFilesPanel: React.FC<CaseFilesPanelProps> = ({ onSwitchToChat, searchQuery = '' }) => {
  const { setExtractedData, setCurrentFile, setRawFileContent } = useChat();
  const [cases, setCases] = useState<CaseFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailCaseId, setDetailCaseId] = useState<number | null>(null);
  const [loadSuccess, setLoadSuccess] = useState<string | null>(null);

  const loadCases = async () => {
    try {
      setLoading(true);
      const response = await getCases();
      setCases(response);
      setError(null);
    } catch (err) {
      setError('Failed to load case files');
      console.error('Load cases error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCases();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const q = searchQuery.trim().toLowerCase();
  const filteredCases = q
    ? cases.filter(
        (c) =>
          (c.original_filename || '').toLowerCase().includes(q) ||
          (c.C_case_number || '').toLowerCase().includes(q) ||
          (c.B_source || '').toLowerCase().includes(q) ||
          (c.H_location || '').toLowerCase().includes(q) ||
          (c.A_date_received || '').toLowerCase().includes(q)
      )
    : cases;

  const formatFileType = (fileType: string) => {
    const typeMap: { [key: string]: string } = {
      'txt': 'TXT',
      'tmo': 'TMO PDF',
      'rcc': 'RCC PDF'
    };
    return typeMap[fileType] || fileType.toUpperCase();
  };

  const handleLoadForQueryFromModal = async (caseId: number, filename: string, caseData: any) => {
    setLoadSuccess(null);
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
      setRawFileContent(null);  // Backend doesn't store raw_content; use Q_case_details from extractedData for document details
      setCurrentFile({
        name: filename,
        size: 0,
        type: '',
        case_id: caseId
      });
      setLoadSuccess(`Loaded "${filename}" to chat. You can ask questions or generate draft replies.`);
      onSwitchToChat?.();
    } catch (err) {
      console.error('Load case for query error:', err);
      setError('Failed to load case info. Please try again.');
    }
  };

  if (loading) {
    return (
      <div className="case-files-panel">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="case-files-panel">
        <div className="error-state">
          <p>{error}</p>
          <GradientButton onClick={loadCases} size="sm" variant="primary">
            Retry
          </GradientButton>
        </div>
      </div>
    );
  }

  return (
    <div className="case-files-panel">
      <div className="panel-header">
        <h2>Processed Case Files</h2>
        <p className="panel-description">
          All processed case files (TXT, TMO PDF, RCC PDF). Same case number shows latest only.
        </p>
      </div>

      {filteredCases.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📋</div>
          <h3>{cases.length === 0 ? 'No case files yet' : 'No matching case files'}</h3>
          <p>{cases.length === 0 ? 'Upload case files in the chat to process them' : `No results for "${searchQuery}"`}</p>
        </div>
      ) : (
        <div className="case-table-container">
          <table className="case-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>File type</th>
                <th>Case number</th>
                <th>Source</th>
                <th>Location</th>
                <th>Date received</th>
                <th>Processing time</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredCases.map((caseFile) => (
                <tr key={caseFile.id}>
                  <td className="filename-cell" data-label="Filename" title={caseFile.original_filename}>
                    {caseFile.original_filename}
                  </td>
                  <td data-label="File type">
                    <span className={`file-type-badge ${caseFile.file_type}`}>
                      {formatFileType(caseFile.file_type)}
                    </span>
                  </td>
                  <td data-label="Case number">{caseFile.C_case_number || '-'}</td>
                  <td data-label="Source">{caseFile.B_source || '-'}</td>
                  <td data-label="Location">{caseFile.H_location || '-'}</td>
                  <td data-label="Date received">{caseFile.A_date_received || '-'}</td>
                  <td data-label="Processing time">{caseFile.processing_time}</td>
                  <td data-label="Action">
                    <GradientButton
                      onClick={() => setDetailCaseId(caseFile.id)}
                      size="sm"
                      variant="outline"
                      className="case-action-btn"
                      style={{ minWidth: '64px' }}
                    >
                      Details
                    </GradientButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {loadSuccess && (
        <div className="panel-load-success">
          {loadSuccess}
        </div>
      )}
      <div className="panel-footer">
        <p>{filteredCases.length === cases.length ? `${cases.length} case file(s)` : `${filteredCases.length} of ${cases.length} case file(s)`} (deduplicated by case number, latest only)</p>
      </div>

      <CaseDetailModal
        caseId={detailCaseId}
        onClose={() => setDetailCaseId(null)}
        onLoadForQuery={handleLoadForQueryFromModal}
      />
    </div>
  );
};

export default CaseFilesPanel;
