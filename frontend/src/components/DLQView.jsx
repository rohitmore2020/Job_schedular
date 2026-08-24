import React, { useState, useEffect } from 'react';
import { AlertOctagon, RotateCcw, Trash2, CheckCircle, ChevronDown, ChevronUp, Zap, Sparkles } from 'lucide-react';
import { apiClient } from '../api/client';

export default function DLQView({ queues, selectedQueueId, setSelectedQueueId, onInspectJob }) {
  const [dlqEntries, setDlqEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);

  const fetchDLQ = async () => {
    if (!selectedQueueId) return;
    try {
      setLoading(true);
      const res = await apiClient.getDLQ(selectedQueueId);
      setDlqEntries(res.data.items || []);
    } catch (e) {
      console.error('Error fetching DLQ:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedQueueId) {
      fetchDLQ();
    }
  }, [selectedQueueId]);

  const handleReplaySingle = async (dlqId) => {
    try {
      setActionLoading(dlqId);
      await apiClient.replayDLQ(dlqId);
      await fetchDLQ();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to replay DLQ job');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReplayAll = async () => {
    if (!selectedQueueId) return;
    try {
      setActionLoading('bulk');
      const res = await apiClient.replayAllDLQ(selectedQueueId);
      alert(res.data.message);
      await fetchDLQ();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to replay all DLQ jobs');
    } finally {
      setActionLoading(null);
    }
  };

  const handlePurge = async (dlqId) => {
    if (!confirm('Are you sure you want to permanently purge this incident record?')) return;
    try {
      setActionLoading(dlqId);
      await apiClient.purgeDLQ(dlqId);
      await fetchDLQ();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to purge DLQ entry');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse"></div>
            <h2 className="text-lg font-bold text-white tracking-tight">Dead Letter Queue Incident Center</h2>
          </div>
          <p className="text-xs text-slate-400">
            Unrecoverable task exceptions, exhausted retry limits, and dead worker lease expirations.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {queues && (
            <select
              value={selectedQueueId || ''}
              onChange={(e) => setSelectedQueueId(e.target.value)}
              className="px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 outline-none focus:border-sky-500 cursor-pointer"
            >
              {queues.map((q) => (
                <option key={q.id} value={q.id} className="bg-slate-900">
                  {q.name}
                </option>
              ))}
            </select>
          )}

          <button
            onClick={handleReplayAll}
            disabled={actionLoading === 'bulk' || dlqEntries.length === 0}
            className="py-2 px-4 rounded-lg bg-gradient-to-r from-rose-500 to-indigo-600 hover:from-rose-400 hover:to-indigo-500 text-white text-xs font-semibold flex items-center gap-2 shadow-glow-rose transition-all active:scale-95 disabled:opacity-50"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${actionLoading === 'bulk' ? 'animate-spin' : ''}`} />
            <span>Replay All ({dlqEntries.filter((e) => !e.is_replayed).length})</span>
          </button>
        </div>
      </div>

      {/* Incidents List */}
      <div className="space-y-3">
        {dlqEntries.length > 0 ? (
          dlqEntries.map((item) => {
            const isExpanded = expandedId === item.id;
            return (
              <div
                key={item.id}
                className={`glass-panel p-5 border transition-all ${
                  item.is_replayed
                    ? 'border-emerald-500/20 opacity-75'
                    : 'border-rose-500/30 hover:border-rose-500/50 shadow-glow-rose'
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1 min-w-[280px]">
                    <div className="w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 shrink-0 mt-0.5">
                      <AlertOctagon className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-slate-100 text-sm">
                          {item.job?.name || 'Task'}
                        </span>
                        <span
                          className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${
                            item.is_replayed
                              ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                              : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                          }`}
                        >
                          {item.is_replayed ? 'REPLAYED' : 'ACTIVE INCIDENT'}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">
                          {item.total_attempts} attempts made
                        </span>
                      </div>
                      <p className="text-xs text-rose-300 font-mono mt-1">{item.failed_reason}</p>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Moved to DLQ on {new Date(item.moved_to_dlq_at).toLocaleString()}
                      </p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : item.id)}
                      className="px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium flex items-center gap-1 transition-colors"
                    >
                      <span>{isExpanded ? 'Hide Trace' : 'View Trace'}</span>
                      {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    </button>

                    {!item.is_replayed && (
                      <button
                        onClick={() => handleReplaySingle(item.id)}
                        disabled={actionLoading === item.id}
                        className="py-1.5 px-3 rounded bg-sky-500 hover:bg-sky-400 text-white text-xs font-semibold flex items-center gap-1.5 shadow-glow-cyan transition-all"
                      >
                        <RotateCcw className="w-3 h-3" />
                        <span>Replay Job</span>
                      </button>
                    )}

                    <button
                      onClick={() => handlePurge(item.id)}
                      disabled={actionLoading === item.id}
                      className="p-1.5 rounded bg-slate-800 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 transition-colors"
                      title="Purge Entry"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Expanded Stack Trace */}
                {isExpanded && (
                  <div className="mt-4 pt-4 border-t border-slate-800/80 space-y-3 text-xs">
                    {item.ai_failure_summary && (
                      <div>
                        <div className="flex items-center gap-1.5 mb-1 text-[11px] font-semibold text-purple-400 uppercase tracking-wider">
                          <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                          <span>AI Root-Cause Diagnostic:</span>
                        </div>
                        <div className="p-3 rounded-lg bg-purple-950/20 border border-purple-800/40 text-purple-200 font-mono text-[11px] whitespace-pre-wrap">
                          {item.ai_failure_summary}
                        </div>
                      </div>
                    )}

                    <div>
                      <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                        Captured Python Traceback:
                      </span>
                      <pre className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 text-rose-300 font-mono text-[11px] overflow-x-auto max-h-48">
                        {item.last_error || 'No stack trace captured.'}
                      </pre>
                    </div>

                    {item.job?.payload && (
                      <div>
                        <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
                          Original Input Payload:
                        </span>
                        <pre className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 text-sky-300 font-mono text-[11px] overflow-x-auto">
                          {JSON.stringify(item.job.payload, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <div className="glass-panel p-12 text-center text-slate-400">
            <CheckCircle className="w-8 h-8 text-emerald-400 mx-auto mb-2 opacity-80" />
            <p className="text-sm font-semibold text-slate-200">No active incidents in this queue</p>
            <p className="text-xs text-slate-400 mt-1">All executions are succeeding or properly recovered by the worker retry engine.</p>
          </div>
        )}
      </div>
    </div>
  );
}
