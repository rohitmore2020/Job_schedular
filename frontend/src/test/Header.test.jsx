import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import Header from '../components/Header';

describe('Header Component', () => {
  const mockProjects = [
    { id: 'proj-1', name: 'Production Project', slug: 'prod-proj' },
    { id: 'proj-2', name: 'Staging Project', slug: 'stage-proj' },
  ];

  it('renders project selector, WebSocket status badge, and refresh button', () => {
    const onRefresh = vi.fn();
    const openProjectModal = vi.fn();
    const setSelectedProject = vi.fn();

    render(
      <Header
        currentTab="jobs"
        projects={mockProjects}
        selectedProject={mockProjects[0]}
        setSelectedProject={setSelectedProject}
        wsConnected={true}
        onRefresh={onRefresh}
        loading={false}
        openProjectModal={openProjectModal}
      />
    );

    // Tab title
    expect(screen.getByText('Job Ingestion & Live Lifecycle')).toBeInTheDocument();

    // WebSocket Live Feed badge
    expect(screen.getByText('Live Stream')).toBeInTheDocument();

    // Project selection
    expect(screen.getByDisplayValue(/Production Project/)).toBeInTheDocument();

    // Refresh click
    const refreshBtn = screen.getByTitle('Refresh Data');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('displays polling sync status badge when WebSocket is disconnected', () => {
    render(
      <Header
        currentTab="overview"
        projects={mockProjects}
        selectedProject={mockProjects[0]}
        setSelectedProject={vi.fn()}
        wsConnected={false}
        onRefresh={vi.fn()}
        loading={false}
        openProjectModal={vi.fn()}
      />
    );

    expect(screen.getByText('Polling Sync')).toBeInTheDocument();
  });
});
