import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Harness from './PlacesPageHarness.svelte';
import type { PlaceOut } from '$lib/types/index.js';

const mockPlace = (overrides: Partial<PlaceOut> = {}): PlaceOut => ({
	id: 'p1',
	name: 'Wawel Castle',
	address: 'Wawel 5, Kraków',
	maps_url: null,
	lat: 50.054,
	lng: 19.936,
	gmaps_place_id: null,
	list_name: 'Kraków',
	source_list_url: null,
	scraped_at: null,
	enriched_at: null,
	opening_hours: null,
	preferred_hour_from: null,
	preferred_hour_to: null,
	visit_duration_min: null,
	priority: 'normal',
	skipped: false,
	...overrides
});

const places = [
	mockPlace({ id: 'p1', name: 'Wawel Castle' }),
	mockPlace({ id: 'p2', name: 'Cloth Hall' })
];

function pageData(focusPlaceId: string | null) {
	return { orchestratorReady: true, places, backendError: null, focusPlaceId };
}

describe('/places page — focus deep link', () => {
	beforeEach(() => {
		vi.spyOn(HTMLElement.prototype, 'scrollIntoView').mockImplementation(() => {});
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('clears a filter that hides the focused place and shows its row', async () => {
		const { getByText } = render(Harness, {
			props: { data: pageData('p1'), initialFilterSkipped: true }
		});

		// p1 is active (skipped: false), so a "skipped only" filter would hide it unless cleared.
		await expect.element(getByText('Wawel Castle')).toBeVisible();
	});

	it('highlights the focused row', async () => {
		const { container } = render(Harness, {
			props: { data: pageData('p1'), initialFilterSkipped: true }
		});

		await vi.waitFor(() => {
			const row = container.querySelector('#place-row-p1');
			expect(row).not.toBeNull();
			expect(row?.className).toContain('ring-amber-400');
		});
	});

	it('scrolls the focused row into view', async () => {
		render(Harness, { props: { data: pageData('p1'), initialFilterSkipped: true } });

		await vi.waitFor(() => {
			expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
		});
	});

	it('focuses the preferred-hours-from input of the focused place', async () => {
		const { getByRole } = render(Harness, {
			props: { data: pageData('p1'), initialFilterSkipped: true }
		});

		await expect.element(getByRole('spinbutton').first()).toHaveFocus();
	});

	it('does nothing when the focused place id does not exist', async () => {
		const { container, getByText } = render(Harness, {
			props: { data: pageData('does-not-exist') }
		});

		await expect.element(getByText('Wawel Castle')).toBeVisible();
		expect(container.querySelector('.ring-amber-400')).toBeNull();
		expect(HTMLElement.prototype.scrollIntoView).not.toHaveBeenCalled();
	});

	it('does not highlight or focus anything when no focus id is given', async () => {
		const { container } = render(Harness, { props: { data: pageData(null) } });

		expect(container.querySelector('.ring-amber-400')).toBeNull();
		expect(HTMLElement.prototype.scrollIntoView).not.toHaveBeenCalled();
	});
});
