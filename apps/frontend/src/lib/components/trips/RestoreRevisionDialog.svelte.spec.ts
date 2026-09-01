import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import RestoreRevisionDialog from './RestoreRevisionDialog.svelte';
import { restoreTripRevision } from '$lib/api/trips.js';
import { invalidate } from '$app/navigation';
import { ApiError } from '$lib/api/client.js';

vi.mock('$lib/api/trips.js', () => ({
	restoreTripRevision: vi.fn()
}));
vi.mock('$app/navigation', () => ({
	invalidate: vi.fn().mockResolvedValue(undefined)
}));

const mockRestore = vi.mocked(restoreTripRevision);

describe('RestoreRevisionDialog', () => {
	beforeEach(() => vi.clearAllMocks());

	it('confirming calls restoreTripRevision with the current revision as the CAS token', async () => {
		mockRestore.mockResolvedValue({ revision: 3 } as never);
		const { getByRole } = render(RestoreRevisionDialog, {
			props: { open: true, tripId: 'abc', targetRevision: 1, currentRevision: 2 }
		});
		await userEvent.click(getByRole('button', { name: 'Przywróć' }));
		expect(mockRestore).toHaveBeenCalledWith('abc', 1, 2);
	});

	it('a successful restore invalidates the scoped trip key', async () => {
		mockRestore.mockResolvedValue({ revision: 3 } as never);
		const { getByRole } = render(RestoreRevisionDialog, {
			props: { open: true, tripId: 'abc', targetRevision: 1, currentRevision: 2 }
		});
		await userEvent.click(getByRole('button', { name: 'Przywróć' }));
		expect(invalidate).toHaveBeenCalledWith('app:trip:abc');
	});

	it('a 409 shows the reload-and-try-again message and keeps the dialog open', async () => {
		mockRestore.mockRejectedValue(new ApiError(409, 'conflict'));
		const { getByRole, getByTestId } = render(RestoreRevisionDialog, {
			props: { open: true, tripId: 'abc', targetRevision: 1, currentRevision: 2 }
		});
		await userEvent.click(getByRole('button', { name: 'Przywróć' }));
		expect(getByTestId('restore-conflict').query()).toBeTruthy();
		expect(invalidate).not.toHaveBeenCalled();
	});
});
