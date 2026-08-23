import React, { useState, useEffect } from 'react';
import {
  Boxes,
  RefreshCw,
  Search,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  PlayCircle,
  StopCircle,
  Layers,
  Clock,
  ChevronRight,
  Filter,
} from 'lucide-react';
import { apiClient } from '../api/client';

export default function BatchesView() {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [batchJobs, setBatchJobs] = useState([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const fetchBatches = async () => {
    try {
      setLoading(true);
      const params = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      const res = await apiClient.getBatches(params);
      setBatches(res.data.items || []);
    } catch (e) {
      console.error('Failed to fetch batches:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBatches();
    const interval = setInterval(fetchBatches, 4000);
    return () => clearInterval(interval);
  }, [statusFilter]);

  const handleSelectBatch = async (batch) => {
    setSelectedBatch(batch);
    try {
      setLoadingJobs(true);
      const res = await apiClient.getBatchJobs(batch.id);
      setBatchJobs(res.data.items || []);
    } catch (e) {
      console.error('Failed to fetch batch jobs:', e);
    } finally {
      setLoadingJobs(false);
    }
  };

  const handleCancelBatch = async (batchId) => {
    try {
      await apiClient.cancelBatch(batchId);
      await fetchBatches();
      if (selectedBatch?.id === batchId) {
        const detail = await apiClient.getBatch(batchId);
        setSelectedBatch(detail.data);
      }
    } catch (e) {
      console.error('Failed to cancel batch:', e);
    }
  };

  const handleRetryBatch = async (batchId) => {
    try {
      await apiClient.retryBatch(batchId);
      await fetchBatches();
      if (selectedBatch?.id === batchId) {
        const detail = await apiClient.getBatch(batchId);
        setSelectedBatch(detail.data);
      }
    } catch (e) {
      console.error('Failed to retry batch:', e);
    }
  };

  const filteredBatches = batches.filter((b) =>
    b.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const getStatusBadge = (status) => {
    switch (status) {
      case 'completed':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      case 'processing':
        return 'bg-sky-500/10 text-sky-400 border-sky-500/30';
      case 'partially_failed':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
      case 'failed':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/30';
      case 'cancelled':
        return 'bg-slate-500/10 text-slate-400 border-slate-500/30';
      default:
        return 'bg-slate-500/10 text-slate-400 border-slate-500/30';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Boxes className="w-6 h-6 text-sky-400" />
            Batch Jobs & Progress Tracking
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Atomic batch orchestration with aggregated execution progress, live error rates, and 1-click retry.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchBatches}
            className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 rounded-xl bg-[#0B132B]/60 border border-slate-800/80 backdrop-blur-md">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search batches..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 transition-colors"
          />
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-xs text-slate-300 rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500"
          >
            <option value="all">All Statuses</option>
            <option value="processing">Processing</option>
            <option value="completed">Completed</option>
            <option value="partially_failed">Partially Failed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>

      {/* Batch Cards Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {filteredBatches.map((batch) => {
          const isSelected = selectedBatch?.id === batch.id;
          return (
            <div
              key={batch.id}
              onClick={() => handleSelectBatch(batch)}
              className={`p-5 rounded-xl border transition-all cursor-pointer ${
                isSelected
                  ? 'bg-slate-900/90 border-sky-500/50 shadow-glow-cyan'
                  : 'bg-[#0B132B]/70 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900/50'
              }`}
            >
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <h3 className="text-sm font-semibold text-white tracking-wide flex items-center gap-2">
                    {batch.name}
                  </h3>
                  <p className="text-[11px] text-slate-400 font-mono mt-0.5">ID: {batch.id}</p>
                </div>
                <span
                  className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border ${getStatusBadge(
                    batch.status
                  )}`}
                >
                  {batch.status}
                </span>
              </div>

              {/* Visual Progress Bar */}
              <div className="space-y-1.5 my-4">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400 font-medium">Execution Progress</span>
                  <span className="text-sky-400 font-mono font-bold">{batch.progress_percent}%</span>
                </div>
                <div className="w-full h-2.5 rounded-full bg-slate-950/80 overflow-hidden flex border border-slate-800">
                  <div
                    style={{ width: `${(batch.completed_jobs / (batch.total_jobs || 1)) * 100}%` }}
                    className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 transition-all duration-500"
                    title={`Completed: ${batch.completed_jobs}`}
                  />
                  <div
                    style={{ width: `${(batch.failed_jobs / (batch.total_jobs || 1)) * 100}%` }}
                    className="h-full bg-rose-500 transition-all duration-500"
                    title={`Failed: ${batch.failed_jobs}`}
                  />
                  <div
                    style={{ width: `${(batch.cancelled_jobs / (batch.total_jobs || 1)) * 100}%` }}
                    className="h-full bg-slate-600 transition-all duration-500"
                    title={`Cancelled: ${batch.cancelled_jobs}`}
                  />
                </div>
              </div>

              {/* Metrics Pill Row */}
              <div className="grid grid-cols-4 gap-2 pt-2 border-t border-slate-800/60 text-center">
                <div className="bg-slate-950/50 p-2 rounded-lg border border-slate-800/40">
                  <p className="text-[10px] text-slate-400">Total</p>
                  <p className="text-xs font-bold text-white font-mono">{batch.total_jobs}</p>
                </div>
                <div className="bg-emerald-950/20 p-2 rounded-lg border border-emerald-900/30">
                  <p className="text-[10px] text-emerald-400">Completed</p>
                  <p className="text-xs font-bold text-emerald-300 font-mono">{batch.completed_jobs}</p>
                </div>
                <div className="bg-rose-950/20 p-2 rounded-lg border border-rose-900/30">
                  <p className="text-[10px] text-rose-400">Failed</p>
                  <p className="text-xs font-bold text-rose-300 font-mono">{batch.failed_jobs}</p>
                </div>
                <div className="bg-sky-950/20 p-2 rounded-lg border border-sky-900/30">
                  <p className="text-[10px] text-sky-400">Pending</p>
                  <p className="text-xs font-bold text-sky-300 font-mono">{batch.pending_jobs}</p>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-800/60 text-xs">
                <span className="text-slate-400 text-[11px]">
                  Created {new Date(batch.created_at).toLocaleTimeString()}
                </span>
                <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                  {batch.status === 'processing' && (
                    <button
                      onClick={() => handleCancelBatch(batch.id)}
                      className="px-2.5 py-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-[11px] font-medium transition-colors"
                    >
                      Cancel Batch
                    </button>
                  )}
                  {(batch.status === 'failed' ||
                    batch.status === 'partially_failed' ||
                    batch.status === 'cancelled') && (
                    <button
                      onClick={() => handleRetryBatch(batch.id)}
                      className="px-2.5 py-1 rounded bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 border border-sky-500/30 text-[11px] font-medium transition-colors"
                    >
                      Retry Failed
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {filteredBatches.length === 0 && !loading && (
        <div className="p-12 text-center rounded-xl bg-[#0B132B]/40 border border-slate-800">
          <Boxes className="w-10 h-10 text-slate-600 mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-slate-300">No Batches Found</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            Submit a batch job through the REST API or using the Batch Job Modal.
          </p>
        </div>
      )}
    </div>
  );
}
