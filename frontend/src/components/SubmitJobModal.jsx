import React, { useState } from 'react';
import { PlusCircle, Layers, Zap, Sliders, Clock, Tag, ShieldCheck, X } from 'lucide-react';
import { apiClient } from '../api/client';

export default function SubmitJobModal({ isOpen, onClose, queues, selectedQueueId, onJobSubmitted }) {
  if (!isOpen) return null;

  const [mode, setMode] = useState('single'); // 'single' | 'batch'
  const [queueId, setQueueId] = useState(selectedQueueId || (queues?.[0]?.id || ''));
  const [taskName, setTaskName] = useState('send_email');
  const [priority, setPriority] = useState(30);
  const [maxRetries, setMaxRetries] = useState(3);
  const [delaySeconds, setDelaySeconds] = useState(0);
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [tagsText, setTagsText] = useState('production, email');
  const [payloadText, setPayloadText] = useState('{\n  "email": "customer@company.com",\n  "subject": "Monthly Statement"\n}');
  const [batchCount, setBatchCount] = useState(25);
  const [submitting, setSubmitting] = useState(false);

  const taskPresets = [
    { name: 'send_email', label: 'Send Email', payload: '{\n  "email": "client@example.com",\n  "subject": "Security Alert"\n}' },
    { name: 'process_video', label: 'Process Video (FFmpeg)', payload: '{\n  "video_url": "https://s3.aws.com/raw.mp4",\n  "codec": "h264"\n}' },
    { name: 'calculate_report', label: 'Calculate Report', payload: '{\n  "report_type": "quarterly_ledger"\n}' },
    { name: 'mock_failing_task', label: 'Failing Task (Trigger DLQ)', payload: '{\n  "error_type": "DatabaseTimeout"\n}' },
  ];

  const handleSelectPreset = (preset) => {
    setTaskName(preset.name);
    setPayloadText(preset.payload);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!queueId) {
      alert('Please select a target queue');
      return;
    }

    try {
      setSubmitting(true);
      let parsedPayload = {};
      try {
        parsedPayload = JSON.parse(payloadText);
      } catch (err) {
        alert('Invalid JSON in payload');
        setSubmitting(false);
        return;
      }

      const tags = tagsText
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);

      if (mode === 'single') {
        await apiClient.createJob(
          queueId,
          {
            name: taskName.trim(),
            payload: parsedPayload,
            priority: Number(priority),
            max_retries: Number(maxRetries),
            delay_seconds: Number(delaySeconds) > 0 ? Number(delaySeconds) : undefined,
            tags,
          },
          idempotencyKey.trim() || undefined
        );
      } else {
        // Batch submission
        const batchJobs = Array.from({ length: Number(batchCount) }, (_, i) => ({
          name: `${taskName.trim()}_${i + 1}`,
          payload: { ...parsedPayload, index: i + 1 },
          priority: Number(priority) + (i % 5),
          max_retries: Number(maxRetries),
          tags: [...tags, 'batch'],
        }));

        await apiClient.createBatchJobs(queueId, { jobs: batchJobs });
      }

      onJobSubmitted();
      onClose();
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to submit job');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-md z-50 flex items-center justify-center p-4">
      <div className="glass-panel w-full max-w-xl p-6 relative border border-sky-500/30 shadow-2xl overflow-y-auto max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
              <PlusCircle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white tracking-tight">Job Ingestion Playground</h3>
              <p className="text-xs text-slate-400">Submit immediate, delayed, or high-throughput batch tasks.</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Mode Tabs */}
        <div className="flex rounded-lg bg-slate-900/90 p-1 mb-5 border border-slate-800 text-xs font-semibold">
          <button
            type="button"
            onClick={() => setMode('single')}
            className={`flex-1 py-1.5 rounded-md transition-all ${
              mode === 'single' ? 'bg-sky-500 text-white shadow-glow-cyan' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Single Job
          </button>
          <button
            type="button"
            onClick={() => setMode('batch')}
            className={`flex-1 py-1.5 rounded-md transition-all ${
              mode === 'batch' ? 'bg-indigo-600 text-white shadow-glow-indigo' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Bulk Batch Ingestion (Up to 1,000)
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          {/* Target Queue */}
          <div>
            <label className="block text-slate-300 mb-1 font-medium">Target Queue</label>
            <select
              value={queueId}
              onChange={(e) => setQueueId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500 cursor-pointer"
            >
              {queues?.map((q) => (
                <option key={q.id} value={q.id}>
                  {q.name} (P{q.priority})
                </option>
              ))}
            </select>
          </div>

          {/* Task Type Presets */}
          <div>
            <label className="block text-slate-300 mb-1.5 font-medium">Task Handler Preset</label>
            <div className="grid grid-cols-2 gap-2">
              {taskPresets.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => handleSelectPreset(p)}
                  className={`p-2 rounded-lg text-left border transition-all ${
                    taskName === p.name
                      ? 'bg-sky-500/15 border-sky-500 text-sky-300 font-semibold'
                      : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700'
                  }`}
                >
                  <span className="block font-medium text-xs text-slate-200">{p.label}</span>
                  <span className="block font-mono text-[10px] text-slate-400 truncate">{p.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Priority & Retries Sliders */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="flex justify-between mb-1">
                <label className="text-slate-300 font-medium">Priority Score</label>
                <span className="font-mono text-sky-400 font-bold">P{priority}</span>
              </div>
              <input
                type="range"
                min="1"
                max="100"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="w-full accent-sky-400 cursor-pointer"
              />
            </div>
            <div>
              <div className="flex justify-between mb-1">
                <label className="text-slate-300 font-medium">Max Retries</label>
                <span className="font-mono text-indigo-400 font-bold">{maxRetries} max</span>
              </div>
              <input
                type="range"
                min="0"
                max="10"
                value={maxRetries}
                onChange={(e) => setMaxRetries(e.target.value)}
                className="w-full accent-indigo-400 cursor-pointer"
              />
            </div>
          </div>

          {/* Delay & Idempotency Key (Single Mode) */}
          {mode === 'single' ? (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-slate-300 mb-1 font-medium">Delay (Seconds from now)</label>
                <input
                  type="number"
                  min="0"
                  placeholder="0 (immediate)"
                  value={delaySeconds}
                  onChange={(e) => setDelaySeconds(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
                />
              </div>
              <div>
                <label className="block text-slate-300 mb-1 font-medium">Idempotency Key (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. order-uuid-1234"
                  value={idempotencyKey}
                  onChange={(e) => setIdempotencyKey(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white font-mono outline-none focus:border-sky-500"
                />
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-slate-300 mb-1 font-medium">Batch Job Count</label>
              <input
                type="number"
                min="2"
                max="500"
                value={batchCount}
                onChange={(e) => setBatchCount(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
              />
            </div>
          )}

          {/* Tags */}
          <div>
            <label className="block text-slate-300 mb-1 font-medium">Categorization Tags (comma separated)</label>
            <input
              type="text"
              value={tagsText}
              onChange={(e) => setTagsText(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-white outline-none focus:border-sky-500"
            />
          </div>

          {/* JSON Payload Editor */}
          <div>
            <label className="block text-slate-300 mb-1 font-medium">Input JSON Payload</label>
            <textarea
              rows={3}
              value={payloadText}
              onChange={(e) => setPayloadText(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sky-300 font-mono text-xs outline-none focus:border-sky-500"
            />
          </div>

          {/* Footer Submit */}
          <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="py-2 px-5 rounded-lg bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white font-semibold shadow-glow-cyan transition-all active:scale-95 disabled:opacity-50"
            >
              {submitting ? 'Submitting...' : mode === 'single' ? 'Enqueue Job' : `Enqueue ${batchCount} Jobs in Batch`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
