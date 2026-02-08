'use client';

const MONO = { fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace" };

interface PositionsTableProps {
  open: any[];
  closed: any[];
  loading: boolean;
}

export function PositionsTable({ open, closed, loading }: PositionsTableProps) {
  if (loading) {
    return <div className="border border-slate-200 rounded-sm p-6 animate-pulse bg-slate-50 h-40" />;
  }

  return (
    <div className="space-y-5">
      {/* Open positions */}
      <div className="border border-slate-200 rounded-sm bg-white overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-slate-500 font-medium">
            Open Positions ({open.length})
          </span>
        </div>
        {open.length === 0 ? (
          <div className="px-4 py-6 text-sm text-slate-400 text-center">No open positions</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" style={MONO}>
              <thead>
                <tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-wider text-slate-400">
                  <th className="px-4 py-2">Symbol</th>
                  <th className="px-4 py-2">Entry Date</th>
                  <th className="px-4 py-2">Entry Price</th>
                  <th className="px-4 py-2">Score</th>
                  <th className="px-4 py-2">Weight</th>
                </tr>
              </thead>
              <tbody>
                {open.map((p: any, i: number) => (
                  <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="px-4 py-2 font-medium text-slate-800">{p.symbol}</td>
                    <td className="px-4 py-2 text-slate-500">{p.entry_date}</td>
                    <td className="px-4 py-2 text-slate-600">{p.entry_price}</td>
                    <td className="px-4 py-2 text-slate-600">{p.score}</td>
                    <td className="px-4 py-2 text-slate-600">{p.weight}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Closed positions */}
      <div className="border border-slate-200 rounded-sm bg-white overflow-hidden">
        <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
          <span className="text-[11px] uppercase tracking-wider text-slate-500 font-medium">
            Closed Positions ({closed.length})
          </span>
        </div>
        {closed.length === 0 ? (
          <div className="px-4 py-6 text-sm text-slate-400 text-center">No closed positions</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" style={MONO}>
              <thead>
                <tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-wider text-slate-400">
                  <th className="px-4 py-2">Symbol</th>
                  <th className="px-4 py-2">Entry</th>
                  <th className="px-4 py-2">Exit</th>
                  <th className="px-4 py-2">Return</th>
                  <th className="px-4 py-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {closed.map((p: any, i: number) => (
                  <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="px-4 py-2 font-medium text-slate-800">{p.symbol}</td>
                    <td className="px-4 py-2 text-slate-500">{p.entry_date}</td>
                    <td className="px-4 py-2 text-slate-500">{p.exit_date}</td>
                    <td
                      className={`px-4 py-2 font-medium ${
                        (p.return_pct ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'
                      }`}
                    >
                      {p.return_pct != null ? `${p.return_pct.toFixed(2)}%` : '-'}
                    </td>
                    <td className="px-4 py-2 text-slate-500">{p.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
