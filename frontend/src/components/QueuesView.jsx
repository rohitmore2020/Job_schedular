import React, { useState } from 'react';
import { Layers, Play, Pause, Plus, Settings2, ShieldAlert, Cpu, CheckCircle } from 'lucide-react';
import { apiClient } from '../api/client';

export default function QueuesView({ queues, selectedProject, onRefresh }) {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newQueueName, setNewQueueName] = useState('');
  const [newPriority, setNewPriority] = useState(50);
  const [newConcurrency, setNewConcurrency] = useState(10);
  const [newStrategy, setNewStrategy] = useState('exponential');
  const [loadingAction, setLoadingAction] = useState(null);

  const handleTogglePause = async (queue) => {
    try {
      setLoadingAction(queue.id);
      if (queue.is_paused) {
        await apiClient.resumeQueue(queue.id);
      } else {
        await apiClient.pauseQueue(queue.id);
      }
      await onRefresh();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to update queue state');
    } finally {
      setLoadingAction(null);
    }
  };

  const handleCreateQueue = async (e) => {
    e.preventDefault();
    if (!selectedProject || !newQueueName.trim()) return;

    try {
      await apiClient.createQueue(selectedProject.id, {
        name: newQueueName.trim(),
        priority: Number(newPriority),
        concurrency_limit: Number(newConcurrency),
        retry_policy: {
          strategy: newStrategy,
          initial_interval_sec: 5,
          max_interval_sec: 3600,
          backoff_multiplier: 2.0,
          jitter: true,
        },
      });
      setShowCreateModal(false);
      setNewQueueName('');
      await onRefresh();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to create queue');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Active Queues & Concurrency Controls</h2>
          <p className="text-xs text-slate-400">Configure priorities, pause/resume workers, and adjust throughput caps.</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="py-2 px-4 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-xs font-semibold flex items-center gap-2 shadow-glow-cyan transition-all active:scale-95"
        >
          <Plus className="w-4 h-4" />
          <span>Create New Queue</span>
        </button>
      </div>

      {/* Queues Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {queues && queues.length > 0 ? (
          queues.map((q) => {
            const isPaused = q.is_paused;
            return (
              <div
                key={q.id}
                className={`glass-panel p-6 relative overflow-hidden transition-all ${
                  isPaused ? 'border-amber-500/30' : 'border-sky-500/20'
                }`}
              >
                {/* Top status bar */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-2.5 h-2.5 rounded-full ${
                        isPaused ? 'bg-amber-400' : 'bg-emerald-400 animate-pulse'
                      }`}
                    ></div>
                    <span className="text-xs font-mono font-bold text-slate-200">{q.name}</span>
                  </div>
                  <span
                    className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                      isPaused
                        ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                        : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                    }`}
                  >
                    {isPaused ? 'PAUSED' : 'ACTIVE'}
                  </span>
                </div>

                {/* Queue Specs */}
                <div className="grid grid-cols-2 gap-3 mb-5 text-xs">
                  <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800">
                    <span className="text-slate-400 text-[11px] block">Queue Priority</span>
                    <span className="font-mono font-bold text-slate-200 text-sm">P{q.priority}</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800">
                    <span className="text-slate-400 text-[11px] block">Concurrency Limit</span>
                    <span className="font-mono font-bold text-sky-400 text-sm">{q.concurrency_limit} max</span>
                  </div>
                </div>

                {/* Retry Policy Summary */}
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 mb-5 text-xs">
                  <div className="flex items-center justify-between text-slate-300">
                    <span className="text-[11px] text-slate-400">Retry Strategy:</span>
                    <span className="font-mono uppercase text-sky-300 font-semibold">
                      {q.retry_policy?.strategy || 'exponential'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-slate-300 mt-1 text-[11px]">
                    <span className="text-slate-400">Interval / Multiplier:</span>
                    <span className="font-mono text-slate-300">
                      {q.retry_policy?.initial_interval_sec || 5}s (×{q.retry_policy?.backoff_multiplier || 2})
                    </span>
                  </div>
                </div>

                {/* Controls */}
                <div className="flex items-center gap-2 pt-2 border-t border-slate-800/80">
                  <button
                    onClick={() => handleTogglePause(q)}
                    disabled={loadingAction === q.id}
                    className={`w-full py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
                      isPaused
                        ? 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30'
                        : 'bg-amber-500/15 hover:bg-amber-500/25 text-amber-400 border border-amber-500/30'
                    }`}
                  >
                    {isPaused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
                    <span>{isPaused ? 'Resume Processing' : 'Pause Queue'}</span>
                  </button>
                </div>
              </div>
            );
          })
        ) : (
          <div className="col-span-3 glass-panel p-12 text-center text-slate-400">
            No queues found in this project. Click "Create New Queue" to start.
          </div>
        )}
      </div>

      {/* Create Queue Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="glass-panel w-full max-w-md p-6 relative border border-sky-500/30 shadow-2xl">
            <h3 className="text-base font-bold text-white mb-1">Create Job Queue</h3>
            <p className="text-xs text-slate-400 mb-5">Configure isolated queue settings and retry backoff policies.</p>

            <form onSubmit={handleCreateQueue} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 mb-1 font-medium">Queue Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. video-rendering-high"
                  value={newQueueName}
                  onChange={(e) => setNewQueueName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 mb-1 font-medium">Priority (1-100)</label>
                  <input
                    type="number"
                    min="1"
                    max="100"
                    value={newPriority}
                    onChange={(e) => setNewPriority(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 mb-1 font-medium">Concurrency Limit</label>
                  <input
                    type="number"
                    min="1"
                    max="500"
                    value={newConcurrency}
                    onChange={(e) => setNewConcurrency(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-300 mb-1 font-medium">Retry Strategy</label>
                <select
                  value={newStrategy}
                  onChange={(e) => setNewStrategy(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500 cursor-pointer"
                >
                  <option value="exponential">Exponential Backoff with Full Jitter</option>
                  <option value="linear">Linear Backoff</option>
                  <option value="fixed">Fixed Delay</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-white font-semibold shadow-glow-cyan transition-all"
                >
                  Create Queue
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
