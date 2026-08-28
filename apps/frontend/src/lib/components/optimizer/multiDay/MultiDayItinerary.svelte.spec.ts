import { describe, it, expect } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import MultiDayItinerary from './MultiDayItinerary.svelte';
import type { DayPlan, DayRouteSegment, MultiDayResponse, RouteStep } from '$lib/types/index.js';

function step(id: string, name: string): RouteStep {
	return {
		place_id: id,
		name,
		lat: 50,
		lng: 20,
		arrival_time: '10:00:00',
		departure_time: '11:00:00',
		travel_from_previous_s: 300,
		visit_duration_min: 60,
		wait_min: 0
	};
}

function segment(kind: DayRouteSegment['kind'], steps: RouteStep[] = []): DayRouteSegment {
	return {
		kind,
		steps,
		total_travel_time_s: 300,
		total_visit_time_min: 60,
		total_wait_min: 0,
		skipped: []
	};
}

function ordinaryDay(index: number): DayPlan {
	return {
		day_index: index,
		date: `2026-03-0${index + 1}`,
		steps: [step(`p${index}`, `Place ${index}`)],
		total_travel_time_s: 300,
		total_visit_time_min: 60,
		total_wait_min: 0,
		skipped: []
	};
}

function transitionDay(overrides: Partial<DayPlan> = {}): DayPlan {
	return {
		day_index: 1,
		date: '2026-03-02',
		steps: [],
		total_travel_time_s: 0,
		total_visit_time_min: 0,
		total_wait_min: 0,
		skipped: [],
		transfer: {
			origin: { name: 'Hotel A', lat: 50, lng: 20 },
			destination: { name: 'Hotel B', lat: 51, lng: 21 },
			departure_time: '10:00:00',
			arrival_time: '11:30:00',
			duration_s: 5400
		},
		route_segments: [segment('PRE_TRANSFER'), segment('POST_TRANSFER')],
		...overrides
	};
}

function responseWith(
	days: DayPlan[],
	unassigned: MultiDayResponse['unassigned'] = []
): MultiDayResponse {
	return { days, transport_mode: 'WALK', unassigned };
}

describe('MultiDayItinerary', () => {
	it('renders an ordinary day using flat steps', async () => {
		const { getByText } = render(MultiDayItinerary, {
			props: { response: responseWith([ordinaryDay(0)]) }
		});
		expect(getByText('Place 0')).toBeTruthy();
	});

	it('renders PRE/transfer/POST as three separate blocks for a transition day', async () => {
		const day = transitionDay({
			route_segments: [
				segment('PRE_TRANSFER', [step('pre1', 'Pre Place')]),
				segment('POST_TRANSFER', [step('post1', 'Post Place')])
			]
		});
		const { getByText, getByTestId } = render(MultiDayItinerary, {
			props: { response: responseWith([day]) }
		});
		expect(getByTestId('pre-transfer-block').getByText('Pre Place')).toBeTruthy();
		expect(getByTestId('post-transfer-block').getByText('Post Place')).toBeTruthy();
		expect(getByText('Hotel A → Hotel B')).toBeTruthy();
	});

	it('shows a placeholder, not day.steps, when PRE has no stops', async () => {
		const day = transitionDay({
			route_segments: [
				segment('PRE_TRANSFER', []),
				segment('POST_TRANSFER', [step('post1', 'Post Place')])
			]
		});
		const { getByTestId } = render(MultiDayItinerary, { props: { response: responseWith([day]) } });
		expect(getByTestId('pre-transfer-block').getByText('Post Place').query()).toBeNull();
	});

	it('shows a placeholder when POST has no stops', async () => {
		const day = transitionDay({
			route_segments: [
				segment('PRE_TRANSFER', [step('pre1', 'Pre Place')]),
				segment('POST_TRANSFER', [])
			]
		});
		const { getByTestId } = render(MultiDayItinerary, { props: { response: responseWith([day]) } });
		expect(getByTestId('post-transfer-block').getByText('Pre Place').query()).toBeNull();
	});

	it('renders the transfer block even when both sides are empty (transfer-only day)', async () => {
		const day = transitionDay({
			route_segments: [segment('PRE_TRANSFER', []), segment('POST_TRANSFER', [])]
		});
		const { getByTestId } = render(MultiDayItinerary, { props: { response: responseWith([day]) } });
		expect(getByTestId('transfer-block')).toBeTruthy();
	});

	it('resolves segments by kind even when the solver order is reversed', async () => {
		const day = transitionDay({
			route_segments: [
				segment('POST_TRANSFER', [step('post1', 'Post Place')]),
				segment('PRE_TRANSFER', [step('pre1', 'Pre Place')])
			]
		});
		const { getByTestId } = render(MultiDayItinerary, { props: { response: responseWith([day]) } });
		expect(getByTestId('pre-transfer-block').getByText('Pre Place')).toBeTruthy();
		expect(getByTestId('post-transfer-block').getByText('Post Place')).toBeTruthy();
	});

	it('falls back to a humanized label for an unrecognized skip reason', async () => {
		const day = ordinaryDay(0);
		day.skipped = [{ place_id: 'x', name: 'Mystery Place', reason: 'SOME_NEW_BACKEND_REASON' }];
		const { getByText } = render(MultiDayItinerary, { props: { response: responseWith([day]) } });
		expect(getByText(/Mystery Place/)).toBeTruthy();
	});

	it('renders unassigned places once at the itinerary level', async () => {
		const { getByText } = render(MultiDayItinerary, {
			props: {
				response: responseWith(
					[ordinaryDay(0)],
					[{ place_id: 'u1', name: 'Unassigned Place', reason: 'CAPACITY_EXCEEDED' }]
				)
			}
		});
		expect(getByText('Unassigned Place')).toBeTruthy();
	});

	it('switching day tabs updates the rendered day and bound activeDayIndex', async () => {
		const { getByTestId, getByText } = render(MultiDayItinerary, {
			props: { response: responseWith([ordinaryDay(0), ordinaryDay(1)]), activeDayIndex: 0 }
		});
		expect(getByText('Place 0')).toBeTruthy();
		await userEvent.click(getByTestId('day-tab-1'));
		expect(getByText('Place 1')).toBeTruthy();
		expect(getByText('Place 0').query()).toBeNull();
	});
});
