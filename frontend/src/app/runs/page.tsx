'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

interface RunSummary {
  run_id: string;
  timestamp: string;
  purpose: string;
  date_range: { start: string; end: string };
  total_signals: number;
  trade_signals: number;
  models: { [key: string]: string };
  has_backtest: boolean;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchRuns();
  }, []);

  const fetchRuns = async () => {
    try {
      const response = await fetch('/api/runs');
      if (response.ok) {
        const data = await response.json();
        setRuns(data.runs);
      }
    } catch (error) {
      console.error('Failed to fetch runs:', error);
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Run History</h1>

      <div className="card">
        <table className="min-w-full divide-y divide-gray-200">
          <thead>
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Run ID
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Purpose
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Date Range
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Signals
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Model
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Backtest
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {runs.map((run) => (
              <tr key={run.run_id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <Link
                    href={`/runs/${run.run_id}`}
                    className="text-primary-600 hover:text-primary-800 font-medium"
                  >
                    {run.run_id.substring(0, 30)}...
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <span className="badge badge-info">{run.purpose}</span>
                </td>
                <td className="px-4 py-3 text-sm text-gray-600">
                  {run.date_range.start} to {run.date_range.end}
                </td>
                <td className="px-4 py-3 text-sm">
                  <span className="text-green-600 font-medium">
                    {run.trade_signals}
                  </span>
                  <span className="text-gray-400"> / {run.total_signals}</span>
                </td>
                <td className="px-4 py-3 text-sm text-gray-600">
                  {run.models.batch_score}
                </td>
                <td className="px-4 py-3">
                  {run.has_backtest ? (
                    <span className="badge badge-success">Yes</span>
                  ) : (
                    <span className="badge badge-warning">No</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
