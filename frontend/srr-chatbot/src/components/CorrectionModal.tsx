import React, { useState } from 'react';
import { X } from 'lucide-react';
import { saveUserFeedback } from '../services/api';
import './CorrectionModal.css';

export interface CorrectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  fieldName: string;
  fieldLabel: string;
  incorrectValue: string;
  caseId?: number | null;
  sourceText?: string;
}

const CorrectionModal: React.FC<CorrectionModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  fieldName,
  fieldLabel,
  incorrectValue,
  caseId,
  sourceText,
}) => {
  const [correctValue, setCorrectValue] = useState('');
  const [note, setNote] = useState('');
  const [scope, setScope] = useState<'case' | 'global'>(caseId ? 'case' : 'global');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    if (!correctValue.trim()) {
      setError('Please enter the correct value');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await saveUserFeedback({
        case_id: caseId ?? undefined,
        field_name: fieldName,
        incorrect_value: incorrectValue || undefined,
        correct_value: correctValue.trim(),
        note: note.trim() || undefined,
        source_text: sourceText,
        scope,
      });
      onSuccess?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save correction');
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    setCorrectValue('');
    setNote('');
    setError(null);
    onClose();
  };

  return (
    <div className="modal-overlay correction-modal-overlay" onClick={(e) => { e.stopPropagation(); handleClose(); }}>
      <div className="modal-content correction-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Submit correction / 提交纠错</h2>
          <button className="modal-close" onClick={handleClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>
        <div className="modal-body">
          <div className="correction-field">
            <label>Field / 字段</label>
            <div className="correction-readonly">{fieldLabel}</div>
          </div>
          <div className="correction-field">
            <label>Current value (incorrect) / 当前值（错误）</label>
            <div className="correction-readonly">{incorrectValue || '(empty)'}</div>
          </div>
          <div className="correction-field">
            <label>Correct value / 正确值 <span className="required">*</span></label>
            <input
              type="text"
              value={correctValue}
              onChange={(e) => setCorrectValue(e.target.value)}
              placeholder="Enter correct value"
              className="correction-input"
            />
          </div>
          <div className="correction-field">
            <label>Note (optional) / 备注（可选）</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. This case is tree trimming complaint"
              className="correction-textarea"
              rows={2}
            />
          </div>
          <div className="correction-field">
            <label>Scope / 适用范围</label>
            <div className="correction-scope">
              <label className="scope-option">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === 'case'}
                  onChange={() => setScope('case')}
                />
                Case only / 仅本案
              </label>
              <label className="scope-option">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === 'global'}
                  onChange={() => setScope('global')}
                />
                Global (for future similar cases) / 全局
              </label>
            </div>
          </div>
          {error && <div className="correction-error">{error}</div>}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn-secondary" onClick={handleClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleSubmit}
            disabled={submitting || !correctValue.trim()}
          >
            {submitting ? 'Submitting...' : 'Submit'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default CorrectionModal;
