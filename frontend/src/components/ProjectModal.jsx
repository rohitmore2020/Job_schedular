import React, { useState, useEffect } from 'react';
import {
  FolderKanban,
  Plus,
  Edit3,
  Key,
  Copy,
  Check,
  Building2,
  ShieldCheck,
  X,
  Database,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { apiClient } from '../api/client';

export default function ProjectModal({
  isOpen,
  onClose,
  user,
  projects,
  selectedProject,
  onProjectCreated,
  onProjectUpdated,
}) {
  const [activeTab, setActiveTab] = useState('manage'); // 'manage' | 'create' | 'apikeys'
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [apiKeys, setApiKeys] = useState([]);
  const [newKeyName, setNewKeyName] = useState('');
  const [generatedKey, setGeneratedKey] = useState(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (selectedProject) {
      setEditName(selectedProject.name || '');
      setEditDescription(selectedProject.description || '');
      if (isOpen && activeTab === 'apikeys') {
        loadApiKeys(selectedProject.id);
      }
    }
  }, [selectedProject, isOpen, activeTab]);

  const loadApiKeys = async (projectId) => {
    try {
      setLoading(true);
      const res = await apiClient.getProjectApiKeys(projectId);
      setApiKeys(res.data || []);
    } catch (e) {
      console.error('Failed to load API keys:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProject = async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;

    try {
      setLoading(true);
      setError(null);
      const res = await apiClient.createProject({
        name: newName.trim(),
        description: newDescription.trim() || undefined,
      });
      const created = res.data;
      setNewName('');
      setNewDescription('');
      onProjectCreated(created);
      setActiveTab('manage');
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to create project');
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateProject = async (e) => {
    e.preventDefault();
    if (!selectedProject || !editName.trim()) return;

    try {
      setLoading(true);
      setError(null);
      const res = await apiClient.updateProject(selectedProject.id, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
      });
      onProjectUpdated(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to update project');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateApiKey = async (e) => {
    e.preventDefault();
    if (!selectedProject || !newKeyName.trim()) return;

    try {
      setLoading(true);
      setError(null);
      const res = await apiClient.createProjectApiKey(selectedProject.id, {
        name: newKeyName.trim(),
      });
      setGeneratedKey(res.data.api_key);
      setNewKeyName('');
      await loadApiKeys(selectedProject.id);
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to generate API key');
    } finally {
      setLoading(false);
    }
  };

  const handleCopyKey = () => {
    if (generatedKey) {
      navigator.clipboard.writeText(generatedKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="glass-panel w-full max-w-2xl relative border border-sky-500/30 shadow-2xl overflow-hidden animate-fadeIn">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/40">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-sky-500/15 border border-sky-500/30 flex items-center justify-center">
              <FolderKanban className="w-4 h-4 text-sky-400" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white tracking-tight">Project Management & Multi-Tenancy</h2>
              <div className="flex items-center gap-2 text-[11px] text-slate-400 mt-0.5">
                <Building2 className="w-3 h-3 text-slate-500" />
                <span>Org: <strong className="text-slate-300 font-semibold">{user?.organization?.name || 'Production Org'}</strong></span>
                <span>•</span>
                <span>Active: <strong className="text-sky-400 font-semibold">{selectedProject?.name || 'Default'}</strong></span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Multi-Tenancy Breadcrumb Banner */}
        <div className="px-6 py-2.5 bg-slate-900/60 border-b border-slate-800/80 flex items-center gap-2 text-[11px] text-slate-400">
          <span className="flex items-center gap-1 font-medium text-slate-300">
            <Building2 className="w-3.5 h-3.5 text-indigo-400" /> {user?.organization?.name || 'Organization'}
          </span>
          <ArrowRight className="w-3 h-3 text-slate-600" />
          <span className="flex items-center gap-1 font-semibold text-sky-400">
            <Database className="w-3.5 h-3.5 text-sky-400" /> {selectedProject?.name || 'Project'}
          </span>
          <ArrowRight className="w-3 h-3 text-slate-600" />
          <span className="flex items-center gap-1 text-slate-400">
            <Layers className="w-3.5 h-3.5 text-slate-500" /> Queues & Jobs (Isolated)
          </span>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-800 bg-slate-950/20 px-6">
          <button
            onClick={() => setActiveTab('manage')}
            className={`py-3 px-4 text-xs font-semibold border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'manage'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Edit3 className="w-3.5 h-3.5" />
            <span>Active Project Settings</span>
          </button>
          <button
            onClick={() => setActiveTab('create')}
            className={`py-3 px-4 text-xs font-semibold border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'create'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create New Project</span>
          </button>
          <button
            onClick={() => setActiveTab('apikeys')}
            className={`py-3 px-4 text-xs font-semibold border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === 'apikeys'
                ? 'border-sky-500 text-sky-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Key className="w-3.5 h-3.5" />
            <span>Project API Keys</span>
          </button>
        </div>

        {/* Tab Contents */}
        <div className="p-6">
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs">
              {error}
            </div>
          )}

          {/* TAB 1: MANAGE / RENAME ACTIVE PROJECT */}
          {activeTab === 'manage' && selectedProject && (
            <form onSubmit={handleUpdateProject} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">Project Name</label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Description</label>
                <textarea
                  rows={3}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  placeholder="Optional project details and environment notes..."
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500 resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3 p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-[11px]">
                <div>
                  <span className="text-slate-500 block">Project ID (UUID)</span>
                  <span className="font-mono text-slate-300 select-all">{selectedProject.id}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Slug / Namespace</span>
                  <span className="font-mono text-sky-400">{selectedProject.slug}</span>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-5 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-white font-semibold shadow-glow-cyan transition-all disabled:opacity-50"
                >
                  {loading ? 'Saving...' : 'Rename & Save Changes'}
                </button>
              </div>
            </form>
          )}

          {/* TAB 2: CREATE NEW PROJECT */}
          {activeTab === 'create' && (
            <form onSubmit={handleCreateProject} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">New Project Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Payments Microservice, AI Inference Pipeline"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Description</label>
                <textarea
                  rows={3}
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Describe the workload or environment for this project..."
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500 resize-none"
                />
              </div>

              <div className="p-3 rounded-lg bg-sky-500/10 border border-sky-500/20 text-[11px] text-sky-300 flex items-start gap-2">
                <ShieldCheck className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
                <p>
                  Projects provide full multi-tenant isolation. All queues, jobs, recurring cron schedules, and DLQ entries created in this project are scoped strictly to its namespace.
                </p>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-5 py-2 rounded-lg bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white font-semibold shadow-glow-cyan transition-all disabled:opacity-50"
                >
                  {loading ? 'Creating...' : 'Create Project'}
                </button>
              </div>
            </form>
          )}

          {/* TAB 3: PROJECT API KEYS */}
          {activeTab === 'apikeys' && (
            <div className="space-y-4 text-xs">
              {/* Generate Key Form */}
              <form onSubmit={handleGenerateApiKey} className="flex gap-2">
                <input
                  type="text"
                  required
                  placeholder="Key Identifier (e.g. backend-prod-agent)"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-white font-semibold transition-all disabled:opacity-50"
                >
                  Generate Key
                </button>
              </form>

              {/* Newly Generated Secret Banner */}
              {generatedKey && (
                <div className="p-3.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-[11px] uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5" /> API Key Generated — Copy Now!
                    </span>
                    <button
                      onClick={handleCopyKey}
                      className="px-2 py-0.5 rounded bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-200 text-[10px] font-bold flex items-center gap-1 transition-colors"
                    >
                      {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                      <span>{copied ? 'Copied!' : 'Copy Key'}</span>
                    </button>
                  </div>
                  <div className="p-2 rounded bg-slate-950/80 border border-slate-800 font-mono text-xs text-white break-all select-all">
                    {generatedKey}
                  </div>
                  <p className="text-[10px] text-slate-400">
                    This secret token will not be displayed again. Use it in the <code className="text-sky-300">X-API-Key</code> header for programmatic job dispatching.
                  </p>
                </div>
              )}

              {/* Existing API Keys Table */}
              <div className="space-y-2 pt-2">
                <h4 className="text-slate-400 font-semibold text-[11px]">Active Keys for {selectedProject?.name}</h4>
                {apiKeys.length > 0 ? (
                  <div className="rounded-lg border border-slate-800 overflow-hidden divide-y divide-slate-800">
                    {apiKeys.map((k) => (
                      <div key={k.id} className="p-3 bg-slate-900/50 flex items-center justify-between">
                        <div>
                          <p className="font-semibold text-white">{k.name}</p>
                          <p className="font-mono text-slate-400 text-[11px]">{k.prefix}</p>
                        </div>
                        <span className="text-[10px] text-slate-500">
                          Created {new Date(k.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-500 text-[11px] p-4 text-center border border-slate-800 rounded-lg bg-slate-950/40">
                    No API keys created yet for this project.
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
