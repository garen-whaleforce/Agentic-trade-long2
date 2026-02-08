'use client';

const MONO = { fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace" };

interface KpiCardsProps {
  summary: any;
  loading: boolean;
}

export function KpiCards({ summary, loading }: KpiCardsProps) {
  if (loading || !summary) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="border border-slate-200 rounded-sm p-4 animate-pulse bg-slate-50 h-20" />
        ))}
      </div>
    );
  }

  const cards = [
    { label: 'Open', value: summary.open_count },
    { label: 'Closed', value: summary.closed_count },
    { label: 'Total', value: summary.total_positions },
    {
      label: 'Avg Return',
      value: `${summary.avg_closed_return_pct?.toFixed(2) ?? '0.00'}%`,
      color: (summary.avg_closed_return_pct ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-600',
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map(({ label, value, color }) => (
        <div key={label} className="border border-slate-200 rounded-sm bg-white p-4">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">{label}</div>
          <div className={`text-lg font-semibold ${color ?? 'text-slate-800'}`} style={MONO}>
            {value}
          </div>
        </div>
      ))}
    </div>
  );
}
