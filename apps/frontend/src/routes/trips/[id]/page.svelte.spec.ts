import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import Page from './+page.svelte';
import { deleteTrip } from '$lib/api/trips.js';
import { goto } from '$app/navigation';
import type { SingleDayTripOut, MultiDayTripOut } from '$lib/types/index.js';

vi.mock('$lib/api/trips.js', () => ({
	deleteTrip: vi.fn().mockResolvedValue(undefined),
	restoreTripRevision: vi.fn().mockResolvedValue({ revision: 1 }),
	getTripRevision: vi.fn().mockResolvedValue({}),
	getTripRevisions: vi
		.fn()
		.mockResolvedValue({ trip_id: 'abc', current_revision: 0, revisions: [] })
}));

vi.mock('$app/navigation', () => ({
	goto: vi.fn().mockResolvedValue(undefined),
	invalidate: vi.fn().mockResolvedValue(undefined)
}));

const chatMock = {
	setTripContext: vi.fn(),
	clearTripContext: vi.fn()
};
vi.mock('$lib/state/context.svelte.js', () => ({
	getChatContext: () => chatMock
}));

const mockTrip: SingleDayTripOut = {
	plan_type: 'SINGLE_DAY',
	id: 'abc',
	name: 'Weekend in Kraków',
	date: '2025-06-01',
	created_at: '2025-06-01T10:00:00Z',
	updated_at: null,
	revision: 0,
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

const mockMultiDayTrip: MultiDayTripOut = {
	plan_type: 'MULTI_DAY',
	id: 'multi-1',
	name: 'Kraków then Warsaw',
	start_date: '2025-08-01',
	end_date: '2025-08-03',
	num_days: 3,
	created_at: '2025-08-01T10:00:00Z',
	updated_at: null,
	revision: 0,
	transport_mode: 'WALK',
	multi_day_request: {
		days: [
			{ date: '2025-08-01', day_start_hour: 9, day_end_hour: 21 },
			{ date: '2025-08-02', day_start_hour: 9, day_end_hour: 21 },
			{ date: '2025-08-03', day_start_hour: 9, day_end_hour: 21 }
		],
		places: [],
		transport_mode: 'WALK'
	},
	multi_day_response: {
		days: [],
		transport_mode: 'WALK',
		unassigned: []
	}
};

const mockRevisions = {
	trip_id: 'abc',
	current_revision: 0,
	revisions: [
		{
			revision: 0,
			source: 'CREATED' as const,
			summary: 'Trip created',
			restored_from_revision: null,
			schema_version: 1,
			snapshot_hash: 'h0',
			recorded_at: '2025-06-01T10:00:00Z'
		}
	]
};

describe('/trips/[id] page', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('binds the chat to the trip context on mount and clears it on unmount', async () => {
		const { unmount } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(chatMock.setTripContext).toHaveBeenCalledWith('abc', 'SINGLE_DAY', expect.any(Function));
		unmount();
		expect(chatMock.clearTripContext).toHaveBeenCalled();
	});

	it('keeps the chat session when the same trip is re-fetched (no re-bind, no clear)', async () => {
		const { rerender } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockMultiDayTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(chatMock.setTripContext).toHaveBeenCalledTimes(1);

		// trip_updated -> invalidate -> load re-runs -> a fresh object with the same id
		await rerender({
			data: {
				orchestratorReady: true,
				trip: { ...mockMultiDayTrip },
				backendError: null,
				revisions: mockRevisions
			}
		});

		expect(chatMock.setTripContext).toHaveBeenCalledTimes(1);
		expect(chatMock.clearTripContext).not.toHaveBeenCalled();
	});

	it('re-binds the chat context when navigating to a different trip', async () => {
		const { rerender } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockMultiDayTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		await rerender({
			data: {
				orchestratorReady: true,
				trip: mockTrip,
				backendError: null,
				revisions: mockRevisions
			}
		});

		expect(chatMock.setTripContext).toHaveBeenCalledTimes(2);
		expect(chatMock.setTripContext).toHaveBeenLastCalledWith(
			'abc',
			'SINGLE_DAY',
			expect.any(Function)
		);
	});

	it('scoped-invalidates on a trip_updated callback, not invalidateAll', async () => {
		const { invalidate } = await import('$app/navigation');
		render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockMultiDayTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		const onUpdated = chatMock.setTripContext.mock.calls.at(-1)?.[2] as () => void;
		onUpdated();
		expect(invalidate).toHaveBeenCalledWith('app:trip:multi-1');
	});

	it('renders trip name in heading', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(getByText('Weekend in Kraków')).toBeTruthy();
	});

	it('renders trip date', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(getByText(/2025-06-01/)).toBeTruthy();
	});

	it('renders transport mode', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(getByText('WALK')).toBeTruthy();
	});

	it('renders day time window', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(getByText('9:00 – 21:00')).toBeTruthy();
	});

	it('renders travel, visit and wait metrics', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
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
					backendError: { message: 'Trip load failed', status: 503, source: 'backend' },
					revisions: null
				}
			}
		});
		expect(getByText('Backend niedostępny')).toBeTruthy();
		expect(getByText('(503)')).toBeTruthy();
	});

	it('renders back link to /trips', async () => {
		const { getByRole } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		const backLink = getByRole('link', { name: /Zapisane trasy/ }).element();
		expect(backLink.getAttribute('href')).toBe('/trips');
	});

	it('renders open-in-optimizer link with trip id', async () => {
		const { getByRole } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		const link = getByRole('link', { name: 'Otwórz w planerze trasy' }).element();
		expect(link.getAttribute('href')).toBe('/optimizer?from=abc');
	});

	it('delete button opens confirm dialog with trip name', async () => {
		const { getByRole, getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
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
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		await userEvent.click(getByRole('button', { name: 'Usuń trasę' }));
		await userEvent.click(getByRole('button', { name: 'Usuń', exact: true }));
		expect(deleteTrip).toHaveBeenCalledWith('abc');
		expect(goto).toHaveBeenCalledWith(`/trips?deleted=${encodeURIComponent('Weekend in Kraków')}`);
	});

	it('cancel closes dialog without calling the API', async () => {
		const { getByRole, getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		await userEvent.click(getByRole('button', { name: 'Usuń trasę' }));
		await userEvent.click(getByRole('button', { name: 'Anuluj' }));
		expect(deleteTrip).not.toHaveBeenCalled();
		expect(getByText('Usuwanie trasy').query()).toBeNull();
	});

	it('shows error toast when delete fails', async () => {
		vi.mocked(deleteTrip).mockRejectedValueOnce(new Error('boom'));
		const { getByRole, getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		await userEvent.click(getByRole('button', { name: 'Usuń trasę' }));
		await userEvent.click(getByRole('button', { name: 'Usuń', exact: true }));
		expect(getByText('Nie udało się usunąć trasy. Spróbuj ponownie.')).toBeTruthy();
		expect(goto).not.toHaveBeenCalled();
	});

	it('single-day rendering is unchanged (regression guard)', async () => {
		const { getByText, getByRole } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(getByText('Weekend in Kraków')).toBeTruthy();
		expect(getByText(/2025-06-01/)).toBeTruthy();
		expect(getByText('WALK')).toBeTruthy();
		expect(getByText('9:00 – 21:00')).toBeTruthy();
		expect(getByRole('link', { name: 'Otwórz w planerze trasy' })).toBeTruthy();
	});

	it('renders the multi-day trip summary (date range, day count, transport)', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockMultiDayTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(getByText('Kraków then Warsaw')).toBeTruthy();
		expect(getByText(/2025-08-01 – 2025-08-03/)).toBeTruthy();
		expect(getByText('3')).toBeTruthy();
		expect(getByText('WALK')).toBeTruthy();
	});

	it('multi-day detail does not access single-day-only fields', async () => {
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockMultiDayTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(getByText('Kraków then Warsaw')).toBeTruthy();
		expect(getByText('30m').query()).toBeNull();
		expect(getByText('90 min').query()).toBeNull();
	});

	it('shows the open-in-optimizer action for a multi-day trip too', async () => {
		const { getByRole } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: mockMultiDayTrip,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		const link = getByRole('link', { name: 'Otwórz w planerze trasy' }).element();
		expect(link.getAttribute('href')).toBe('/optimizer?from=multi-1');
	});

	it('renders the persisted multi-day itinerary, not a placeholder notice', async () => {
		const tripWithDay: MultiDayTripOut = {
			...mockMultiDayTrip,
			multi_day_response: {
				days: [
					{
						day_index: 0,
						date: '2025-08-01',
						steps: [
							{
								place_id: 'p1',
								name: 'Wawel',
								lat: 50,
								lng: 20,
								arrival_time: '10:00:00',
								departure_time: '11:00:00',
								travel_from_previous_s: 0,
								visit_duration_min: 60,
								wait_min: 0
							}
						],
						total_travel_time_s: 0,
						total_visit_time_min: 60,
						total_wait_min: 0,
						skipped: []
					}
				],
				transport_mode: 'WALK',
				unassigned: []
			}
		};
		const { getByText } = render(Page, {
			props: {
				data: {
					orchestratorReady: true,
					trip: tripWithDay,
					backendError: null,
					revisions: mockRevisions
				}
			}
		});
		expect(getByText('Wawel')).toBeTruthy();
	});
});
