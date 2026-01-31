'use client';

import { useState } from 'react';

interface Evidence {
  quote: string;
  speaker: string;
  section: string;
  paragraph_index?: number;
}

interface AnalysisResultProps {
  result: any;
  isLoading: boolean;
  onFullAudit: () => void;
}

export function AnalysisResult({
  result,
  isLoading,
  onFullAudit,
}: AnalysisResultProps) {
  const [showPrompt, setShowPrompt] = useState(false);
  const [showModelInfo, setShowModelInfo] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Analyzing...</p>
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-gray-500">
          Select an earnings call to see analysis results.
        </p>
      </div>
    );
  }

  const getScoreColor = (score: number) => {
    if (score >= 0.7) return 'score-high';
    if (score >= 0.5) return 'score-medium';
    return 'score-low';
  };

  return (
    <div className="space-y-4">
      <h2 className="card-header">Analysis Result</h2>

      {/* Header Info */}
      <div className="p-4 bg-gray-50 rounded-md">
        <div className="flex justify-between items-center">
          <div>
            <span className="font-bold text-xl">{result.symbol}</span>
            <span className="text-gray-500 ml-2">{result.event_date}</span>
          </div>
          <span className="badge badge-info">{result.mode}</span>
        </div>
      </div>

      {/* Score Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className={`p-4 rounded-md text-center ${getScoreColor(result.score)}`}>
          <div className="text-2xl font-bold">{(result.score * 100).toFixed(0)}%</div>
          <div className="text-sm">Score</div>
        </div>
        <div
          className={`p-4 rounded-md text-center ${
            result.trade_candidate || result.trade_long_final
              ? 'bg-green-50 text-green-600'
              : 'bg-gray-50 text-gray-600'
          }`}
        >
          <div className="text-2xl font-bold">
            {result.trade_candidate || result.trade_long_final ? '✓ Long' : '✗ No Trade'}
          </div>
          <div className="text-sm">Decision</div>
        </div>
        <div className="p-4 rounded-md text-center bg-blue-50 text-blue-600">
          <div className="text-2xl font-bold">
            {((result.confidence_calibrated || result.confidence || result.score) * 100).toFixed(0)}%
          </div>
          <div className="text-sm">Confidence</div>
        </div>
      </div>

      {/* Key Flags */}
      {result.key_flags && (
        <div className="space-y-2">
          <h3 className="font-medium text-gray-700">Key Signals</h3>
          <div className="flex flex-wrap gap-2">
            {result.key_flags.guidance_positive && (
              <span className="badge badge-success">Guidance Positive</span>
            )}
            {result.key_flags.revenue_beat && (
              <span className="badge badge-success">Revenue Beat</span>
            )}
            {result.key_flags.guidance_raised && (
              <span className="badge badge-success">Guidance Raised</span>
            )}
            {result.key_flags.margin_concern && (
              <span className="badge badge-danger">Margin Concern</span>
            )}
            {result.key_flags.buyback_announced && (
              <span className="badge badge-info">Buyback</span>
            )}
          </div>
        </div>
      )}

      {/* Evidence */}
      <div className="space-y-2">
        <h3 className="font-medium text-gray-700">
          Evidence ({result.evidence_count || result.evidence_snippets?.length || 0})
        </h3>
        <div className="space-y-3">
          {(result.evidence_snippets || []).map((evidence: Evidence, idx: number) => (
            <div key={idx} className="p-3 bg-gray-50 rounded-md border-l-4 border-primary-500">
              <p className="text-gray-800 italic">"{evidence.quote}"</p>
              <p className="text-sm text-gray-500 mt-1">
                — {evidence.speaker}, {evidence.section}
                {evidence.paragraph_index !== undefined && `, ¶${evidence.paragraph_index}`}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* No Trade Reason */}
      {result.no_trade_reason && (
        <div className="p-3 bg-yellow-50 rounded-md border-l-4 border-yellow-500">
          <p className="font-medium text-yellow-700">No Trade Reason:</p>
          <p className="text-yellow-600">{result.no_trade_reason}</p>
        </div>
      )}

      {/* Expandable Sections */}
      <div className="space-y-2">
        {/* Model Info */}
        <button
          onClick={() => setShowModelInfo(!showModelInfo)}
          className="w-full text-left px-4 py-2 bg-gray-100 rounded-md hover:bg-gray-200 flex justify-between items-center"
        >
          <span>Model Info</span>
          <span>{showModelInfo ? '▲' : '▼'}</span>
        </button>
        {showModelInfo && (
          <div className="p-4 bg-gray-50 rounded-md text-sm space-y-2">
            <p><strong>Model:</strong> {result.model}</p>
            <p><strong>Mode:</strong> {result.mode}</p>
            <p><strong>Prompt Version:</strong> {result.prompt_version || result.prompt_info?.template_id}</p>
            <p><strong>Token Usage:</strong></p>
            <ul className="ml-4">
              <li>Input: {result.token_usage?.input?.toLocaleString()}</li>
              <li>Output: {result.token_usage?.output?.toLocaleString()}</li>
              <li>Total: {result.token_usage?.total?.toLocaleString()}</li>
            </ul>
            <p><strong>Cost:</strong> ${result.cost_usd?.toFixed(4)}</p>
            <p><strong>Latency:</strong> {result.latency_ms?.toLocaleString()}ms</p>
          </div>
        )}

        {/* Prompt Info (for full_audit) */}
        {result.prompt_info && (
          <>
            <button
              onClick={() => setShowPrompt(!showPrompt)}
              className="w-full text-left px-4 py-2 bg-gray-100 rounded-md hover:bg-gray-200 flex justify-between items-center"
            >
              <span>Prompt Info</span>
              <span>{showPrompt ? '▲' : '▼'}</span>
            </button>
            {showPrompt && (
              <div className="p-4 bg-gray-50 rounded-md text-sm space-y-2">
                <p><strong>Template ID:</strong> {result.prompt_info.template_id}</p>
                <p><strong>Hash:</strong> {result.prompt_info.prompt_hash}</p>
                <div>
                  <p className="font-medium">Rendered Prompt:</p>
                  <pre className="mt-2 p-2 bg-gray-100 rounded text-xs overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                    {result.prompt_info.rendered_prompt}
                  </pre>
                </div>
              </div>
            )}
          </>
        )}

        {/* Raw Output */}
        <button
          onClick={() => setShowRaw(!showRaw)}
          className="w-full text-left px-4 py-2 bg-gray-100 rounded-md hover:bg-gray-200 flex justify-between items-center"
        >
          <span>Raw Output</span>
          <span>{showRaw ? '▲' : '▼'}</span>
        </button>
        {showRaw && (
          <pre className="p-4 bg-gray-800 text-green-400 rounded-md text-xs overflow-x-auto max-h-64 overflow-y-auto">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </div>

      {/* Full Audit Button */}
      {result.mode === 'batch_score' && (
        <button
          onClick={onFullAudit}
          className="w-full btn btn-primary"
        >
          Run Full Audit Analysis
        </button>
      )}
    </div>
  );
}
