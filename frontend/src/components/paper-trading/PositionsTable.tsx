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
          <span className="text-[10px] text-slate-400" style={MONO}>
            Total weight: {open.reduce((s: number, p: any) => s + (p.weight || 0), 0).toFixed(3)}
          </span>
        </div>
        {open.length === 0 ? (
          <div className="px-4 py-6 text-sm text-slate-400 text-center">No open positions</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" style={MONO}>
              <thead>
                <tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-wider text-slate-400">
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">Sector</th>
                  <th className="px-3 py-2">Entry</th>
                  <th className="px-3 py-2 text-right">Price</th>
                  <th className="px-3 py-2 text-right">Prob</th>
                  <th className="px-3 py-2 text-right">Weight</th>
                  <th className="px-3 py-2 text-right">TP</th>
                  <th className="px-3 py-2 text-right">SL</th>
                  <th className="px-3 py-2">Max Hold</th>
                </tr>
              </thead>
              <tbody>
                {open.map((p: any, i: number) => (
                  <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="px-3 py-2 font-medium text-slate-800">{p.symbol}</td>
                    <td className="px-3 py-2 text-slate-500 text-[10px]">{p.sector ?? '-'}</td>
                    <td className="px-3 py-2 text-slate-500">{p.entry_date}</td>
                    <td className="px-3 py-2 text-slate-600 text-right">{fmt(p.entry_price)}</td>
                    <td className="px-3 py-2 text-slate-600 text-right">{p.prob?.toFixed(3) ?? '-'}</td>
                    <td className="px-3 py-2 text-slate-600 text-right">{(p.weight * 100).toFixed(1)}%</td>
                    <td className="px-3 py-2 text-emerald-600 text-right">{fmt(p.take_profit_price)}</td>
                    <td className="px-3 py-2 text-rose-500 text-right">{fmt(p.stop_loss_price)}</td>
                    <td className="px-3 py-2 text-slate-500">{p.max_hold_date ?? '-'}</td>
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
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">Sector</th>
                  <th className="px-3 py-2">Entry</th>
                  <th className="px-3 py-2 text-right">Entry $</th>
                  <th className="px-3 py-2">Exit</th>
                  <th className="px-3 py-2 text-right">Exit $</th>
                  <th className="px-3 py-2 text-right">Return</th>
                  <th className="px-3 py-2">Reason</th>
                  <th className="px-3 py-2 text-right">Days</th>
                </tr>
              </thead>
              <tbody>
                {closed.map((p: any, i: number) => (
                  <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="px-3 py-2 font-medium text-slate-800">{p.symbol}</td>
                    <td className="px-3 py-2 text-slate-500 text-[10px]">{p.sector ?? '-'}</td>
                    <td className="px-3 py-2 text-slate-500">{p.entry_date}</td>
                    <td className="px-3 py-2 text-slate-600 text-right">{fmt(p.entry_price)}</td>
                    <td className="px-3 py-2 text-slate-500">{p.exit_date}</td>
                    <td className="px-3 py-2 text-slate-600 text-right">{fmt(p.exit_price)}</td>
                    <td
                      className={`px-3 py-2 font-medium text-right ${
                        (p.return_pct ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'
                      }`}
                    >
                      {p.return_pct != null ? `${p.return_pct > 0 ? '+' : ''}${p.return_pct.toFixed(2)}%` : '-'}
                    </td>
                    <td className="px-3 py-2 text-slate-500">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded text-[10px] ${
                          p.exit_reason === 'take_profit'
                            ? 'bg-emerald-50 text-emerald-700'
                            : p.exit_reason === 'stop_loss'
                              ? 'bg-rose-50 text-rose-700'
                              : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {p.exit_reason ?? '-'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-slate-500 text-right">{p.hold_days_approx ?? '-'}</td>
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

function fmt(v: number | null | undefined): string {
  if (v == null) return '-';
  return v >= 100 ? v.toFixed(2) : v.toFixed(2);
}
