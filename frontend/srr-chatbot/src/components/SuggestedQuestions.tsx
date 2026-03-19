/**
 * Suggested actions component.
 * Shows three draft-reply buttons: Interim, Final, Wrong Referral.
 * Styled with SRR red-orange theme.
 */
import React from 'react';
import './SuggestedQuestions.css';

interface SuggestedQuestionsProps {
  onQuestionClick: (type: string, skipQuestions?: boolean) => void;
  disabled?: boolean;
  /** When true, compact layout for inline chat message bubble */
  embedded?: boolean;
  /** When true, use smaller action buttons */
  compact?: boolean;
  /** When true, show End button to exit draft reply flow */
  showEndButton?: boolean;
  /** Called when user clicks End */
  onEndDraft?: () => void;
}

interface Question {
  id: string;
  label_en: string;
  label_zh: string;
  emoji: string;
}

const questions: Question[] = [
  {
    id: 'interim',
    label_en: 'Draft Interim Reply',
    label_zh: '草拟过渡回复',
    emoji: '📝'
  },
  {
    id: 'final',
    label_en: 'Draft Final Reply',
    label_zh: '草拟最终回复',
    emoji: '✅'
  },
  {
    id: 'wrong_referral',
    label_en: 'Draft Wrong Referral Reply',
    label_zh: '草拟错误转介回复',
    emoji: '🔄'
  }
];

const SuggestedQuestions: React.FC<SuggestedQuestionsProps> = ({ 
  onQuestionClick, 
  disabled = false,
  embedded = false,
  compact = false,
  showEndButton = false,
  onEndDraft
}) => {
  return (
    <div className={`suggested-questions-container ${embedded ? 'suggested-questions-embedded' : ''} ${compact ? 'suggested-questions-compact' : ''}`}>
      <div className="suggested-questions-header">
        <span className="header-icon">💬</span>
        <span className="header-text">
          Suggested Actions
        </span>
      </div>
      
      <div className="suggested-questions-grid">
        {questions.map((question) => (
          <div key={question.id} className="question-item">
            <button
              className={`suggested-question-btn ${compact ? 'suggested-question-btn-compact' : ''}`}
              onClick={() => onQuestionClick(question.id, false)}
              disabled={disabled}
            >
              <span className="question-emoji">{question.emoji}</span>
              <span className="question-label">{question.label_en}</span>
            </button>
            <button
              className={`direct-generate-btn ${compact ? 'direct-generate-btn-compact' : ''}`}
              onClick={() => onQuestionClick(question.id, true)}
              disabled={disabled}
              title="Skip questions and generate directly from case data"
            >
              ⚡ Direct
            </button>
          </div>
        ))}
        {showEndButton && (
          <div className="question-item question-item-end">
            <button
              type="button"
              className="suggested-question-end-btn"
              onClick={() => onEndDraft?.()}
              disabled={disabled}
              title="End draft reply flow and return to normal chat"
            >
              ✕ End / 結束
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default SuggestedQuestions;
