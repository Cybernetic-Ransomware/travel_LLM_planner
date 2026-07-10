import { describe, it, expect } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Page from './+page.svelte';
import type { TripSummaryOut } from '$lib/types/index.js';

const mockTrip: TripSummaryOut = {
	id: 'abc',
	name: 'Weekend in Kraków',
	date: '2025-06-01',
	created_at: '2025-06-01T10:00:00Z'
};

describe('/trips page', () => {
	it('renders the page title', async () => {
		const { getByRole } = render(Page, {
			props: { data: { orchestratorReady: true, trips: [], backendError: null } }
		});
		expect(getByRole('heading', { name: 'Zapisane trasy' })).toBeTruthy();
	});

	it('renders empty state when no trips', async () => {
		const { getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trips: [], backendError: null } }
		});
		expect(getByText('Nie masz jeszcze zapisanych tras.')).toBeTruthy();
	});

	it('renders backend error when backendError is set', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trips: [],
					backendError: { message: 'Service unavailable', status: 503, source: 'backend' }
				}
			}
		});
		expect(getByText('Backend niedostępny')).toBeTruthy();
		expect(getByText('(503)')).toBeTruthy();
	});

	it('renders trip card with name and date', async () => {
		const { getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trips: [mockTrip], backendError: null } }
		});
		expect(getByText('Weekend in Kraków')).toBeTruthy();
		expect(getByText(/2025-06-01/)).toBeTruthy();
	});

	it('link points to /trips/:id', async () => {
		const { getByText } = render(Page, {
			props: { data: { orchestratorReady: true, trips: [mockTrip], backendError: null } }
		});
		const nameEl = getByText('Weekend in Kraków').element();
		const link = nameEl.closest('a');
		expect(link?.getAttribute('href')).toBe('/trips/abc');
	});
});
