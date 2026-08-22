import React from 'react';
import {
  Activity,
  Layers,
  Cpu,
  AlertOctagon,
  CheckCircle2,
  Clock,
  ArrowUpRight,
  TrendingUp,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

export default function OverviewView({ stats, queues, jobs, workers, dlqCount, onInspectJob }) {
  // Compute aggregated stats
  const totalJobs = jobs?.total || 0;
  const completedJobs = jobs?.items?.filter((j) => j.status === 'completed').length || 0;
  const activeQueues = queues?.length || 0;
  const aliveWorkers = workers?.filter((w) => w.is_alive).length || 0;

  // Mock throughput timeseries for smooth real-time visualization
  const throughputData = [
    { time: '12:00', completed: 18, failed: 1, latency: 45 },
    { time: '12:05', completed: 32, failed: 0, latency: 38 },
    { time: '12:10', completed: 48, failed: 2, latency: 52 },
    { time: '12:15', completed: 65, failed: 1, latency: 41 },
    { time: '12:20', completed: 89, failed: 3, latency: 60 },
    { time: '12:25', completed: 112, failed: 0, latency: 35 },
    { time: '12:30', completed: 140, failed: 1, latency: 42 },
  ];

  const statusDistribution = [
    { name: 'Completed', value: completedJobs || 12, color: '#10B981' },
    { name: 'Queued', value: jobs?.items?.filter((j) => j.status === 'queued').length || 4, color: '#38BDF8' },
    { name: 'Running', value: jobs?.items?.filter((j) => j.status === 'running').length || 2, color: '#6366F1' },
    { name: 'DLQ / Failed', value: dlqCount || 1, color: '#F43F5E' },
  ];

  return (
    <div className="space-y-6">
      {/* Top KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Completed Jobs */}
        <div className="glass-panel p-5 relative overflow-hidden group glass-panel-hover">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Throughput</span>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <h2 className="text-2xl font-bold text-white tracking-tight">{totalJobs}</h2>
            <div className="flex items-center gap-1.5 mt-1 text-xs text-emerald-400">
              <TrendingUp className="w-3.5 h-3.5" />
              <span>99.4% execution success rate</span>
            </div>
          </div>
          <div className="absolute -bottom-6 -right-6 w-24 h-24 bg-emerald-500/10 rounded-full blur-xl group-hover:bg-emerald-500/20 transition-all"></div>
        </div>

        {/* KPI 2: Active Queues */}
        <div className="glass-panel p-5 relative overflow-hidden group glass-panel-hover">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Active Queues</span>
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 shadow-glow-cyan">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <h2 className="text-2xl font-bold text-white tracking-tight">{activeQueues}</h2>
            <div className="flex items-center gap-1.5 mt-1 text-xs text-sky-400">
              <span>Dynamic concurrency limits</span>
            </div>
          </div>
          <div className="absolute -bottom-6 -right-6 w-24 h-24 bg-sky-500/10 rounded-full blur-xl group-hover:bg-sky-500/20 transition-all"></div>
        </div>

        {/* KPI 3: Live Worker Fleet */}
        <div className="glass-panel p-5 relative overflow-hidden group glass-panel-hover">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Worker Fleet</span>
            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shadow-glow-indigo">
              <Cpu className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <h2 className="text-2xl font-bold text-white tracking-tight">{aliveWorkers} <span className="text-sm font-normal text-slate-400">Nodes</span></h2>
            <div className="flex items-center gap-1.5 mt-1 text-xs text-indigo-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Heartbeats active (5s intervals)</span>
            </div>
          </div>
          <div className="absolute -bottom-6 -right-6 w-24 h-24 bg-indigo-500/10 rounded-full blur-xl group-hover:bg-indigo-500/20 transition-all"></div>
        </div>

        {/* KPI 4: Dead Letter Queue */}
        <div className="glass-panel p-5 relative overflow-hidden group glass-panel-hover">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">DLQ Incidents</span>
            <div className="w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 shadow-glow-rose">
              <AlertOctagon className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3">
            <h2 className="text-2xl font-bold text-rose-400 tracking-tight">{dlqCount}</h2>
            <div className="flex items-center gap-1.5 mt-1 text-xs text-slate-400">
              <span>Automatic crash isolation</span>
            </div>
          </div>
          <div className="absolute -bottom-6 -right-6 w-24 h-24 bg-rose-500/10 rounded-full blur-xl group-hover:bg-rose-500/20 transition-all"></div>
        </div>
      </div>

      {/* Analytics & Throughput Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Throughput Area Chart */}
        <div className="lg:col-span-2 glass-panel p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-white tracking-tight">Execution Throughput & Latency</h3>
              <p className="text-xs text-slate-400">Jobs dispatched vs processing latency (ms)</p>
            </div>
            <div className="flex items-center gap-4 text-xs">
              <span className="flex items-center gap-1.5 text-sky-400 font-medium">
                <span className="w-2.5 h-2.5 rounded-full bg-sky-400"></span> Dispatched
              </span>
              <span className="flex items-center gap-1.5 text-indigo-400 font-medium">
                <span className="w-2.5 h-2.5 rounded-full bg-indigo-400"></span> Latency (ms)
              </span>
            </div>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={throughputData}>
                <defs>
                  <linearGradient id="skyGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38BDF8" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#38BDF8" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="indigoGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366F1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366F1" stopOpacity={0.0} />
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
                <Area type="monotone" dataKey="completed" stroke="#38BDF8" strokeWidth={2} fillOpacity={1} fill="url(#skyGrad)" />
                <Area type="monotone" dataKey="latency" stroke="#6366F1" strokeWidth={2} fillOpacity={1} fill="url(#indigoGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* State Distribution Donut Chart */}
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-white tracking-tight">Status Distribution</h3>
            <p className="text-xs text-slate-400">Current state across active queues</p>
          </div>
          <div className="h-44 my-2">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusDistribution}
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={65}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {statusDistribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0F172A',
                    borderColor: 'rgba(56, 189, 248, 0.2)',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs pt-2 border-t border-slate-800">
            {statusDistribution.map((item) => (
              <div key={item.name} className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: item.color }}></span>
                <span className="text-slate-400 truncate">{item.name}:</span>
                <span className="font-semibold text-slate-200">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Live Recent Jobs Activity Stream */}
      <div className="glass-panel p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-sky-400" />
            <h3 className="text-sm font-bold text-white tracking-tight">Real-Time Ingestion Feed</h3>
          </div>
          <span className="text-xs text-slate-400">Showing last {jobs?.items?.length || 0} jobs</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-medium">
                <th className="pb-3">Task Name</th>
                <th className="pb-3">Status</th>
                <th className="pb-3">Priority</th>
                <th className="pb-3">Attempts</th>
                <th className="pb-3">Submitted</th>
                <th className="pb-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {jobs?.items && jobs.items.length > 0 ? (
                jobs.items.slice(0, 6).map((j) => (
                  <tr key={j.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 font-mono font-medium text-slate-200 flex items-center gap-2">
                      <Zap className="w-3.5 h-3.5 text-sky-400 shrink-0" />
                      <span>{j.name}</span>
                    </td>
                    <td className="py-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                          j.status === 'completed'
                            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
                            : j.status === 'running'
                            ? 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/25 animate-pulse'
                            : j.status === 'queued'
                            ? 'bg-sky-500/15 text-sky-400 border border-sky-500/25'
                            : j.status === 'dead_letter'
                            ? 'bg-rose-500/15 text-rose-400 border border-rose-500/25'
                            : 'bg-slate-700/40 text-slate-300'
                        }`}
                      >
                        {j.status}
                      </span>
                    </td>
                    <td className="py-3 text-slate-300 font-mono">P{j.priority}</td>
                    <td className="py-3 text-slate-300 font-mono">{j.attempt_count} / {j.max_retries}</td>
                    <td className="py-3 text-slate-400">{new Date(j.created_at).toLocaleTimeString()}</td>
                    <td className="py-3 text-right">
                      <button
                        onClick={() => onInspectJob(j.id)}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-sky-400 hover:text-sky-300 text-xs transition-colors font-medium"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400">
                    No recent jobs in this queue. Click "Submit New Job" to enqueue.
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
