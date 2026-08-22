import React, { useState } from 'react';
import { Search, Filter, RefreshCw, XCircle, RotateCcw, Eye, Zap, Tag } from 'lucide-react';
import { apiClient } from '../api/client';

export default function JobsView({ jobs, queues, selectedQueueId, setSelectedQueueId, onInspectJob, onRefresh }) {
  const [statusFilter, setStatusFilter] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [actionLoading, setActionLoading] = useState(null);

  const statuses = [
    { value: '', label: 'All Statuses' },
    { value: 'queued', label: 'Queued' },
    { value: 'running', label: 'Running' },
    { value: 'completed', label: 'Completed' },
    { value: 'failed', label: 'Failed' },
    { value: 'dead_letter', label: 'Dead Letter (DLQ)' },
    { value: 'scheduled', label: 'Scheduled' },
    { value: 'cancelled', label: 'Cancelled' },
  ];

  const handleCancelJob = async (jobId) => {
    try {
      setActionLoading(jobId);
      await apiClient.cancelJob(jobId);
      await onRefresh();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to cancel job');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRetryJob = async (jobId) => {
    try {
      setActionLoading(jobId);
      await apiClient.retryJob(jobId);
      await onRefresh();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to retry job');
    } finally {
      setActionLoading(null);
    }
  };

  // Filter items based on local state if needed
  const filteredJobs = jobs?.items?.filter((j) => {
    if (statusFilter && j.status !== statusFilter) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      const matchName = j.name.toLowerCase().includes(q);
      const matchKey = j.idempotency_key?.toLowerCase().includes(q);
      if (!matchName && !matchKey) return false;
    }
    return true;
  }) || [];

  return (
    <div className="space-y-6">
      {/* Search & Filters Bar */}
      <div className="glass-panel p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3 flex-1">
          {/* Keyword Search */}
          <div className="relative min-w-[240px] flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search by job name or idempotency key..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-slate-900/80 border border-slate-800 text-xs text-white placeholder-slate-500 outline-none focus:border-sky-500"
            />
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-slate-900/80 border border-slate-800 text-xs text-slate-200 outline-none focus:border-sky-500 cursor-pointer"
            >
              {statuses.map((s) => (
                <option key={s.value} value={s.value} className="bg-slate-900 text-slate-200">
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          {/* Queue Filter */}
          {queues && (
            <select
              value={selectedQueueId || ''}
              onChange={(e) => setSelectedQueueId(e.target.value || null)}
              className="px-3 py-2 rounded-lg bg-slate-900/80 border border-slate-800 text-xs text-slate-200 outline-none focus:border-sky-500 cursor-pointer"
            >
              <option value="" className="bg-slate-900">All Queues</option>
              {queues.map((q) => (
                <option key={q.id} value={q.id} className="bg-slate-900">
                  {q.name}
                </option>
              ))}
            </select>
          )}
        </div>

        <span className="text-xs text-slate-400 font-medium">
          Showing <span className="text-sky-400 font-bold">{filteredJobs.length}</span> jobs
        </span>
      </div>

      {/* Jobs Table */}
      <div className="glass-panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/50 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                <th className="py-3 px-4">Task Name & Key</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Priority</th>
                <th className="py-3 px-4">Attempts</th>
                <th className="py-3 px-4">Scheduled Run</th>
                <th className="py-3 px-4">Worker Lock</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-medium">
              {filteredJobs.length > 0 ? (
                filteredJobs.map((j) => (
                  <tr key={j.id} className="hover:bg-slate-800/30 transition-colors">
                    {/* Name and Idempotency Key */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <Zap className="w-4 h-4 text-sky-400 shrink-0" />
                        <div>
                          <span className="font-mono text-slate-100 font-semibold block">{j.name}</span>
                          {j.idempotency_key && (
                            <span className="text-[10px] font-mono text-slate-400 block truncate max-w-[200px]">
                              key: {j.idempotency_key}
                            </span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Status Badge */}
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                          j.status === 'completed'
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
                            : j.status === 'running'
                            ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/25 animate-pulse'
                            : j.status === 'queued'
                            ? 'bg-sky-500/15 text-sky-400 border border-sky-500/25'
                            : j.status === 'dead_letter'
                            ? 'bg-rose-500/15 text-rose-400 border border-rose-500/25'
                            : j.status === 'scheduled'
                            ? 'bg-purple-500/15 text-purple-400 border border-purple-500/25'
                            : 'bg-slate-700/40 text-slate-400 border border-slate-700'
                        }`}
                      >
                        {j.status}
                      </span>
                    </td>

                    {/* Priority */}
                    <td className="py-3 px-4 text-slate-300 font-mono">P{j.priority}</td>

                    {/* Attempts */}
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {j.attempt_count} / {j.max_retries}
                    </td>

                    {/* Scheduled Run */}
                    <td className="py-3 px-4 text-slate-400">
                      {new Date(j.run_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </td>

                    {/* Worker Lock */}
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-400">
                      {j.locked_by_worker_id ? (
                        <span className="text-indigo-400">{j.locked_by_worker_id}</span>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => onInspectJob(j.id)}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 text-xs font-semibold transition-colors flex items-center gap-1"
                        >
                          <Eye className="w-3 h-3" />
                          <span>Inspect</span>
                        </button>

                        {(j.status === 'queued' || j.status === 'scheduled' || j.status === 'running') && (
                          <button
                            onClick={() => handleCancelJob(j.id)}
                            disabled={actionLoading === j.id}
                            className="p-1 rounded bg-slate-800 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 transition-colors"
                            title="Cancel Job"
                          >
                            <XCircle className="w-3.5 h-3.5" />
                          </button>
                        )}

                        {(j.status === 'failed' || j.status === 'dead_letter' || j.status === 'cancelled') && (
                          <button
                            onClick={() => handleRetryJob(j.id)}
                            disabled={actionLoading === j.id}
                            className="p-1 rounded bg-slate-800 hover:bg-sky-500/20 text-slate-400 hover:text-sky-400 transition-colors"
                            title="Retry Now"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    No jobs matching your filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
