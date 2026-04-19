import { getPlaces, patchPlace, deletePlace } from '$lib/api/gmaps.js';
import type { PlaceOut, PlacePatch } from '$lib/types/index.js';

export class PlacesState {
	places = $state<PlaceOut[]>([]);
	filterSkipped = $state<boolean | null>(null);
	filterListName = $state<string | null>(null);
	loading = $state(false);
	error = $state<string | null>(null);

	readonly filtered = $derived(
		this.places.filter((p) => {
			if (this.filterSkipped !== null && p.skipped !== this.filterSkipped) return false;
			if (this.filterListName && p.list_name !== this.filterListName) return false;
			return true;
		})
	);

	readonly listNames = $derived(
		[...new Set(this.places.map((p) => p.list_name).filter((n): n is string => n !== null))].sort()
	);

	readonly stats = $derived({
		total: this.filtered.length,
		active: this.filtered.filter((p) => !p.skipped).length,
		enriched: this.filtered.filter((p) => p.enriched_at !== null).length,
		withHours: this.filtered.filter((p) => p.preferred_hour_from !== null).length
	});

	async load(params?: { skipped?: boolean; list_name?: string }): Promise<void> {
		this.loading = true;
		this.error = null;
		try {
			this.places = await getPlaces(params);
		} catch (err) {
			this.error = (err as Error).message;
		} finally {
			this.loading = false;
		}
	}

	async patch(id: string, patch: PlacePatch): Promise<void> {
		const index = this.places.findIndex((p) => p.id === id);
		if (index === -1) return;

		const previous = this.places[index];
		this.places[index] = { ...previous, ...patch } as PlaceOut;

		try {
			const updated = await patchPlace(id, patch);
			this.places[index] = updated;
		} catch (err) {
			this.places[index] = previous;
			this.error = (err as Error).message;
		}
	}

	async remove(id: string): Promise<void> {
		const previous = [...this.places];
		this.places = this.places.filter((p) => p.id !== id);

		try {
			await deletePlace(id);
		} catch (err) {
			this.places = previous;
			this.error = (err as Error).message;
		}
	}
}
