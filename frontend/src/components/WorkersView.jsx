import React, { useState, useEffect } from 'react';
import { Cpu, HardDrive, Activity, Radio, CheckCircle, Clock } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { apiClient } from '../api/client';

export default function WorkersView({ workers, onRefresh }) {
  const [selectedWorkerId, setSelectedWorkerId] = useState(null);
  const [heartbeats, setHeartbeats] = useState([]);
  const [loadingHb, setLoadingHb] = useState(false);

  useEffect(() => {
    if (workers && workers.length > 0 && !selectedWorkerId) {
      setSelectedWorkerId(workers[0].worker_id);
    }
  }, [workers]);

  useEffect(() => {
    if (selectedWorkerId) {
      loadHeartbeats(selectedWorkerId);
    }
  }, [selectedWorkerId]);

  const loadHeartbeats = async (workerId) => {
    try {
      setLoadingHb(true);
      const res = await apiClient.getWorkerHeartbeats(workerId);
      const formatted = (res.data || [])
        .slice(0, 30)
        .reverse()
        .map((h) => ({
          time: new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          cpu: Number(h.cpu_percent.toFixed(1)),
          memory: Number(h.memory_mb.toFixed(1)),
          active_jobs: h.active_jobs,
        }));
      setHeartbeats(formatted);
    } catch (e) {
      console.error('Error loading worker heartbeats:', e);
    } finally {
      setLoadingHb(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-bold text-white tracking-tight">Distributed Worker Nodes Fleet</h2>
        <p className="text-xs text-slate-400">Live CPU, memory telemetry, concurrency utilization, and node liveness.</p>
      </div>

      {/* Workers Nodes Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {workers && workers.length > 0 ? (
          workers.map((w) => {
            const isSelected = selectedWorkerId === w.worker_id;
            return (
              <div
                key={w.worker_id}
                onClick={() => setSelectedWorkerId(w.worker_id)}
                className={`glass-panel p-5 cursor-pointer border transition-all ${
                  isSelected
                    ? 'border-sky-400 shadow-glow-cyan bg-slate-900/90'
                    : 'border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2.5 h-2.5 rounded-full ${
                        w.is_alive ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'
                      }`}
                    ></span>
                    <span className="font-mono font-bold text-slate-200 text-xs truncate max-w-[180px]">
                      {w.worker_id}
                    </span>
                  </div>
                  <span
                    className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase ${
                      w.is_alive
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                        : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                    }`}
                  >
                    {w.is_alive ? 'ALIVE' : 'DEAD'}
                  </span>
                </div>

                <div className="space-y-2 text-xs text-slate-400 mb-4">
                  <div className="flex justify-between">
                    <span>Host / PID:</span>
                    <span className="font-mono text-slate-300 font-medium">
                      {w.hostname} (PID: {w.pid})
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Concurrency Limit:</span>
                    <span className="font-mono text-sky-400 font-semibold">{w.concurrency_limit} slots</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Active In-flight Jobs:</span>
                    <span className="font-mono text-indigo-400 font-semibold">{w.current_active_jobs} jobs</span>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span>Last Heartbeat:</span>
                    <span className="text-slate-400">{new Date(w.last_heartbeat_at).toLocaleTimeString()}</span>
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-800 text-[11px] text-sky-400 font-semibold flex items-center justify-between">
                  <span>{isSelected ? 'Viewing Telemetry' : 'Click to inspect metrics'}</span>
                  <Activity className="w-3.5 h-3.5" />
                </div>
              </div>
            );
          })
        ) : (
          <div className="col-span-3 glass-panel p-12 text-center text-slate-400">
            No active worker nodes registered yet.
          </div>
        )}
      </div>

      {/* Selected Worker Telemetry Timeseries */}
      {selectedWorkerId && (
        <div className="glass-panel p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-sky-400" />
                <h3 className="text-sm font-bold text-white tracking-tight">
                  Node Telemetry Time-Series: <span className="font-mono text-sky-400">{selectedWorkerId}</span>
                </h3>
              </div>
              <p className="text-xs text-slate-400">Real-time CPU percentage and Resident Memory MB metrics (5s interval).</p>
            </div>
            <div className="flex items-center gap-4 text-xs font-medium">
              <span className="flex items-center gap-1 text-sky-400">
                <span className="w-2.5 h-2.5 rounded-full bg-sky-400"></span> CPU %
              </span>
              <span className="flex items-center gap-1 text-purple-400">
                <span className="w-2.5 h-2.5 rounded-full bg-purple-400"></span> Memory (MB)
              </span>
            </div>
          </div>

          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={heartbeats}>
                <defs>
                  <linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38BDF8" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#38BDF8" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="memGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#A855F7" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#A855F7" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" stroke="#475569" fontSize={11} tickLine={false} />
                <YAxis stroke="#475569" fontSize={11} tickLine={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0F172A',
                    borderColor: 'rgba(56, 189, 248, 0.2)',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                />
                <Area type="monotone" dataKey="cpu" stroke="#38BDF8" strokeWidth={2} fillOpacity={1} fill="url(#cpuGrad)" />
                <Area type="monotone" dataKey="memory" stroke="#A855F7" strokeWidth={2} fillOpacity={1} fill="url(#memGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
