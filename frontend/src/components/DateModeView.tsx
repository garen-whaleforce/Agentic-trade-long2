'use client';

import { useState } from 'react';
import { format } from 'date-fns';

interface EarningsEvent {
  event_id: string;
  symbol: string;
  company_name: string;
  fiscal_year: number;
  fiscal_quarter: number;
  event_date: string;
  transcript_available: boolean;
}

interface DateModeViewProps {
  onEventSelect: (eventId: string) => void;
}

export function DateModeView({ onEventSelect }: DateModeViewProps) {
  const [selectedDate, setSelectedDate] = useState<string>(
    format(new Date(), 'yyyy-MM-dd')
  );
  const [events, setEvents] = useState<EarningsEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);

  const fetchEvents = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`/api/earnings?date=${selectedDate}`);
      if (response.ok) {
        const data = await response.json();
        setEvents(data.events);
      }
    } catch (error) {
      console.error('Failed to fetch events:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEventClick = (eventId: string) => {
    setSelectedEventId(eventId);
    onEventSelect(eventId);
  };

  return (
    <div className="space-y-4">
      <h2 className="card-header">Select Date</h2>

      {/* Date Picker */}
      <div className="flex gap-4">
        <input
          type="date"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          min="2017-01-01"
          max={format(new Date(), 'yyyy-MM-dd')}
          className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
        <button onClick={fetchEvents} className="btn btn-primary">
          {isLoading ? 'Loading...' : 'Search'}
        </button>
      </div>

      {/* Events List */}
      <div className="space-y-2">
        <h3 className="font-medium text-gray-700">
          Earnings Calls ({events.length})
        </h3>

        {events.length === 0 ? (
          <p className="text-gray-500 text-sm">
            No earnings calls found. Select a date and click Search.
          </p>
        ) : (
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
                      {event.symbol}
                    </span>
                    <span className="text-gray-500 ml-2">
                      {event.company_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-500">
                      Q{event.fiscal_quarter} {event.fiscal_year}
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
        )}
      </div>
    </div>
  );
}
