import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import Sidebar from '../components/Sidebar';

describe('Sidebar Component', () => {
  it('renders all navigation tabs and Codity branding', () => {
    const setCurrentTab = vi.fn();
    const openSubmitModal = vi.fn();

    render(
      <Sidebar
        currentTab="overview"
        setCurrentTab={setCurrentTab}
        user={{ role: 'admin' }}
        onLogout={vi.fn()}
        openSubmitModal={openSubmitModal}
      />
    );

    // Branding
    expect(screen.getByText('CODITY')).toBeInTheDocument();
    expect(screen.getByText('Distributed Scheduler')).toBeInTheDocument();

    // Nav items
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Queues')).toBeInTheDocument();
    expect(screen.getByText('Jobs')).toBeInTheDocument();
    expect(screen.getByText('Batch Jobs')).toBeInTheDocument();
    expect(screen.getByText('Dead Letter Queue')).toBeInTheDocument();
    expect(screen.getByText('Cron Schedules')).toBeInTheDocument();
    expect(screen.getByText('Worker Fleet')).toBeInTheDocument();
  });

  it('switches tabs when clicked', () => {
    const setCurrentTab = vi.fn();
    render(
      <Sidebar
        currentTab="overview"
        setCurrentTab={setCurrentTab}
        user={{ role: 'admin' }}
        onLogout={vi.fn()}
        openSubmitModal={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText('Jobs'));
    expect(setCurrentTab).toHaveBeenCalledWith('jobs');

    fireEvent.click(screen.getByText('Dead Letter Queue'));
    expect(setCurrentTab).toHaveBeenCalledWith('dlq');
  });

  it('triggers submit job modal when Submit New Job button clicked', () => {
    const openSubmitModal = vi.fn();
    render(
      <Sidebar
        currentTab="overview"
        setCurrentTab={vi.fn()}
        user={{ role: 'admin' }}
        onLogout={vi.fn()}
        openSubmitModal={openSubmitModal}
      />
    );

    fireEvent.click(screen.getByText('Submit New Job'));
    expect(openSubmitModal).toHaveBeenCalledTimes(1);
  });
});
