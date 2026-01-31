'use client';

import { useState } from 'react';
import { DateModeView } from '@/components/DateModeView';
import { SymbolModeView } from '@/components/SymbolModeView';
import { AnalysisResult } from '@/components/AnalysisResult';
import { Tabs } from '@/components/ui/Tabs';

export default function Home() {
  const [activeTab, setActiveTab] = useState<'date' | 'symbol'>('date');
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const handleEventSelect = async (eventId: string) => {
    setSelectedEventId(eventId);
    setIsAnalyzing(true);

    try {
      // Call analyze API
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: eventId, mode: 'batch_score' }),
      });

      if (response.ok) {
        const data = await response.json();
        setAnalysisResult(data);
      }
    } catch (error) {
      console.error('Analysis failed:', error);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleFullAudit = async () => {
    if (!selectedEventId) return;
    setIsAnalyzing(true);

    try {
      const response = await fetch('/api/analyze/full_audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: selectedEventId }),
      });

      if (response.ok) {
        const data = await response.json();
        setAnalysisResult(data);
      }
    } catch (error) {
      console.error('Full audit failed:', error);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Mode Selection Tabs */}
      <div className="card">
        <Tabs
          tabs={[
            { id: 'date', label: 'By Date' },
            { id: 'symbol', label: 'By Symbol' },
          ]}
          activeTab={activeTab}
          onTabChange={(id) => setActiveTab(id as 'date' | 'symbol')}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Panel: Selection */}
        <div className="card">
          {activeTab === 'date' ? (
            <DateModeView onEventSelect={handleEventSelect} />
          ) : (
            <SymbolModeView onEventSelect={handleEventSelect} />
          )}
        </div>

        {/* Right Panel: Analysis Result */}
        <div className="card">
          <AnalysisResult
            result={analysisResult}
            isLoading={isAnalyzing}
            onFullAudit={handleFullAudit}
          />
        </div>
      </div>
    </div>
  );
}
