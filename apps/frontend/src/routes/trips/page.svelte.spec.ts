import { describe, it, expect } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Page from './+page.svelte';
import type { SingleDayTripSummaryOut, MultiDayTripSummaryOut } from '$lib/types/index.js';

const mockTrip: SingleDayTripSummaryOut = {
	plan_type: 'SINGLE_DAY',
	id: 'abc',
	name: 'Weekend in Kraków',
	date: '2025-06-01',
	created_at: '2025-06-01T10:00:00Z'
};

const mockMultiDayTrip: MultiDayTripSummaryOut = {
	plan_type: 'MULTI_DAY',
	id: 'multi-1',
	name: 'Kraków then Warsaw',
	start_date: '2025-08-01',
	end_date: '2025-08-03',
	num_days: 3,
	created_at: '2025-08-01T10:00:00Z'
};

describe('/trips page', () => {
	it('renders the page title', async () => {
		const { getByRole } = render(Page, {
			props: {
				data: { orchestratorReady: true, trips: [], backendError: null, deletedName: null }
			}
		});
		expect(getByRole('heading', { name: 'Zapisane trasy' })).toBeTruthy();
	});

	it('renders empty state when no trips', async () => {
		const { getByText } = render(Page, {
			props: {
				data: { orchestratorReady: true, trips: [], backendError: null, deletedName: null }
			}
		});
		expect(getByText('Nie masz jeszcze zapisanych tras.')).toBeTruthy();
	});

	it('empty state renders CTA link to optimizer', async () => {
		const { getByRole } = render(Page, {
			props: {
				data: { orchestratorReady: true, trips: [], backendError: null, deletedName: null }
			}
		});
		const cta = getByRole('link', { name: 'Zaplanuj pierwszą trasę' }).element();
		expect(cta.getAttribute('href')).toBe('/optimizer');
	});

	it('renders success toast when deletedName is set', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trips: [],
					backendError: null,
					deletedName: 'Weekend in Kraków'
				}
			}
		});
		expect(getByText('Trasa "Weekend in Kraków" została usunięta.')).toBeTruthy();
	});

	it('renders backend error when backendError is set', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trips: [],
					backendError: { message: 'Service unavailable', status: 503, source: 'backend' },
					deletedName: null
				}
			}
		});
		expect(getByText('Backend niedostępny')).toBeTruthy();
		expect(getByText('(503)')).toBeTruthy();
	});

	it('renders trip card with name and date', async () => {
		const { getByText } = render(Page, {
			props: {
				data: { orchestratorReady: true, trips: [mockTrip], backendError: null, deletedName: null }
			}
		});
		expect(getByText('Weekend in Kraków')).toBeTruthy();
		expect(getByText(/2025-06-01/)).toBeTruthy();
	});

	it('link points to /trips/:id', async () => {
		const { getByText } = render(Page, {
			props: {
				data: { orchestratorReady: true, trips: [mockTrip], backendError: null, deletedName: null }
			}
		});
		const nameEl = getByText('Weekend in Kraków').element();
		const link = nameEl.closest('a');
		expect(link?.getAttribute('href')).toBe('/trips/abc');
	});

	it('renders mixed single- and multi-day list without crashing', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trips: [mockTrip, mockMultiDayTrip],
					backendError: null,
					deletedName: null
				}
			}
		});
		expect(getByText('Weekend in Kraków')).toBeTruthy();
		expect(getByText('Kraków then Warsaw')).toBeTruthy();
	});

	it('multi-day card shows date range and day count instead of a single date', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trips: [mockMultiDayTrip],
					backendError: null,
					deletedName: null
				}
			}
		});
		expect(getByText(/2025-08-01 – 2025-08-03/)).toBeTruthy();
		expect(getByText(/Zakres dat/)).toBeTruthy();
		expect(getByText(/^Data trasy:/).query()).toBeNull();
	});
});
