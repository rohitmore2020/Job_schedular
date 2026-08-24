import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import BatchesView from '../components/BatchesView';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({
  apiClient: {
    getBatches: vi.fn(),
    getBatchJobs: vi.fn(),
    cancelBatch: vi.fn(),
    retryBatch: vi.fn(),
  },
}));

describe('BatchesView Component', () => {
  const mockBatches = [
    {
      id: 'batch-xyz-100',
      name: 'Invoice Generation Batch',
      status: 'completed',
      total_jobs: 50,
      completed_jobs: 50,
      failed_jobs: 0,
      pending_jobs: 0,
      progress_percent: 100.0,
      created_at: '2026-08-24T12:00:00Z',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    apiClient.getBatches.mockResolvedValue({
      data: { items: mockBatches, total: 1 },
    });
    apiClient.getBatchJobs.mockResolvedValue({
      data: { items: [], total: 0 },
    });
  });

  it('renders batch list with completion percentage and status', async () => {
    render(<BatchesView />);

    await waitFor(() => {
      expect(screen.getByText('Invoice Generation Batch')).toBeInTheDocument();
    });

    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getAllByText('50').length).toBeGreaterThan(0);
    expect(screen.getByText('completed')).toBeInTheDocument();
  });
});
