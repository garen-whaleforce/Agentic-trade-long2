'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';

interface RunDetail {
  run_id: string;
  config: any;
  summary: any;
  backtest_result: any;
}

export default function RunDetailPage() {
  const params = useParams();
  const runId = params.runId as string;

  const [run, setRun] = useState<RunDetail | null>(null);
  const [signals, setSignals] = useState<any[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchRunDetail();
    fetchSignals();
  }, [runId]);

  const fetchRunDetail = async () => {
    try {
      const response = await fetch(`/api/runs/${runId}`);
      if (response.ok) {
        const data = await response.json();
        setRun(data);
      }
    } catch (error) {
      console.error('Failed to fetch run:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchSignals = async () => {
    try {
      const response = await fetch(`/api/runs/${runId}/signals?limit=50`);
      if (response.ok) {
        const data = await response.json();
        setSignals(data.signals);
      }
    } catch (error) {
      console.error('Failed to fetch signals:', error);
    }
  };

  const fetchEventDetail = async (eventId: string) => {
    try {
      const response = await fetch(`/api/runs/${runId}/llm/${eventId}`);
      if (response.ok) {
        const data = await response.json();
        setSelectedEvent(data);
      }
    } catch (error) {
      console.error('Failed to fetch event:', error);
    }
  };

  if (isLoading || !run) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">
          Run: {run.run_id.substring(0, 40)}...
        </h1>
        <span className="badge badge-info">{run.config.purpose}</span>
      </div>

      {/* Config & Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Configuration */}
        <div className="card">
          <h2 className="card-header">Configuration</h2>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-500">Date Range:</dt>
              <dd>
                {run.config.date_range.start} to {run.config.date_range.end}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Batch Score Model:</dt>
              <dd>{run.config.models?.batch_score}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Prompt Version:</dt>
              <dd>{run.config.prompt_versions?.batch_score}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Score Threshold:</dt>
              <dd>{run.config.thresholds?.score_threshold}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Evidence Min:</dt>
              <dd>{run.config.thresholds?.evidence_min_count}</dd>
            </div>
          </dl>
        </div>

        {/* Summary */}
        <div className="card">
          <h2 className="card-header">Summary</h2>
          {run.summary && (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">Total Events:</dt>
                <dd>{run.summary.total_events}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Trade Signals:</dt>
                <dd className="text-green-600 font-medium">
                  {run.summary.trade_signals}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">No Trade:</dt>
                <dd>{run.summary.no_trade_signals}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Total Cost:</dt>
                <dd>${run.summary.total_cost_usd?.toFixed(2)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">Avg Latency:</dt>
                <dd>{run.summary.avg_latency_ms}ms</dd>
              </div>
            </dl>
          )}
        </div>
      </div>

      {/* Backtest Results */}
      {run.backtest_result && (
        <div className="card">
          <h2 className="card-header">
            Backtest Results (from Whaleforce API)
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-4 bg-green-50 rounded-md text-center">
              <div className="text-2xl font-bold text-green-600">
                {(run.backtest_result.performance.cagr * 100).toFixed(1)}%
              </div>
              <div className="text-sm text-gray-500">CAGR</div>
            </div>
            <div className="p-4 bg-blue-50 rounded-md text-center">
              <div className="text-2xl font-bold text-blue-600">
                {run.backtest_result.performance.sharpe_ratio.toFixed(2)}
              </div>
              <div className="text-sm text-gray-500">Sharpe</div>
            </div>
            <div className="p-4 bg-purple-50 rounded-md text-center">
              <div className="text-2xl font-bold text-purple-600">
                {(run.backtest_result.performance.win_rate * 100).toFixed(1)}%
              </div>
              <div className="text-sm text-gray-500">Win Rate</div>
            </div>
            <div className="p-4 bg-red-50 rounded-md text-center">
              <div className="text-2xl font-bold text-red-600">
                {(run.backtest_result.performance.max_drawdown * 100).toFixed(1)}%
              </div>
              <div className="text-sm text-gray-500">Max DD</div>
            </div>
          </div>
        </div>
      )}

      {/* Signals List */}
      <div className="card">
        <h2 className="card-header">Signals</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  Event
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  Symbol
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  Score
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  Decision
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  Evidence
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {signals.map((signal) => (
                <tr key={signal.event_id} className="hover:bg-gray-50">
                  <td className="px-4 py-2 text-sm">{signal.event_id}</td>
                  <td className="px-4 py-2 text-sm font-medium">
                    {signal.symbol}
                  </td>
                  <td className="px-4 py-2 text-sm">
                    {(signal.score * 100).toFixed(0)}%
                  </td>
                  <td className="px-4 py-2">
                    {signal.trade_long ? (
                      <span className="badge badge-success">Long</span>
                    ) : (
                      <span className="badge badge-warning">No Trade</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-sm">{signal.evidence_count}</td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => fetchEventDetail(signal.event_id)}
                      className="text-primary-600 hover:text-primary-800 text-sm"
                    >
                      View Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Event Detail Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-bold">
                  Event: {selectedEvent.event_id}
                </h3>
                <button
                  onClick={() => setSelectedEvent(null)}
                  className="text-gray-500 hover:text-gray-700"
                >
                  Close
                </button>
              </div>

              {/* Request Info */}
              <div className="mb-4">
                <h4 className="font-medium text-gray-700 mb-2">LLM Request</h4>
                <div className="p-4 bg-gray-50 rounded-md text-sm space-y-2">
                  <p>
                    <strong>Model:</strong> {selectedEvent.request.model}
                  </p>
                  <p>
                    <strong>Prompt ID:</strong>{' '}
                    {selectedEvent.request.prompt_template_id}
                  </p>
                  <p>
                    <strong>Hash:</strong> {selectedEvent.request.prompt_hash}
                  </p>
                  <details>
                    <summary className="cursor-pointer text-primary-600">
                      View Rendered Prompt
                    </summary>
                    <pre className="mt-2 p-2 bg-gray-100 rounded text-xs whitespace-pre-wrap">
                      {selectedEvent.request.rendered_prompt}
                    </pre>
                  </details>
                </div>
              </div>

              {/* Response Info */}
              <div className="mb-4">
                <h4 className="font-medium text-gray-700 mb-2">LLM Response</h4>
                <div className="p-4 bg-gray-50 rounded-md text-sm space-y-2">
                  <p>
                    <strong>Score:</strong>{' '}
                    {selectedEvent.response.raw_output.score}
                  </p>
                  <p>
                    <strong>Trade:</strong>{' '}
                    {selectedEvent.response.raw_output.trade_candidate
                      ? 'Yes'
                      : 'No'}
                  </p>
                  <p>
                    <strong>Tokens:</strong>{' '}
                    {selectedEvent.response.token_usage.total}
                  </p>
                  <p>
                    <strong>Cost:</strong> $
                    {selectedEvent.response.cost_usd.toFixed(4)}
                  </p>
                  <p>
                    <strong>Latency:</strong>{' '}
                    {selectedEvent.response.latency_ms}ms
                  </p>
                  <details>
                    <summary className="cursor-pointer text-primary-600">
                      View Raw Output
                    </summary>
                    <pre className="mt-2 p-2 bg-gray-800 text-green-400 rounded text-xs whitespace-pre-wrap">
                      {JSON.stringify(
                        selectedEvent.response.raw_output,
                        null,
                        2
                      )}
                    </pre>
                  </details>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
