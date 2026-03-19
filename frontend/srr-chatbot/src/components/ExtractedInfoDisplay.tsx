import React from 'react';
import { FileText, Calendar, User, MapPin, Phone, AlertTriangle, Edit3 } from 'lucide-react';
import { ExtractedData } from '../types';

const FIELD_CONFIG: Array<{ key: keyof ExtractedData; label: string; icon?: React.ReactNode }> = [
  { key: 'A_date_received', label: 'Date Received (A)', icon: <Calendar size={12} style={{ display: 'inline', marginRight: '4px' }} /> },
  { key: 'B_source', label: 'Source (B)' },
  { key: 'C_case_number', label: 'Case Number (C)' },
  { key: 'D_type', label: 'Case Type (D)' },
  { key: 'E_caller_name', label: 'Caller Name (E)', icon: <User size={12} style={{ display: 'inline', marginRight: '4px' }} /> },
  { key: 'F_contact_no', label: 'Contact Number (F)', icon: <Phone size={12} style={{ display: 'inline', marginRight: '4px' }} /> },
  { key: 'G_slope_no', label: 'Slope Number (G)', icon: <AlertTriangle size={12} style={{ display: 'inline', marginRight: '4px' }} /> },
  { key: 'H_location', label: 'Location (H)', icon: <MapPin size={12} style={{ display: 'inline', marginRight: '4px' }} /> },
  { key: 'I_nature_of_request', label: 'Nature of Request (I)' },
  { key: 'J_subject_matter', label: 'Subject Matter (J)' },
  { key: 'K_10day_rule_due_date', label: '10-Day Rule Due Date (K)', icon: <Calendar size={12} style={{ display: 'inline', marginRight: '4px' }} /> },
  { key: 'L_icc_interim_due', label: 'ICC Interim Reply Due Date (L)' },
  { key: 'M_icc_final_due', label: 'ICC Final Reply Due Date (M)' },
  { key: 'N_works_completion_due', label: 'Works Completion Due Date (N)' },
  { key: 'O1_fax_to_contractor', label: 'Fax to Contractor Date (O1)' },
  { key: 'O2_email_send_time', label: 'Email Send Time (O2)' },
  { key: 'P_fax_pages', label: 'Fax Pages (P)' },
  { key: 'Q_case_details', label: 'Case Details (Q)' },
];

interface ExtractedInfoDisplayProps {
  data: ExtractedData;
  caseId?: number | null;
  onCorrectField?: (fieldName: string, incorrectValue: string) => void;
}

const ExtractedInfoDisplay: React.FC<ExtractedInfoDisplayProps> = ({ data, caseId, onCorrectField }) => {
  const formatValue = (value: string | undefined | null) => {
    return value && value.trim() ? value : 'Not provided';
  };

  const isEmptyValue = (value: string | undefined | null) => {
    return !value || !value.trim();
  };

  return (
    <div className="extracted-info">
      <h3>
        <FileText size={16} />
        Extracted Case Information
      </h3>
      <div className="info-grid">
        {FIELD_CONFIG.map(({ key, label, icon }) => {
          const value = data[key];
          return (
            <div key={key} className="info-item">
              <div className="info-label">
                {icon}
                {label}
                {onCorrectField && (
                  <button
                    type="button"
                    className="correction-btn"
                    onClick={() => onCorrectField(key, String(value ?? ''))}
                    title="Report correction"
                  >
                    <Edit3 size={12} style={{ display: 'inline', marginRight: '2px' }} />
                    Correct
                  </button>
                )}
              </div>
              <div className={`info-value ${isEmptyValue(value) ? 'empty' : ''}`}>
                {formatValue(value)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ExtractedInfoDisplay;