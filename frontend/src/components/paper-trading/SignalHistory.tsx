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
        setDates(data.dates || []);
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

  return (
    <div className="border border-slate-200 rounded-sm bg-white overflow-hidden">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <span className="text-[11px] uppercase tracking-wider text-slate-500 font-medium">
          Signal History ({dates.length} days)
        </span>
      </div>
      <div className="p-4">
        {dates.length === 0 ? (
          <div className="text-sm text-slate-400 text-center py-4">No signal data available</div>
        ) : (
          <div className="space-y-3">
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
            {signals && (
              <pre
                className="mt-3 p-3 bg-slate-900 text-slate-300 rounded-sm text-xs overflow-x-auto max-h-80 overflow-y-auto"
                style={MONO}
              >
                {JSON.stringify(signals, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
