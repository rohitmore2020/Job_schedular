import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import DLQView from '../components/DLQView';
import { apiClient } from '../api/client';

// Mock apiClient
vi.mock('../api/client', () => ({
  apiClient: {
    getDLQ: vi.fn(),
    replayDLQ: vi.fn(),
    purgeDLQ: vi.fn(),
  },
}));

describe('DLQView Component', () => {
  const mockQueues = [{ id: 'q-1', name: 'payment-queue' }];

  const mockDLQData = {
    total: 1,
    items: [
      {
        id: 101,
        job_id: 'dead-job-777',
        queue_id: 'q-1',
        failed_reason: 'Exhausted 3 retry attempts. Last error: Stripe timeout',
        total_attempts: 3,
        last_error: 'Connection timeout after 30s',
        ai_failure_summary: '🤖 [AI Root Cause]: Payment gateway unreachable.\n💡 [Recommendation]: Retry with increased timeout.',
        moved_to_dlq_at: '2026-08-24T10:00:00Z',
        is_replayed: false,
        job: {
          id: 'dead-job-777',
          name: 'charge_subscription',
          status: 'dead_letter',
        },
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    apiClient.getDLQ.mockResolvedValue({ data: mockDLQData });
  });

  it('renders dead letter queue jobs and reveals AI diagnostics on expanding trace', async () => {
    render(
      <DLQView
        queues={mockQueues}
        selectedQueueId="q-1"
        setSelectedQueueId={vi.fn()}
        onInspectJob={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('charge_subscription')).toBeInTheDocument();
    });

    expect(screen.getByText(/Exhausted 3 retry attempts/)).toBeInTheDocument();

    // Click View Trace to open accordion
    const viewTraceBtn = screen.getByRole('button', { name: /View Trace/i });
    fireEvent.click(viewTraceBtn);

    expect(screen.getByText(/Payment gateway unreachable/)).toBeInTheDocument();
    expect(screen.getByText(/Retry with increased timeout/)).toBeInTheDocument();
  });

  it('triggers 1-click DLQ replay when Replay Job button is clicked', async () => {
    apiClient.replayDLQ.mockResolvedValue({ data: { success: true } });

    render(
      <DLQView
        queues={mockQueues}
        selectedQueueId="q-1"
        setSelectedQueueId={vi.fn()}
        onInspectJob={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('charge_subscription')).toBeInTheDocument();
    });

    const replayBtn = screen.getByRole('button', { name: /Replay Job/i });
    fireEvent.click(replayBtn);

    expect(apiClient.replayDLQ).toHaveBeenCalledWith(101);
  });
});
