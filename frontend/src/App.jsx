import React, { useState, useEffect, useRef } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import OverviewView from './components/OverviewView';
import QueuesView from './components/QueuesView';
import JobsView from './components/JobsView';
import BatchesView from './components/BatchesView';
import DLQView from './components/DLQView';
import SchedulesView from './components/SchedulesView';
import WorkersView from './components/WorkersView';
import SubmitJobModal from './components/SubmitJobModal';
import JobDetailDrawer from './components/JobDetailDrawer';
import AuthModal from './components/AuthModal';
import ProjectModal from './components/ProjectModal';
import { apiClient } from './api/client';

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(localStorage.getItem('access_token')));
  const [user, setUser] = useState(null);
  const [currentTab, setCurrentTab] = useState('overview');

  // Multi-tenant project & queue state
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [queues, setQueues] = useState([]);
  const [selectedQueueId, setSelectedQueueId] = useState(null);
  const [jobs, setJobs] = useState({ items: [], total: 0 });
  const [workers, setWorkers] = useState([]);
  const [dlqCount, setDlqCount] = useState(0);

  // Modals & Drawers
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [showProjectModal, setShowProjectModal] = useState(false);
  const [inspectJobId, setInspectJobId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);

  // Initial Auth Check
  useEffect(() => {
    if (isAuthenticated) {
      loadInitialData();
      connectWebSocket();
    }
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [isAuthenticated]);

  // Load queues whenever selected project changes
  useEffect(() => {
    if (selectedProject) {
      loadQueues(selectedProject.id);
    }
  }, [selectedProject]);

  // Connect real-time WebSocket dynamically
  const connectWebSocket = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host; // e.g. localhost:3000 or localhost:5173
    const wsUrl = import.meta.env.VITE_WS_URL || `${protocol}//${host}/api/v1/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          refreshData();
        } catch (e) {}
      };

      ws.onclose = () => {
        setWsConnected(false);
        setTimeout(connectWebSocket, 5000);
      };
    } catch (e) {
      setWsConnected(false);
    }
  };

  const loadInitialData = async () => {
    try {
      setLoading(true);
      const resUser = await apiClient.getMe();
      setUser(resUser.data);

      const resProjects = await apiClient.getProjects();
      setProjects(resProjects.data || []);

      if (resProjects.data?.length > 0) {
        setSelectedProject(resProjects.data[0]);
      }
    } catch (e) {
      console.error('Error in initial load:', e);
      if (e.response?.status === 401) {
        setIsAuthenticated(false);
      }
    } finally {
      setLoading(false);
    }
  };

  const loadQueues = async (projectId) => {
    try {
      const resQueues = await apiClient.getQueues(projectId);
      setQueues(resQueues.data || []);
      if (resQueues.data?.length > 0 && !selectedQueueId) {
        setSelectedQueueId(resQueues.data[0].id);
      }
      await refreshData();
    } catch (e) {
      console.error('Error loading queues:', e);
    }
  };

  const refreshData = async () => {
    try {
      const [resJobs, resWorkers] = await Promise.all([
        apiClient.getJobs({
          project_id: selectedProject?.id,
          queue_id: selectedQueueId || undefined,
          page_size: 50,
        }),
        apiClient.getWorkers(),
      ]);
      setJobs(resJobs.data || { items: [], total: 0 });
      setWorkers(resWorkers.data || []);

      if (selectedQueueId) {
        const resDlq = await apiClient.getDLQ(selectedQueueId);
        setDlqCount(resDlq.data?.total || 0);
      }
    } catch (e) {
      console.error('Error refreshing scheduler data:', e);
    }
  };

  const handleProjectCreated = (newProject) => {
    setProjects((prev) => [newProject, ...prev]);
    setSelectedProject(newProject);
    setSelectedQueueId(null);
  };

  const handleProjectUpdated = (updatedProject) => {
    setProjects((prev) =>
      prev.map((p) => (p.id === updatedProject.id ? { ...p, ...updatedProject } : p))
    );
    setSelectedProject((prev) =>
      prev?.id === updatedProject.id ? { ...prev, ...updatedProject } : prev
    );
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setIsAuthenticated(false);
    setUser(null);
  };

  if (!isAuthenticated) {
    return <AuthModal onAuthenticated={() => setIsAuthenticated(true)} />;
  }

  return (
    <div className="flex h-screen bg-[#080E1A] text-slate-100 overflow-hidden font-sans">
      {/* Left Sidebar */}
      <Sidebar
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        user={user}
        onLogout={handleLogout}
        openSubmitModal={() => setShowSubmitModal(true)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <Header
          currentTab={currentTab}
          projects={projects}
          selectedProject={selectedProject}
          setSelectedProject={setSelectedProject}
          wsConnected={wsConnected}
          onRefresh={refreshData}
          loading={loading}
          openProjectModal={() => setShowProjectModal(true)}
        />

        {/* Scrollable View Container */}
        <main className="flex-1 p-8 overflow-y-auto">
          {currentTab === 'overview' && (
            <OverviewView
              queues={queues}
              jobs={jobs}
              workers={workers}
              dlqCount={dlqCount}
              selectedProject={selectedProject}
              onInspectJob={(id) => setInspectJobId(id)}
            />
          )}

          {currentTab === 'queues' && (
            <QueuesView
              queues={queues}
              selectedProject={selectedProject}
              onRefresh={refreshData}
            />
          )}

          {currentTab === 'jobs' && (
            <JobsView
              jobs={jobs}
              queues={queues}
              selectedQueueId={selectedQueueId}
              setSelectedQueueId={setSelectedQueueId}
              onInspectJob={(id) => setInspectJobId(id)}
              onRefresh={refreshData}
            />
          )}

          {currentTab === 'batches' && (
            <BatchesView />
          )}

          {currentTab === 'dlq' && (
            <DLQView
              queues={queues}
              selectedQueueId={selectedQueueId}
              setSelectedQueueId={setSelectedQueueId}
              onInspectJob={(id) => setInspectJobId(id)}
            />
          )}

          {currentTab === 'schedules' && (
            <SchedulesView
              queues={queues}
              selectedQueueId={selectedQueueId}
              selectedProject={selectedProject}
              onRefresh={refreshData}
            />
          )}

          {currentTab === 'workers' && (
            <WorkersView
              workers={workers}
              onRefresh={refreshData}
            />
          )}
        </main>
      </div>

      {/* Submit Job Modal */}
      <SubmitJobModal
        isOpen={showSubmitModal}
        onClose={() => setShowSubmitModal(false)}
        queues={queues}
        selectedQueueId={selectedQueueId}
        onJobSubmitted={refreshData}
      />

      {/* Project Management & Multi-Tenancy Modal */}
      <ProjectModal
        isOpen={showProjectModal}
        onClose={() => setShowProjectModal(false)}
        user={user}
        projects={projects}
        selectedProject={selectedProject}
        onProjectCreated={handleProjectCreated}
        onProjectUpdated={handleProjectUpdated}
      />

      {/* Job Detail & Log Inspector Drawer */}
      <JobDetailDrawer
        jobId={inspectJobId}
        onClose={() => setInspectJobId(null)}
        onRefresh={refreshData}
      />
    </div>
  );
}
