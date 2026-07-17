import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import RouteResults from './RouteResults.svelte';
import * as m from '$lib/paraglide/messages.js';
import type { OptimizeResponse, PlaceOut, RouteStep, SkippedPlace } from '$lib/types/index.js';

const mockStep = (id: string, name: string): RouteStep => ({
	place_id: id,
	name,
	lat: 50.0,
	lng: 20.0,
	arrival_time: '09:00:00',
	departure_time: '10:00:00',
	travel_from_previous_s: 600,
	visit_duration_min: 60,
	wait_min: 0
});

const mockSkipped = (id: string, reason: SkippedPlace['reason']): SkippedPlace => ({
	place_id: id,
	name: `Skipped ${id}`,
	reason
});

const mockPlace = (id: string, priority: PlaceOut['priority']): PlaceOut => ({
	id,
	name: `Place ${id}`,
	address: null,
	maps_url: null,
	lat: 50.0,
	lng: 20.0,
	gmaps_place_id: null,
	list_name: null,
	source_list_url: null,
	scraped_at: null,
	enriched_at: null,
	opening_hours: null,
	preferred_hour_from: null,
	preferred_hour_to: null,
	visit_duration_min: null,
	priority,
	skipped: false
});

const mockResult = (steps: RouteStep[], skipped: SkippedPlace[]): OptimizeResponse => ({
	steps,
	total_travel_time_s: 1800,
	total_visit_time_min: 90,
	total_wait_min: 0,
	transport_mode: 'WALK',
	skipped
});

const summaryText = (locator: { element: () => Element }): string =>
	(locator.element().textContent ?? '').replace(/\s+/g, ' ').trim();

describe('RouteResults summary', () => {
	it('shows planned and skipped counts', async () => {
		const result = mockResult(
			[mockStep('p1', 'Wawel'), mockStep('p2', 'Sukiennice')],
			[mockSkipped('p3', 'DROPPED_LOW_PRIORITY')]
		);
		const { getByTestId } = render(RouteResults, { props: { result } });
		const summary = getByTestId('route-summary');
		await expect.element(summary).toBeVisible();
		const text = summaryText(summary);
		expect(text).toContain(`2 ${m.results_summary_planned()}`);
		expect(text).toContain(`1 ${m.results_summary_skipped()}`);
	});

	it('shows must-see kept count when places are provided', () => {
		const result = mockResult(
			[mockStep('p1', 'Wawel'), mockStep('p2', 'Sukiennice')],
			[mockSkipped('p3', 'TIME_WINDOW_INFEASIBLE')]
		);
		const places = [
			mockPlace('p1', 'must_see'),
			mockPlace('p2', 'normal'),
			mockPlace('p3', 'must_see')
		];
		const { getByTestId } = render(RouteResults, { props: { result, places } });
		const text = summaryText(getByTestId('route-summary'));
		expect(text).toContain(`1/2 ${m.results_summary_must_see_kept()}`);
	});

	it('hides the must-see stat when places are not provided', () => {
		const result = mockResult([mockStep('p1', 'Wawel')], []);
		const { getByTestId } = render(RouteResults, { props: { result } });
		const text = summaryText(getByTestId('route-summary'));
		expect(text).not.toContain(m.results_summary_must_see_kept());
	});

	it('hides the must-see stat when no place is must-see', () => {
		const result = mockResult([mockStep('p1', 'Wawel')], []);
		const places = [mockPlace('p1', 'normal'), mockPlace('p2', 'optional')];
		const { getByTestId } = render(RouteResults, { props: { result, places } });
		const text = summaryText(getByTestId('route-summary'));
		expect(text).not.toContain(m.results_summary_must_see_kept());
	});
});

describe('RouteResults skipped places', () => {
	it('passes onmarkmustsee through to SkippedPlaces', async () => {
		const onmarkmustsee = vi.fn();
		const result = mockResult([], [mockSkipped('p1', 'DROPPED_LOW_PRIORITY')]);
		const { getByRole } = render(RouteResults, { props: { result, onmarkmustsee } });

		await expect
			.element(getByRole('button', { name: m.skipped_action_mark_must_see() }))
			.toBeVisible();
	});

	it('passes promotedPlaceIds through to SkippedPlaces', () => {
		const onmarkmustsee = vi.fn();
		const result = mockResult([], [mockSkipped('p1', 'DROPPED_LOW_PRIORITY')]);
		const { getByRole } = render(RouteResults, {
			props: { result, onmarkmustsee, promotedPlaceIds: new Set(['p1']) }
		});

		expect(getByRole('button', { name: m.skipped_action_mark_must_see() }).query()).toBeNull();
	});

	it('passes promotingPlaceId through to SkippedPlaces', async () => {
		const onmarkmustsee = vi.fn();
		const result = mockResult([], [mockSkipped('p1', 'DROPPED_LOW_PRIORITY')]);
		const { getByRole } = render(RouteResults, {
			props: { result, onmarkmustsee, promotingPlaceId: 'p1' }
		});

		await expect
			.element(getByRole('button', { name: m.optimizer_preference_updating() }))
			.toBeVisible();
	});
});
