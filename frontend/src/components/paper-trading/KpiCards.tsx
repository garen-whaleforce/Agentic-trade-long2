'use client';

const MONO = { fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace" };

interface KpiCardsProps {
  summary: any;
  loading: boolean;
}

export function KpiCards({ summary, loading }: KpiCardsProps) {
  if (loading || !summary) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="border border-slate-200 rounded-sm p-4 animate-pulse bg-slate-50 h-20" />
        ))}
      </div>
    );
  }

  const cards = [
    { label: 'Open', value: summary.open_count, sub: 'positions' },
    { label: 'Closed', value: summary.closed_count, sub: 'positions' },
    {
      label: 'Avg Return',
      value: `${summary.avg_closed_return_pct != null ? (summary.avg_closed_return_pct > 0 ? '+' : '') + summary.avg_closed_return_pct.toFixed(2) : '0.00'}%`,
      color: (summary.avg_closed_return_pct ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600',
      sub: 'closed trades',
    },
    {
      label: 'Exposure',
      value: `${((summary.total_open_weight ?? 0) * 100).toFixed(1)}%`,
      sub: 'of portfolio',
    },
    {
      label: 'TP Rate',
      value: summary.closed_count > 0 ? `${((summary.tp_hit_rate ?? 0) * 100).toFixed(0)}%` : '-',
      color: (summary.tp_hit_rate ?? 0) >= 0.5 ? 'text-emerald-600' : 'text-slate-600',
      sub: `${summary.exit_reasons?.take_profit ?? 0} of ${summary.closed_count}`,
    },
    {
      label: 'Total',
      value: summary.total_positions,
      sub: 'all trades',
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map(({ label, value, color, sub }) => (
        <div key={label} className="border border-slate-200 rounded-sm bg-white p-4">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">{label}</div>
          <div className={`text-lg font-semibold ${color ?? 'text-slate-800'}`} style={MONO}>
            {value}
          </div>
          {sub && <div className="text-[10px] text-slate-400 mt-0.5">{sub}</div>}
        </div>
      ))}
    </div>
  );
}
