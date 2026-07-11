import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import Page from './+page.svelte';
import { deleteTrip } from '$lib/api/trips.js';
import { goto } from '$app/navigation';
import type { TripOut } from '$lib/types/index.js';

vi.mock('$lib/api/trips.js', () => ({
	deleteTrip: vi.fn().mockResolvedValue(undefined)
}));

vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined)
}));

const mockTrip: TripOut = {
	id: 'abc',
	name: 'Weekend in Kraków',
	date: '2025-06-01',
	created_at: '2025-06-01T10:00:00Z',
	transport_mode: 'WALK',
	day_start_hour: 9,
	day_end_hour: 21,
	selected_place_ids: ['p1', 'p2'],
	optimizer_request: {
		place_ids: ['p1', 'p2'],
		transport_mode: 'WALK',
		day_start_hour: 9,
		day_end_hour: 21
	},
	optimizer_response: {
		steps: [],
		total_travel_time_s: 1800,
		total_visit_time_min: 90,
		total_wait_min: 15,
		transport_mode: 'WALK',
		skipped: []
	}
};

describe('/trips/[id] page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('renders trip name in heading', async () => {
		const { getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		expect(getByText('Weekend in Kraków')).toBeTruthy();
	});

	it('renders trip date', async () => {
		const { getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		expect(getByText(/2025-06-01/)).toBeTruthy();
	});

	it('renders transport mode', async () => {
		const { getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		expect(getByText('WALK')).toBeTruthy();
	});

	it('renders day time window', async () => {
		const { getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		expect(getByText('9:00 – 21:00')).toBeTruthy();
	});

	it('renders travel, visit and wait metrics', async () => {
		const { getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		expect(getByText('30m')).toBeTruthy();
		expect(getByText('90 min')).toBeTruthy();
		expect(getByText('15 min')).toBeTruthy();
	});

	it('renders backend error when backendError is set', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: null,
					backendError: { message: 'Trip load failed', status: 503, source: 'backend' }
				}
			}
		});
		expect(getByText('Backend niedostępny')).toBeTruthy();
		expect(getByText('(503)')).toBeTruthy();
	});

	it('renders back link to /trips', async () => {
		const { getByRole } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		const backLink = getByRole('link', { name: /Zapisane trasy/ }).element();
		expect(backLink.getAttribute('href')).toBe('/trips');
	});

	it('renders open-in-optimizer link with trip id', async () => {
		const { getByRole } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		const link = getByRole('link', { name: 'Otwórz w planerze trasy' }).element();
		expect(link.getAttribute('href')).toBe('/optimizer?from=abc');
	});

	it('delete button opens confirm dialog with trip name', async () => {
		const { getByRole, getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		await userEvent.click(getByRole('button', { name: 'Usuń trasę' }));
		expect(
			getByText(
				'Czy na pewno chcesz usunąć trasę "Weekend in Kraków"? Tej operacji nie można cofnąć.'
			)
		).toBeTruthy();
	});

	it('confirm calls deleteTrip and navigates to /trips with deleted param', async () => {
		const { getByRole } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		await userEvent.click(getByRole('button', { name: 'Usuń trasę' }));
		await userEvent.click(getByRole('button', { name: 'Usuń', exact: true }));
		expect(deleteTrip).toHaveBeenCalledWith('abc');
		expect(goto).toHaveBeenCalledWith(`/trips?deleted=${encodeURIComponent('Weekend in Kraków')}`);
	});

	it('cancel closes dialog without calling the API', async () => {
		const { getByRole, getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		await userEvent.click(getByRole('button', { name: 'Usuń trasę' }));
		await userEvent.click(getByRole('button', { name: 'Anuluj' }));
		expect(deleteTrip).not.toHaveBeenCalled();
		expect(getByText('Usuwanie trasy').query()).toBeNull();
	});

	it('shows error toast when delete fails', async () => {
		vi.mocked(deleteTrip).mockRejectedValueOnce(new Error('boom'));
		const { getByRole, getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trip: mockTrip, backendError: null } }
		});
		await userEvent.click(getByRole('button', { name: 'Usuń trasę' }));
		await userEvent.click(getByRole('button', { name: 'Usuń', exact: true }));
		expect(getByText('Nie udało się usunąć trasy. Spróbuj ponownie.')).toBeTruthy();
		expect(goto).not.toHaveBeenCalled();
	});
});
