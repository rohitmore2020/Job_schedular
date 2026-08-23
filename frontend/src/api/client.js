import axios from 'axios';

// Use relative /api/v1 by default so it works on any port / reverse proxy
const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT token automatically
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for auth errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_BASE}/auth/refresh`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem('access_token', res.data.access_token);
          localStorage.setItem('refresh_token', res.data.refresh_token);
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`;
          return api(error.config);
        } catch (e) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
        }
      }
    }
    return Promise.reject(error);
  }
);

export const apiClient = {
  // Auth
  signup: (data) => api.post('/auth/signup', data),
  login: (data) => api.post('/auth/login', data),
  getMe: () => api.get('/auth/me'),

  // Projects & Queues
  getProjects: () => api.get('/projects'),
  getProject: (projectId) => api.get(`/projects/${projectId}`),
  createProject: (data) => api.post('/projects', data),
  updateProject: (projectId, data) => api.put(`/projects/${projectId}`, data),
  getProjectApiKeys: (projectId) => api.get(`/projects/${projectId}/api-keys`),
  createProjectApiKey: (projectId, data) => api.post(`/projects/${projectId}/api-keys`, data),
  getQueues: (projectId) => api.get(`/projects/${projectId}/queues`),
  createQueue: (projectId, data) => api.post(`/projects/${projectId}/queues`, data),
  pauseQueue: (queueId) => api.post(`/queues/${queueId}/pause`),
  resumeQueue: (queueId) => api.post(`/queues/${queueId}/resume`),
  getQueueStats: (queueId) => api.get(`/queues/${queueId}/stats`),

  // Jobs
  getJobs: (params) => api.get('/jobs', { params }),
  getJob: (jobId) => api.get(`/jobs/${jobId}`),
  createJob: (queueId, data, idempotencyKey) =>
    api.post(`/queues/${queueId}/jobs`, data, {
      headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {},
    }),
  createBatchJobs: (queueId, data) => api.post(`/queues/${queueId}/jobs/batch`, data),
  cancelJob: (jobId) => api.post(`/jobs/${jobId}/cancel`),
  retryJob: (jobId) => api.post(`/jobs/${jobId}/retry`),
  getJobLogs: (jobId) => api.get(`/jobs/${jobId}/logs`),

  // Dead Letter Queue
  getDLQ: (queueId, params) => api.get(`/queues/${queueId}/dlq`, { params }),
  getDLQEntry: (dlqId) => api.get(`/dlq/${dlqId}`),
  replayDLQ: (dlqId) => api.post(`/dlq/${dlqId}/replay`),
  replayAllDLQ: (queueId) => api.post(`/queues/${queueId}/dlq/replay-all`),
  purgeDLQ: (dlqId) => api.delete(`/dlq/${dlqId}`),

  // Schedules (Cron)
  getSchedules: (params) => api.get('/schedules', { params }),
  createSchedule: (queueId, data) => api.post(`/queues/${queueId}/schedules`, data),
  pauseSchedule: (scheduleId) => api.post(`/schedules/${scheduleId}/pause`),
  resumeSchedule: (scheduleId) => api.post(`/schedules/${scheduleId}/resume`),
  deleteSchedule: (scheduleId) => api.delete(`/schedules/${scheduleId}`),

  // Batches
  getBatches: (params) => api.get('/batches', { params }),
  getBatch: (batchId) => api.get(`/batches/${batchId}`),
  getBatchJobs: (batchId, params) => api.get(`/batches/${batchId}/jobs`, { params }),
  createBatch: (queueId, data) => api.post(`/queues/${queueId}/batches`, data),
  cancelBatch: (batchId) => api.post(`/batches/${batchId}/cancel`),
  retryBatch: (batchId) => api.post(`/batches/${batchId}/retry`),

  // Workers & Fleet Telemetry
  getWorkers: () => api.get('/workers'),
  getWorkerHeartbeats: (workerId) => api.get(`/workers/${workerId}/heartbeats`),

  // Telemetry & Observability
  getTelemetry: (params) => api.get('/telemetry', { params }),
};
