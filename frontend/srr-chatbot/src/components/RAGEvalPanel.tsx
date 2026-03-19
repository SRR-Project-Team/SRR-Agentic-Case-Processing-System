import React, { useMemo, useState } from 'react';
import { RAGEvalData, RetrievalMetric } from '../services/api';

interface RAGEvalPanelProps {
  data: RAGEvalData;
}

const clampPct = (v: number): number => {
  if (!Number.isFinite(v)) return 0;
  const pct = v <= 1 ? v * 100 : v;
  return Math.max(0, Math.min(100, Math.round(pct)));
};

const SOURCE_LABELS: Record<string, string> = {
  historical_cases: 'Historical Cases',
  tree_inventory: 'Tree Inventory',
  knowledge_base: 'Knowledge Base',
  other: 'Other',
};

type ExpandedMetric = 'context' | 'faithfulness' | 'coverage' | null;

const RAGEvalPanel: React.FC<RAGEvalPanelProps> = ({ data }) => {
  const [expanded, setExpanded] = useState(false);
  const [expandedMetric, setExpandedMetric] = useState<ExpandedMetric>(null);
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);

  const quality = data.quality_score ?? 0;
  const contextRel = data.context_relevance ?? 0;
  const faithfulness = data.answer_faithfulness ?? 0;
  const coverage = data.answer_coverage ?? 0;

  const metrics = useMemo(() => data.retrieval_metrics ?? [], [data.retrieval_metrics]);

  const bySource = useMemo(() => {
    const map = new Map<string, RetrievalMetric[]>();
    metrics.forEach((r) => {
      const key = r.source || 'other';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(r);
    });
    return Array.from(map.entries());
  }, [metrics]);

  const contextFormula = useMemo(() => {
    if (metrics.length === 0) return null;
    const pcts = metrics.map((m) => clampPct(m.relevance_score ?? 0));
    const avg = pcts.reduce((a, b) => a + b, 0) / pcts.length;
    return { pcts, avg: Number.isFinite(avg) ? avg : 0 };
  }, [metrics]);

  const toggleMetric = (m: ExpandedMetric) => {
    setExpandedMetric((prev) => (prev === m ? null : m));
  };

  return (
    <div className="rag-eval-panel">
      <button
        type="button"
        className="rag-eval-toggle"
        onClick={() => setExpanded((prev) => !prev)}
      >
        <span>RAG Quality {clampPct(quality)}%</span>
        <span>{expanded ? 'Hide details' : 'Show details'}</span>
      </button>

      {expanded && (
        <div className="rag-eval-details">
          <div className="rag-eval-topline">
            <button
              type="button"
              className="rag-eval-metric-btn"
              onClick={() => toggleMetric('context')}
              title="Click for explanation"
            >
              Context {clampPct(contextRel)}%
            </button>
            <button
              type="button"
              className="rag-eval-metric-btn"
              onClick={() => toggleMetric('faithfulness')}
              title="Click for explanation"
            >
              Faithfulness {clampPct(faithfulness)}%
            </button>
            <button
              type="button"
              className="rag-eval-metric-btn"
              onClick={() => toggleMetric('coverage')}
              title="Click for explanation"
            >
              Coverage {clampPct(coverage)}%
            </button>
            {data.total_latency_ms != null && (
              <span className="rag-eval-metric-static">Latency {data.total_latency_ms}ms</span>
            )}
          </div>

          {expandedMetric === 'context' && (
            <div className="rag-eval-metric-expand">
              <div className="rag-eval-metric-desc">
                <strong>Context</strong> = 所有检索文档 relevance 的平均值。每个文档的 rel 参与此计算。
              </div>
              {contextFormula && (
                <div className="rag-eval-metric-formula">
                  ({contextFormula.pcts.join('% + ')}) ÷ {metrics.length} ≈ {Math.round(contextFormula.avg)}%
                </div>
              )}
              <div className="rag-eval-docs-by-source">
                {bySource.map(([source, docs]) => (
                  <div key={source} className="rag-eval-source-group">
                    <div className="rag-eval-source-header">
                      <span>{SOURCE_LABELS[source] ?? source}</span>
                      <span>{docs.length} docs</span>
                    </div>
                    {docs.map((item) => (
                      <DocRow
                        key={item.doc_id}
                        item={item}
                        expandedDocId={expandedDocId}
                        onToggleSnippet={() =>
                          setExpandedDocId((prev) => (prev === item.doc_id ? null : item.doc_id))
                        }
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}

          {expandedMetric === 'faithfulness' && (
            <div className="rag-eval-metric-expand">
              <div className="rag-eval-metric-desc">
                答案与上下文的关键词重叠
              </div>
              {(data.faithfulness_matched?.length ?? 0) > 0 ? (
                <>
                  <div className="rag-eval-keyword-tags">
                    {data.faithfulness_matched!.map((kw) => (
                      <span key={kw} className="rag-eval-keyword-tag matched">
                        {kw}
                      </span>
                    ))}
                  </div>
                  {data.faithfulness_total != null && data.faithfulness_total > 0 && (
                    <div className="rag-eval-keyword-meta">
                      上下文关键词总数: {data.faithfulness_total}
                    </div>
                  )}
                </>
              ) : (
                <div className="rag-eval-keyword-empty">无匹配关键词（或使用 RAGAS 评估）</div>
              )}
            </div>
          )}

          {expandedMetric === 'coverage' && (
            <div className="rag-eval-metric-expand">
              <div className="rag-eval-metric-desc">
                问题关键词在答案中的覆盖
              </div>
              {(data.coverage_matched?.length ?? 0) > 0 || (data.coverage_missed?.length ?? 0) > 0 ? (
                <div className="rag-eval-keyword-tags">
                  {data.coverage_matched?.map((kw) => (
                    <span key={`${kw}-ok`} className="rag-eval-keyword-tag matched" title="已覆盖">
                      ✓ {kw}
                    </span>
                  ))}
                  {data.coverage_missed?.map((kw) => (
                    <span key={`${kw}-miss`} className="rag-eval-keyword-tag missed" title="未覆盖">
                      ✗ {kw}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="rag-eval-keyword-empty">无关键词数据（或使用 RAGAS 评估）</div>
              )}
            </div>
          )}

          {expandedMetric === null && (
            <>
              {bySource.map(([source, docs]) => (
                <div key={source} className="rag-eval-source-row">
                  <div className="rag-eval-source-header">
                    <span>{SOURCE_LABELS[source] ?? source}</span>
                    <span>{docs.length} docs</span>
                  </div>
                  <div className="rag-eval-source-bar">
                    <span
                      style={{
                        width: `${clampPct(
                          docs.reduce((s, d) => s + (d.relevance_score ?? 0), 0) / docs.length
                        )}%`,
                      }}
                    />
                  </div>
                  {docs.map((item) => (
                    <DocRow
                      key={item.doc_id}
                      item={item}
                      expandedDocId={expandedDocId}
                      onToggleSnippet={() =>
                        setExpandedDocId((prev) => (prev === item.doc_id ? null : item.doc_id))
                      }
                    />
                  ))}
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
};

interface DocRowProps {
  item: RetrievalMetric;
  expandedDocId: string | null;
  onToggleSnippet: () => void;
}

const DocRow: React.FC<DocRowProps> = ({ item, expandedDocId, onToggleSnippet }) => {
  const showSnippet = expandedDocId === item.doc_id;
  const hasSnippet = !!item.snippet?.trim();

  return (
    <div className="rag-eval-doc-row">
      <button
        type="button"
        className="rag-eval-doc-header"
        onClick={onToggleSnippet}
        disabled={!hasSnippet}
      >
        <div className="rag-eval-doc-title">
          {item.doc_title || item.doc_id}
          {item.used_in_answer ? ' (used)' : ''}
        </div>
        <div className="rag-eval-doc-score">
          sim {clampPct(item.similarity_score)}% / rel {clampPct(item.relevance_score)}%
        </div>
        {hasSnippet && (
          <span className="rag-eval-doc-preview-hint">
            {showSnippet ? '▼ Hide preview' : '▶ Preview snippet'}
          </span>
        )}
      </button>
      {showSnippet && hasSnippet && (
        <div className="rag-eval-doc-snippet">{item.snippet}</div>
      )}
    </div>
  );
};

export default RAGEvalPanel;
