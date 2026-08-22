import React, { useState, useEffect } from 'react';
import { Clock, Play, Pause, Trash2, Plus, Calendar, CheckCircle2 } from 'lucide-react';
import { apiClient } from '../api/client';

export default function SchedulesView({ queues, selectedQueueId, selectedProject, onRefresh }) {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [name, setName] = useState('');
  const [cronExpr, setCronExpr] = useState('*/10 * * * *');
  const [priority, setPriority] = useState(50);
  const [payloadText, setPayloadText] = useState('{\n  "mode": "automated_sweep"\n}');
  const [actionLoading, setActionLoading] = useState(null);

  const fetchSchedules = async () => {
    try {
      setLoading(true);
      const res = await apiClient.getSchedules({
        project_id: selectedProject?.id,
        queue_id: selectedQueueId || undefined,
      });
      setSchedules(res.data || []);
    } catch (e) {
      console.error('Error loading schedules:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchedules();
  }, [selectedProject, selectedQueueId]);

  const handleToggleSchedule = async (schedule) => {
    try {
      setActionLoading(schedule.id);
      if (schedule.is_active) {
        await apiClient.pauseSchedule(schedule.id);
      } else {
        await apiClient.resumeSchedule(schedule.id);
      }
      await fetchSchedules();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to toggle schedule state');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (scheduleId) => {
    if (!confirm('Are you sure you want to delete this recurring schedule?')) return;
    try {
      setActionLoading(scheduleId);
      await apiClient.deleteSchedule(scheduleId);
      await fetchSchedules();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to delete schedule');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCreateSchedule = async (e) => {
    e.preventDefault();
    if (!selectedQueueId && (!queues || queues.length === 0)) {
      alert('Please select or create a queue first');
      return;
    }
    const targetQueueId = selectedQueueId || queues[0].id;

    try {
      let parsedPayload = {};
      try {
        parsedPayload = JSON.parse(payloadText);
      } catch (err) {
        alert('Invalid JSON in payload');
        return;
      }

      await apiClient.createSchedule(targetQueueId, {
        name: name.trim(),
        cron_expression: cronExpr.trim(),
        payload: parsedPayload,
        priority: Number(priority),
      });

      setShowCreateModal(false);
      setName('');
      await fetchSchedules();
    } catch (e) {
      alert(e.response?.data?.detail || 'Failed to create schedule');
    }
  };

  const cronPresets = [
    { label: 'Every 5 mins', expr: '*/5 * * * *' },
    { label: 'Every 15 mins', expr: '*/15 * * * *' },
    { label: 'Hourly', expr: '0 * * * *' },
    { label: 'Daily at midnight', expr: '0 0 * * *' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white tracking-tight">Recurring Scheduled Cron Jobs</h2>
          <p className="text-xs text-slate-400">Automate background task sweeps and recurring micro-workflows.</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="py-2 px-4 rounded-lg bg-sky-500 hover:bg-sky-400 text-white text-xs font-semibold flex items-center gap-2 shadow-glow-cyan transition-all active:scale-95"
        >
          <Plus className="w-4 h-4" />
          <span>New Cron Schedule</span>
        </button>
      </div>

      {/* Schedules Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {schedules.length > 0 ? (
          schedules.map((s) => (
            <div
              key={s.id}
              className={`glass-panel p-6 border transition-all ${
                s.is_active ? 'border-sky-500/25 shadow-glow-cyan' : 'border-slate-800 opacity-70'
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="font-mono font-bold text-slate-200 text-sm">{s.name}</span>
                <span
                  className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                    s.is_active
                      ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                      : 'bg-slate-700/40 text-slate-400 border border-slate-700'
                  }`}
                >
                  {s.is_active ? 'ACTIVE CRON' : 'PAUSED'}
                </span>
              </div>

              {/* Cron Expression Pill */}
              <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between mb-4">
                <span className="text-[11px] text-slate-400">Cron Syntax:</span>
                <span className="font-mono text-sky-400 font-bold text-xs bg-sky-500/10 px-2 py-0.5 rounded border border-sky-500/20">
                  {s.cron_expression}
                </span>
              </div>

              {/* Timing Metadata */}
              <div className="space-y-2 text-xs mb-5">
                <div className="flex items-center justify-between text-slate-400">
                  <span>Next Execution:</span>
                  <span className="font-mono text-slate-200 font-medium">
                    {new Date(s.next_run_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'medium' })}
                  </span>
                </div>
                <div className="flex items-center justify-between text-slate-400">
                  <span>Lifetime Runs:</span>
                  <span className="font-mono text-slate-200 font-medium">{s.total_runs_count || 0} times</span>
                </div>
              </div>

              {/* Controls */}
              <div className="flex items-center gap-2 pt-3 border-t border-slate-800">
                <button
                  onClick={() => handleToggleSchedule(s)}
                  disabled={actionLoading === s.id}
                  className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all ${
                    s.is_active
                      ? 'bg-amber-500/15 hover:bg-amber-500/25 text-amber-400 border border-amber-500/30'
                      : 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30'
                  }`}
                >
                  {s.is_active ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                  <span>{s.is_active ? 'Pause' : 'Resume'}</span>
                </button>

                <button
                  onClick={() => handleDelete(s.id)}
                  disabled={actionLoading === s.id}
                  className="p-2 rounded-lg bg-slate-800 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 transition-colors"
                  title="Delete Schedule"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="col-span-3 glass-panel p-12 text-center text-slate-400">
            No recurring cron schedules registered. Click "New Cron Schedule" to configure automated recurring sweeps.
          </div>
        )}
      </div>

      {/* Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="glass-panel w-full max-w-md p-6 relative border border-sky-500/30 shadow-2xl">
            <h3 className="text-base font-bold text-white mb-1">Create Recurring Cron Schedule</h3>
            <p className="text-xs text-slate-400 mb-5">Define scheduled cron execution intervals.</p>

            <form onSubmit={handleCreateSchedule} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 mb-1 font-medium">Task / Schedule Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. generate_daily_analytics"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 mb-1 font-medium">Cron Expression (5-part)</label>
                <input
                  type="text"
                  required
                  placeholder="*/10 * * * *"
                  value={cronExpr}
                  onChange={(e) => setCronExpr(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono outline-none focus:border-sky-500"
                />
                {/* Presets */}
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {cronPresets.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => setCronExpr(p.expr)}
                      className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-sky-300 transition-colors"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-slate-300 mb-1 font-medium">Payload (JSON)</label>
                <textarea
                  rows={3}
                  value={payloadText}
                  onChange={(e) => setPayloadText(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sky-300 font-mono text-xs outline-none focus:border-sky-500"
                />
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
                  Save Schedule
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
