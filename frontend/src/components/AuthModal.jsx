import React, { useState } from 'react';
import { Zap, ShieldCheck, ArrowRight, Sparkles, Key } from 'lucide-react';
import { apiClient } from '../api/client';

export default function AuthModal({ onAuthenticated }) {
  const [isSignup, setIsSignup] = useState(false);
  const [email, setEmail] = useState('admin@distributed-scheduler.io');
  const [password, setPassword] = useState('Password123!');
  const [fullName, setFullName] = useState('Lead Platform Engineer');
  const [orgName, setOrgName] = useState('Enterprise Cloud Ops');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isSignup) {
        const res = await apiClient.signup({
          email: email.trim(),
          password: password.trim(),
          full_name: fullName.trim(),
          organization_name: orgName.trim(),
        });
        localStorage.setItem('access_token', res.data.access_token);
        localStorage.setItem('refresh_token', res.data.refresh_token);
      } else {
        const res = await apiClient.login({
          email: email.trim(),
          password: password.trim(),
        });
        localStorage.setItem('access_token', res.data.access_token);
        localStorage.setItem('refresh_token', res.data.refresh_token);
      }
      onAuthenticated();
    } catch (err) {
      setError(err.response?.data?.detail || 'Authentication failed. Please verify email and password.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = async (userEmail, userPass) => {
    setEmail(userEmail);
    setPassword(userPass);
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.login({
        email: userEmail,
        password: userPass,
      });
      localStorage.setItem('access_token', res.data.access_token);
      localStorage.setItem('refresh_token', res.data.refresh_token);
      onAuthenticated();
    } catch (e) {
      // If user doesn't exist, create it immediately
      try {
        const signRes = await apiClient.signup({
          email: userEmail,
          password: userPass,
          full_name: 'Lead Platform Engineer',
          organization_name: 'Codity Cloud Systems',
        });
        localStorage.setItem('access_token', signRes.data.access_token);
        localStorage.setItem('refresh_token', signRes.data.refresh_token);
        onAuthenticated();
      } catch (err) {
        setError(err.response?.data?.detail || 'Quick authentication error');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-[#080E1A] z-50 flex items-center justify-center p-4">
      {/* Background aurora glows */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96 bg-sky-500/10 rounded-full blur-3xl pointer-events-none"></div>
      <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>

      <div className="glass-panel w-full max-w-md p-8 relative border border-sky-500/20 shadow-2xl z-10">
        {/* Brand */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center shadow-glow-cyan mx-auto mb-3">
            <Zap className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-xl font-bold text-white tracking-tight">CODITY SCHEDULER</h1>
          <p className="text-xs text-slate-400 mt-1">High-Throughput Distributed Task Engine</p>
        </div>

        {/* 1-Click Demo Login Options */}
        <div className="space-y-2 mb-5">
          <button
            type="button"
            onClick={() => handleQuickLogin('admin@distributed-scheduler.io', 'Password123!')}
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 border border-sky-500/30 text-sky-300 font-semibold text-xs flex items-center justify-center gap-2 shadow-glow-cyan transition-all"
          >
            <Sparkles className="w-4 h-4 text-sky-400" />
            <span>1-Click Demo Login (admin@distributed-scheduler.io)</span>
          </button>

          <button
            type="button"
            onClick={() => handleQuickLogin('admin@acme.com', 'admin123')}
            disabled={loading}
            className="w-full py-2 px-3 rounded-lg bg-slate-900/80 hover:bg-slate-800 border border-slate-700/80 text-slate-300 font-medium text-xs flex items-center justify-center gap-2 transition-all"
          >
            <Key className="w-3.5 h-3.5 text-indigo-400" />
            <span>Alternate Demo: admin@acme.com</span>
          </button>
        </div>

        <div className="flex items-center gap-2 my-4 text-[10px] text-slate-500 uppercase tracking-widest font-semibold">
          <div className="flex-1 h-px bg-slate-800"></div>
          <span>Or Sign In Manually</span>
          <div className="flex-1 h-px bg-slate-800"></div>
        </div>

        {error && (
          <div className="p-3 mb-4 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs font-medium">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          {isSignup && (
            <>
              <div>
                <label className="block text-slate-300 mb-1 font-medium">Full Name</label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                />
              </div>
              <div>
                <label className="block text-slate-300 mb-1 font-medium">Organization Name</label>
                <input
                  type="text"
                  required
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                />
              </div>
            </>
          )}

          <div>
            <label className="block text-slate-300 mb-1 font-medium">Email Address</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
            />
          </div>

          <div>
            <label className="block text-slate-300 mb-1 font-medium">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white font-semibold text-xs shadow-glow-cyan transition-all active:scale-95 disabled:opacity-50 mt-2"
          >
            {loading ? 'Authenticating...' : isSignup ? 'Create Account & Organization' : 'Sign In to Dashboard'}
          </button>
        </form>

        <div className="text-center mt-5 text-xs text-slate-400">
          {isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button
            type="button"
            onClick={() => setIsSignup(!isSignup)}
            className="text-sky-400 hover:underline font-semibold"
          >
            {isSignup ? 'Sign In' : 'Sign Up'}
          </button>
        </div>
      </div>
    </div>
  );
}
