import React, { useState, useEffect } from 'react';
import { X, Terminal, Clock, Cpu, RotateCcw, XCircle, CheckCircle2, AlertOctagon, Zap } from 'lucide-react';
import { apiClient } from '../api/client';

export default function JobDetailDrawer({ jobId, onClose, onRefresh }) {
  const [job, setJob] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    if (jobId) {
      loadDetails();
    }
  }, [jobId]);

  const loadDetails = async () => {
    try {
      setLoading(true);
      const [resJob, resLogs] = await Promise.all([
        apiClient.getJob(jobId),
        apiClient.getJobLogs(jobId),
      ]);
      setJob(resJob.data);
      setLogs(resLogs.data || []);
    } catch (e) {
      console.error('Error loading job detail:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async () => {
    try {
      setActionLoading(true);
      await apiClient.retryJob(jobId);
      await loadDetails();
      if (onRefresh) onRefresh();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to retry job');
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    try {
      setActionLoading(true);
      await apiClient.cancelJob(jobId);
      await loadDetails();
      if (onRefresh) onRefresh();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to cancel job');
    } finally {
      setActionLoading(false);
    }
  };

  if (!jobId) return null;

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex justify-end">
      <div className="w-full max-w-2xl bg-[#080E1A] border-l border-slate-800 h-full flex flex-col shadow-2xl overflow-hidden animate-slide-in">
        {/* Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 shrink-0">
              <Zap className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white truncate font-mono">{job?.name || 'Task Detail'}</h3>
                {job?.status && (
                  <span
                    className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                      job.status === 'completed'
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                        : job.status === 'running'
                        ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/30 animate-pulse'
                        : job.status === 'dead_letter'
                        ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                        : 'bg-sky-500/15 text-sky-400 border border-sky-500/30'
                    }`}
                  >
                    {job.status}
                  </span>
                )}
              </div>
              <p className="text-[11px] font-mono text-slate-400 truncate">UUID: {jobId}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {(job?.status === 'failed' || job?.status === 'dead_letter' || job?.status === 'cancelled') && (
              <button
                onClick={handleRetry}
                disabled={actionLoading}
                className="py-1.5 px-3 rounded bg-sky-500 hover:bg-sky-400 text-white text-xs font-semibold flex items-center gap-1.5 shadow-glow-cyan transition-all"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Retry</span>
              </button>
            )}

            {(job?.status === 'queued' || job?.status === 'running' || job?.status === 'scheduled') && (
              <button
                onClick={handleCancel}
                disabled={actionLoading}
                className="py-1.5 px-3 rounded bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/30 text-xs font-semibold flex items-center gap-1.5 transition-all"
              >
                <XCircle className="w-3 h-3" />
                <span>Cancel</span>
              </button>
            )}

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Body */}
        <div className="flex-1 p-6 space-y-6 overflow-y-auto text-xs">
          {loading ? (
            <div className="py-12 text-center text-slate-400">Loading execution audit telemetry...</div>
          ) : (
            <>
              {/* Metadata Grid */}
              <div className="grid grid-cols-3 gap-3">
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                  <span className="text-slate-400 text-[11px] block">Priority</span>
                  <span className="font-mono font-bold text-slate-200 text-sm">P{job?.priority}</span>
                </div>
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                  <span className="text-slate-400 text-[11px] block">Attempt Count</span>
                  <span className="font-mono font-bold text-sky-400 text-sm">
                    {job?.attempt_count} / {job?.max_retries}
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                  <span className="text-slate-400 text-[11px] block">Scheduled Run</span>
                  <span className="font-mono text-slate-200 text-[11px]">
                    {job?.run_at ? new Date(job.run_at).toLocaleTimeString() : 'Immediate'}
                  </span>
                </div>
              </div>

              {/* Payload & Result JSON */}
              <div className="space-y-3">
                <div>
                  <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                    Input Arguments (JSON):
                  </span>
                  <pre className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 font-mono text-sky-300 text-[11px] overflow-x-auto">
                    {JSON.stringify(job?.payload, null, 2)}
                  </pre>
                </div>

                {job?.result && (
                  <div>
                    <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                      Task Output Result:
                    </span>
                    <pre className="p-3 rounded-lg bg-slate-950 border border-emerald-500/20 font-mono text-emerald-300 text-[11px] overflow-x-auto">
                      {JSON.stringify(job.result, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* Execution Attempt Logs & Console Terminal */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Terminal className="w-4 h-4 text-sky-400" />
                  <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                    Console Execution Logs & Stderr ({logs.length} Attempt{logs.length === 1 ? '' : 's'})
                  </span>
                </div>

                <div className="space-y-3">
                  {logs.length > 0 ? (
                    logs.map((exec) => (
                      <div key={exec.id} className="rounded-lg bg-slate-950 border border-slate-800 overflow-hidden">
                        <div className="px-3 py-2 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between text-[11px] font-mono">
                          <span className="text-slate-300 font-semibold">Attempt #{exec.attempt_number}</span>
                          <span className="text-slate-400">
                            Worker: <span className="text-sky-300">{exec.worker_id}</span> ({exec.duration_ms}ms)
                          </span>
                        </div>
                        <div className="p-3 font-mono text-[11px] space-y-2">
                          {exec.logs && (
                            <pre className="text-slate-300 whitespace-pre-wrap">{exec.logs}</pre>
                          )}
                          {exec.error_message && (
                            <div className="p-2 rounded bg-rose-500/10 border border-rose-500/20 text-rose-300">
                              Error: {exec.error_message}
                            </div>
                          )}
                          {exec.stack_trace && (
                            <pre className="text-rose-400 whitespace-pre-wrap text-[10px] overflow-x-auto">
                              {exec.stack_trace}
                            </pre>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-4 rounded-lg bg-slate-950/60 border border-slate-800 text-center text-slate-500">
                      No execution logs recorded yet for this job.
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
