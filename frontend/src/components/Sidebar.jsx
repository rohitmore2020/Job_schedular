import React from 'react';
import {
  LayoutDashboard,
  Layers,
  ListOrdered,
  AlertOctagon,
  Clock,
  Cpu,
  PlusCircle,
  LogOut,
  Boxes,
  Zap,
  Terminal,
  Activity,
} from 'lucide-react';

export default function Sidebar({ currentTab, setCurrentTab, user, onLogout, openSubmitModal }) {
  const navItems = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard, badge: null },
    { id: 'queues', label: 'Queues', icon: Layers, badge: null },
    { id: 'jobs', label: 'Jobs', icon: ListOrdered, badge: null },
    { id: 'batches', label: 'Batch Jobs', icon: Boxes, badge: 'NEW', badgeColor: 'bg-sky-500/20 text-sky-400 border border-sky-500/30' },
    { id: 'dlq', label: 'Dead Letter Queue', icon: AlertOctagon, badge: 'DLQ', badgeColor: 'bg-rose-500/20 text-rose-400 border border-rose-500/30' },
    { id: 'schedules', label: 'Cron Schedules', icon: Clock, badge: null },
    { id: 'workers', label: 'Worker Fleet', icon: Cpu, badge: 'LIVE', badgeColor: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' },
  ];

  return (
    <aside className="w-64 h-screen bg-[#080E1A] border-r border-slate-800/80 flex flex-col justify-between shrink-0 select-none z-30">
      {/* Brand Header */}
      <div>
        <div className="h-16 px-6 flex items-center gap-3 border-b border-slate-800/80">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center shadow-glow-cyan">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold tracking-tight text-white text-base">CODITY</span>
              <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20">v2.0</span>
            </div>
            <p className="text-[11px] text-slate-400 tracking-wide font-medium">Distributed Scheduler</p>
          </div>
        </div>

        {/* Action Button */}
        <div className="px-4 pt-5 pb-3">
          {user?.role === 'viewer' ? (
            <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 text-center text-[11px] text-slate-400">
              <span className="font-semibold text-amber-400">👁️ Viewer Mode</span>
              <p className="text-[10px] text-slate-500 mt-0.5">Read-only monitoring</p>
            </div>
          ) : (
            <button
              onClick={openSubmitModal}
              className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white font-medium text-xs tracking-wide flex items-center justify-center gap-2 shadow-glow-cyan transition-all transform active:scale-[0.98]"
            >
              <PlusCircle className="w-4 h-4" />
              <span>Submit New Job</span>
            </button>
          )}
        </div>

        {/* Navigation Items */}
        <nav className="px-3 py-2 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = currentTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setCurrentTab(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition-all ${
                  active
                    ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30 shadow-glow-cyan font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${active ? 'text-sky-400' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${item.badgeColor}`}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* User Footer Card with RBAC Role Badge */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/40">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white uppercase shrink-0 shadow-sm">
              {user?.full_name?.charAt(0) || 'U'}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <p className="text-xs font-semibold text-slate-200 truncate">{user?.full_name || 'Engineer'}</p>
                <span
                  className={`text-[9px] font-extrabold uppercase px-1 py-0.2 rounded border ${
                    user?.role === 'admin'
                      ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                      : user?.role === 'member'
                      ? 'bg-sky-500/15 text-sky-300 border-sky-500/30'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  {user?.role === 'admin' ? 'ADMIN' : user?.role === 'member' ? 'MEMBER' : 'VIEWER'}
                </span>
              </div>
              <p className="text-[10px] text-slate-400 truncate">{user?.organization?.name || 'Production Org'}</p>
            </div>
          </div>
          <button
            onClick={onLogout}
            title="Sign Out"
            className="p-1.5 rounded text-slate-400 hover:text-rose-400 hover:bg-slate-800/50 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
