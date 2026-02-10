'use client';

import { useState, useEffect } from 'react';

const MONO = { fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace" };

interface SignalHistoryProps {
  apiBase: string;
}

export function SignalHistory({ apiBase }: SignalHistoryProps) {
  const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [signals, setSignals] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${apiBase}/api/paper-trading/signals/dates`)
      .then((r) => r.json())
      .then((data) => {
        const sorted = (data.dates || []).sort((a: string, b: string) => b.localeCompare(a));
        setDates(sorted);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [apiBase]);

  useEffect(() => {
    if (!selectedDate) {
      setSignals(null);
      return;
    }
    setLoading(true);
    fetch(`${apiBase}/api/paper-trading/signals?date=${selectedDate}`)
      .then((r) => r.json())
      .then((data) => {
        setSignals(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [apiBase, selectedDate]);

  if (loading && dates.length === 0) {
    return <div className="border border-slate-200 rounded-sm p-6 animate-pulse bg-slate-50 h-40" />;
  }

  const signalList: any[] = signals?.signals || [];
  const buys = signalList.filter((s: any) => s.action === 'BUY');
  const skips = signalList.filter((s: any) => s.action !== 'BUY');

  return (
    <div className="border border-slate-200 rounded-sm bg-white overflow-hidden">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3 flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wider text-slate-500 font-medium">
          Signal History ({dates.length} days)
        </span>
        {signals && (
          <span className="text-[10px] text-slate-400" style={MONO}>
            {signals.events} events | {buys.length} BUY | {skips.length} skip
          </span>
        )}
      </div>
      <div className="p-4">
        {dates.length === 0 ? (
          <div className="text-sm text-slate-400 text-center py-4">No signal data available</div>
        ) : (
          <div className="space-y-4">
            {/* Date selector */}
            <div className="flex flex-wrap gap-1.5">
              {dates.map((d) => (
                <button
                  key={d}
                  onClick={() => setSelectedDate(d === selectedDate ? null : d)}
                  className={`px-2 py-1 text-xs rounded-sm border transition-colors ${
                    d === selectedDate
                      ? 'bg-slate-800 text-white border-slate-800'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                  }`}
                  style={MONO}
                >
                  {d}
                </button>
              ))}
            </div>

            {/* Signal table */}
            {signals && signalList.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs" style={MONO}>
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-wider text-slate-400">
                      <th className="px-3 py-2">Action</th>
                      <th className="px-3 py-2">Symbol</th>
                      <th className="px-3 py-2">Sector</th>
                      <th className="px-3 py-2 text-right">Drop</th>
                      <th className="px-3 py-2 text-right">EPS Surp</th>
                      <th className="px-3 py-2 text-right">Prob</th>
                      <th className="px-3 py-2 text-right">Thr</th>
                      <th className="px-3 py-2 text-right">Entry $</th>
                      <th className="px-3 py-2 text-right">Weight</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* BUY signals first */}
                    {buys.map((s: any, i: number) => (
                      <SignalRow key={`buy-${i}`} s={s} />
                    ))}
                    {/* Separator if both exist */}
                    {buys.length > 0 && skips.length > 0 && (
                      <tr>
                        <td colSpan={9} className="px-3 py-1">
                          <div className="border-t border-dashed border-slate-200" />
                        </td>
                      </tr>
                    )}
                    {/* NO_TRADE signals */}
                    {skips.map((s: any, i: number) => (
                      <SignalRow key={`skip-${i}`} s={s} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {signals && signalList.length === 0 && (
              <div className="text-sm text-slate-400 text-center py-4">No events on this date</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SignalRow({ s }: { s: any }) {
  const isBuy = s.action === 'BUY';
  return (
    <tr className={`border-b border-slate-50 ${isBuy ? 'bg-emerald-50/30' : ''} hover:bg-slate-50`}>
      <td className="px-3 py-2">
        <span
          className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${
            isBuy ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'
          }`}
        >
          {s.action}
        </span>
      </td>
      <td className="px-3 py-2 font-medium text-slate-800">{s.symbol}</td>
      <td className="px-3 py-2 text-slate-500 text-[10px]">{s.sector ?? '-'}</td>
      <td className="px-3 py-2 text-rose-600 text-right">
        {s.drop_1d != null ? `${(s.drop_1d * 100).toFixed(1)}%` : '-'}
      </td>
      <td className="px-3 py-2 text-right text-slate-600">
        {s.eps_surprise != null ? `${(s.eps_surprise * 100).toFixed(1)}%` : '-'}
      </td>
      <td
        className={`px-3 py-2 text-right font-medium ${
          isBuy ? 'text-emerald-600' : 'text-slate-400'
        }`}
      >
        {s.ml_prob?.toFixed(3) ?? '-'}
      </td>
      <td className="px-3 py-2 text-right text-slate-400">{s.threshold?.toFixed(2) ?? '-'}</td>
      <td className="px-3 py-2 text-right text-slate-600">
        {s.price_t1 != null ? s.price_t1.toFixed(2) : '-'}
      </td>
      <td className="px-3 py-2 text-right text-slate-600">
        {s.weight > 0 ? `${(s.weight * 100).toFixed(1)}%` : '-'}
      </td>
    </tr>
  );
}
