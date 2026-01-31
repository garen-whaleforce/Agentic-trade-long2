'use client';

import { useState } from 'react';

interface CompanyEvent {
  event_id: string;
  fiscal_year: number;
  fiscal_quarter: number;
  event_date: string;
  transcript_available: boolean;
}

interface SymbolModeViewProps {
  onEventSelect: (eventId: string) => void;
}

export function SymbolModeView({ onEventSelect }: SymbolModeViewProps) {
  const [symbol, setSymbol] = useState<string>('');
  const [companyName, setCompanyName] = useState<string>('');
  const [events, setEvents] = useState<CompanyEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const fetchCompanyEvents = async () => {
    if (!symbol.trim()) return;

    setIsLoading(true);
    try {
      const response = await fetch(
        `/api/company/${symbol.toUpperCase()}/events`
      );
      if (response.ok) {
        const data = await response.json();
        setCompanyName(data.company_name);
        setEvents(data.events);
      }
    } catch (error) {
      console.error('Failed to fetch company events:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEventClick = (eventId: string) => {
    setSelectedEventId(eventId);
    onEventSelect(eventId);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      fetchCompanyEvents();
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="card-header">Search by Symbol</h2>

      {/* Symbol Search */}
      <div className="flex gap-4">
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          onKeyPress={handleKeyPress}
          placeholder="Enter symbol (e.g., AAPL)"
          className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 uppercase"
        />
        <button
          onClick={fetchCompanyEvents}
          disabled={!symbol.trim()}
          className="btn btn-primary disabled:opacity-50"
        >
          {isLoading ? 'Loading...' : 'Search'}
        </button>
      </div>

      {/* Company Info */}
      {companyName && (
        <div className="p-3 bg-gray-50 rounded-md">
          <span className="font-bold text-lg">{symbol}</span>
          <span className="text-gray-600 ml-2">{companyName}</span>
        </div>
      )}

      {/* Events List */}
      <div className="space-y-2">
        <h3 className="font-medium text-gray-700">
          Earnings History ({events.length})
        </h3>

        {events.length === 0 ? (
          <p className="text-gray-500 text-sm">
            No earnings calls found. Enter a symbol and click Search.
          </p>
        ) : (
          <div className="max-h-96 overflow-y-auto">
            <ul className="divide-y divide-gray-200">
              {events.map((event) => (
                <li
                  key={event.event_id}
                  onClick={() => handleEventClick(event.event_id)}
                  className={`
                    py-3 px-2 cursor-pointer rounded-md transition-colors
                    ${
                      selectedEventId === event.event_id
                        ? 'bg-primary-50 border-primary-200'
                        : 'hover:bg-gray-50'
                    }
                  `}
                >
                  <div className="flex justify-between items-center">
                    <div>
                      <span className="font-medium text-gray-900">
                        Q{event.fiscal_quarter} {event.fiscal_year}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-500">
                        {event.event_date}
                      </span>
                      {event.transcript_available ? (
                        <span className="badge badge-success">Transcript</span>
                      ) : (
                        <span className="badge badge-warning">Pending</span>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
