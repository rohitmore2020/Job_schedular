import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import SubmitJobModal from '../components/SubmitJobModal';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({
  apiClient: {
    createJob: vi.fn(),
    createBatchJobs: vi.fn(),
  },
}));

describe('SubmitJobModal Component', () => {
  const mockQueues = [
    { id: 'q-1', name: 'critical-queue' },
    { id: 'q-2', name: 'background-queue' },
  ];

  it('renders modal when isOpen is true and submits job payload', async () => {
    const onClose = vi.fn();
    const onJobSubmitted = vi.fn();
    apiClient.createJob.mockResolvedValue({ data: { id: 'job-999', status: 'queued' } });

    render(
      <SubmitJobModal
        isOpen={true}
        onClose={onClose}
        queues={mockQueues}
        selectedQueueId="q-1"
        onJobSubmitted={onJobSubmitted}
      />
    );

    expect(screen.getByText('Job Ingestion Playground')).toBeInTheDocument();
    expect(screen.getByDisplayValue(/critical-queue/)).toBeInTheDocument();

    const submitBtn = screen.getByRole('button', { name: /Enqueue Job/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(apiClient.createJob).toHaveBeenCalled();
      expect(onJobSubmitted).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <SubmitJobModal
        isOpen={false}
        onClose={vi.fn()}
        queues={mockQueues}
        selectedQueueId="q-1"
        onJobSubmitted={vi.fn()}
      />
    );

    expect(container.firstChild).toBeNull();
  });
});
