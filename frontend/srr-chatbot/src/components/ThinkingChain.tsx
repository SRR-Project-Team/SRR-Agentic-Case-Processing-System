import React, { useMemo, useState } from 'react';
import { ThinkingStepEvent } from '../services/api';

interface ThinkingChainProps {
  steps: ThinkingStepEvent[];
  isStreaming?: boolean;
}

const stepLabel: Record<ThinkingStepEvent['step_type'], string> = {
  intent: 'Intent',
  decompose: 'Decompose',
  retrieve: 'Retrieve',
  synthesize: 'Synthesize',
  evaluate: 'Evaluate',
};

const ThinkingChain: React.FC<ThinkingChainProps> = ({ steps, isStreaming = false }) => {
  const [expanded, setExpanded] = useState(false);
  const orderedSteps = useMemo(
    () => [...steps].sort((a, b) => (a.step_id ?? 0) - (b.step_id ?? 0)),
    [steps]
  );

  if (orderedSteps.length === 0) return null;

  return (
    <div className="thinking-chain">
      <button
        type="button"
        className="thinking-chain-toggle"
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span>{isStreaming ? 'Reasoning in progress' : 'Reasoning summary'}</span>
        <span>{expanded ? 'Hide' : `Show ${orderedSteps.length} step(s)`}</span>
      </button>
      {expanded && (
        <div className="thinking-chain-steps">
          {orderedSteps.map((step) => (
            <div key={`${step.step_id}-${step.title}`} className="thinking-chain-step">
              <div className="thinking-chain-step-header">
                <strong>{step.step_id}. {stepLabel[step.step_type] ?? step.step_type}</strong>
                {step.duration_ms != null && <span>{step.duration_ms}ms</span>}
              </div>
              <div className="thinking-chain-step-title">{step.title}</div>
              <div className="thinking-chain-step-content">{step.content}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default ThinkingChain;
