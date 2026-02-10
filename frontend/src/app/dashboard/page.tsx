'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { KpiCards } from '@/components/paper-trading/KpiCards';
import { PositionsTable } from '@/components/paper-trading/PositionsTable';
import { SignalHistory } from '@/components/paper-trading/SignalHistory';

type TabId = 'overview' | 'positions' | 'signals' | 'config';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '';

export default function PaperTradingDashboard() {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [summary, setSummary] = useState<any>(null);
  const [positions, setPositions] = useState<{ open: any[]; closed: any[] }>({
    open: [],
    closed: [],
  });
  const [config, setConfig] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const REFRESH_INTERVAL_MS = 60_000; // 60 seconds

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryRes, positionsRes, configRes, healthRes] = await Promise.all([
        fetch(`${API_BASE}/api/paper-trading/summary`),
        fetch(`${API_BASE}/api/paper-trading/positions`),
        fetch(`${API_BASE}/api/paper-trading/config`),
        fetch(`${API_BASE}/api/paper-trading/health`),
      ]);

      if (!summaryRes.ok) throw new Error(`Summary: ${summaryRes.status}`);
      if (!positionsRes.ok) throw new Error(`Positions: ${positionsRes.status}`);

      setSummary(await summaryRes.json());
      setPositions(await positionsRes.json());
      if (configRes.ok) setConfig(await configRes.json());
      if (healthRes.ok) setHealth(await healthRes.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
      setLastRefresh(new Date());
    }
  }, []);

  // Initial fetch + auto-refresh every 60s
  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchData]);

  const tabs: { id: TabId; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'positions', label: 'Positions' },
    { id: 'signals', label: 'Signals' },
    { id: 'config', label: 'Config' },
  ];

  const MONO = { fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace" };

  return (
    <div className="space-y-5">
      {/* Page header */}
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Paper Trading</h2>
          <p className="text-xs text-slate-500 mt-0.5" style={MONO}>
            V9 G2 TP10{config?.half_weight_enabled ? ` | Half Weight until ${config.half_weight_until}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-[10px] text-slate-400" style={MONO}>
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchData}
            disabled={loading}
            className="px-3 py-1.5 text-xs text-slate-600 border border-slate-300 rounded-sm hover:bg-slate-50 transition-colors disabled:opacity-50"
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="border border-rose-200 bg-rose-50 rounded-sm px-4 py-3 text-sm text-rose-700">
          <span className="font-medium">Error:</span> {error}
          <span className="text-xs text-rose-500 block mt-1">
            Make sure the backend is running: cd backend && python -m uvicorn main:app --reload
          </span>
        </div>
      )}

      {/* Health status bar */}
      {health && (
        <div className="flex items-center gap-4 px-4 py-2 bg-slate-50 border border-slate-200 rounded-sm text-xs text-slate-500">
          <span>
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>
            Cron Active
          </span>
          <span style={MONO}>
            Last run: {health.last_log_time ? new Date(health.last_log_time).toLocaleString() : 'N/A'}
          </span>
          <span style={MONO}>{health.signal_days} signal days</span>
        </div>
      )}

      {/* Tab navigation */}
      <div className="border-b border-slate-200">
        <nav className="flex -mb-px">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 text-xs font-medium uppercase tracking-wider transition-colors ${
                activeTab === tab.id
                  ? 'text-slate-900 border-b-2 border-slate-800'
                  : 'text-slate-500 hover:text-slate-700 border-b-2 border-transparent'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === 'overview' && (
        <div className="space-y-5">
          <KpiCards summary={summary} loading={loading} />
          <PositionsTable
            open={positions.open || []}
            closed={positions.closed || []}
            loading={loading}
          />
        </div>
      )}

      {activeTab === 'positions' && (
        <PositionsTable
          open={positions.open || []}
          closed={positions.closed || []}
          loading={loading}
        />
      )}

      {activeTab === 'signals' && <SignalHistory apiBase={API_BASE} />}

      {activeTab === 'config' && config && (
        <div className="border border-slate-200 rounded-sm bg-white overflow-hidden">
          <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
            <span className="text-[11px] uppercase tracking-wider text-slate-500 font-medium">
              Frozen Configuration
            </span>
          </div>
          <div className="p-4">
            {/* Key params grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {[
                { label: 'Threshold', value: config.threshold },
                { label: 'Stop Loss', value: `${(config.stop_loss * 100).toFixed(0)}%` },
                {
                  label: 'Take Profit',
                  value: `${(config.exit_rule?.take_profit * 100).toFixed(0)}%`,
                },
                { label: 'Max Hold', value: `${config.exit_rule?.max_hold}d` },
                { label: 'Weight', value: `${(config.weight * 100).toFixed(0)}%` },
                { label: 'Leverage', value: `${config.leverage}x` },
                { label: 'Slippage', value: `${(config.slippage * 100).toFixed(2)}%` },
                { label: 'Features', value: config.feature_count },
              ].map(({ label, value }) => (
                <div key={label}>
                  <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-0.5">
                    {label}
                  </div>
                  <div className="text-sm font-semibold text-slate-800" style={MONO}>
                    {String(value)}
                  </div>
                </div>
              ))}
            </div>

            {/* API results */}
            {config.api_results && (
              <div className="border-t border-slate-100 pt-4 mb-4">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 font-medium mb-3">
                  API Backtest Results (2017-2025)
                </div>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
                  {[
                    { label: 'CAGR', value: `${config.api_results.full_cagr}%` },
                    { label: 'Sharpe', value: config.api_results.full_sharpe.toFixed(3) },
                    { label: 'MDD', value: `${config.api_results.full_mdd}%` },
                    { label: 'Sortino', value: config.api_results.full_sortino.toFixed(2) },
                    { label: 'Calmar', value: config.api_results.full_calmar.toFixed(2) },
                    { label: 'Total Ret', value: `${config.api_results.full_total_return}%` },
                  ].map(({ label, value }) => (
                    <div key={label} className="text-center p-2 bg-slate-50 rounded-sm">
                      <div className="text-[10px] uppercase text-slate-400">{label}</div>
                      <div className="text-sm font-semibold text-slate-800" style={MONO}>
                        {value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Feature list */}
            {config.feature_names && (
              <div className="border-t border-slate-100 pt-4 mb-4">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 font-medium mb-2">
                  Features ({config.feature_names.length})
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {config.feature_names.map((f: string) => (
                    <span
                      key={f}
                      className="px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded-sm border border-slate-200"
                      style={MONO}
                    >
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Full YAML dump */}
            <details className="border-t border-slate-100 pt-4">
              <summary className="text-[11px] uppercase tracking-wider text-slate-500 font-medium cursor-pointer hover:text-slate-700">
                Full Config YAML
              </summary>
              <pre
                className="mt-3 p-3 bg-slate-900 text-slate-300 rounded-sm text-xs overflow-x-auto max-h-80 overflow-y-auto"
                style={MONO}
              >
                {JSON.stringify(config, null, 2)}
              </pre>
            </details>
          </div>
        </div>
      )}
    </div>
  );
}
