import type { AccommodationStay } from '$lib/types/index.js';

// AccommodationStay.lat/lng are required, so this in-progress row shape lets lat/lng stay null until resolved.
export interface AccommodationDraft {
	localKey: string;
	name: string;
	lat: number | null;
	lng: number | null;
	check_in_date: string;
	check_out_date: string;
	check_in_from: string | null;
	check_out_by: string | null;
}

export function emptyAccommodationDraft(localKey: string, date: string): AccommodationDraft {
	return {
		localKey,
		name: '',
		lat: null,
		lng: null,
		check_in_date: date,
		check_out_date: date,
		check_in_from: null,
		check_out_by: null
	};
}

export function stayToDraft(localKey: string, stay: AccommodationStay): AccommodationDraft {
	return {
		localKey,
		name: stay.name,
		lat: stay.lat,
		lng: stay.lng,
		check_in_date: stay.check_in_date,
		check_out_date: stay.check_out_date,
		check_in_from: stay.check_in_from ?? null,
		check_out_by: stay.check_out_by ?? null
	};
}

// Mirrors validate_stay_covers_at_least_one_night in src/accommodations/models.py.
export function isCompleteAccommodationDraft(draft: AccommodationDraft): boolean {
	return (
		draft.name.trim().length > 0 &&
		draft.lat !== null &&
		draft.lng !== null &&
		draft.check_out_date > draft.check_in_date
	);
}

// Throws on an incomplete draft — the hard invariant against a null-coordinate AccommodationStay ever being built.
export function draftToStay(draft: AccommodationDraft): AccommodationStay {
	if (draft.lat === null || draft.lng === null || !isCompleteAccommodationDraft(draft)) {
		throw new Error('Cannot convert an incomplete accommodation draft to AccommodationStay');
	}
	return {
		name: draft.name.trim(),
		lat: draft.lat,
		lng: draft.lng,
		check_in_date: draft.check_in_date,
		check_out_date: draft.check_out_date,
		check_in_from: draft.check_in_from,
		check_out_by: draft.check_out_by
	};
}

// Mirrors validate_no_stay_overlaps in src/accommodations/models.py; incomplete drafts are ignored.
export function hasNoStayOverlaps(drafts: AccommodationDraft[]): boolean {
	const complete = drafts.filter(isCompleteAccommodationDraft);
	const ordered = [...complete].sort((a, b) => (a.check_in_date < b.check_in_date ? -1 : 1));
	for (let i = 1; i < ordered.length; i++) {
		if (ordered[i].check_in_date < ordered[i - 1].check_out_date) return false;
	}
	return true;
}
