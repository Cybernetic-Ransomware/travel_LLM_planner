import type {
	DayConfig,
	DaySlot,
	MultiDayRequest,
	TransferBlock,
	TransportModeNoTransit
} from '$lib/types/index.js';
import type { AccommodationDraft } from './accommodationDraft.js';
import { isCompleteAccommodationDraft, draftToStay } from './accommodationDraft.js';
import { defaultDayConfig } from './dayConfig.js';

export interface MultiDayEditableState {
	days: DayConfig[];
	// Full DaySlot[] per place, never bare day-index arrays, so reopen+edit+rerun never drops preferred hours.
	placeSelections: Map<string, DaySlot[]>;
	transportMode: TransportModeNoTransit;
	// Drafts, not AccommodationStay — a row may still be missing coordinates while being edited.
	accommodations: AccommodationDraft[];
	transfers: Map<string, TransferBlock>;
	globalStart: { lat: number; lng: number } | null;
	globalEnd: { lat: number; lng: number } | null;
}

function localDateString(offsetDays = 0): string {
	const d = new Date(Date.now() + offsetDays * 86_400_000);
	const y = d.getFullYear();
	const mo = String(d.getMonth() + 1).padStart(2, '0');
	const day = String(d.getDate()).padStart(2, '0');
	return `${y}-${mo}-${day}`;
}

export function defaultEditableState(): MultiDayEditableState {
	return {
		days: [defaultDayConfig(localDateString())],
		placeSelections: new Map(),
		transportMode: 'WALK',
		accommodations: [],
		transfers: new Map(),
		globalStart: null,
		globalEnd: null
	};
}

// Gates submit — mirrors the invariant that buildMultiDayRequest never emits a null-coordinate AccommodationStay.
export function hasIncompleteAccommodation(state: MultiDayEditableState): boolean {
	return state.accommodations.some((draft) => !isCompleteAccommodationDraft(draft));
}

// Dehydrate: MultiDayEditableState -> MultiDayRequest. Never filters accommodations by range — see ADR-15.
export function buildMultiDayRequest(state: MultiDayEditableState): MultiDayRequest {
	return {
		days: state.days,
		places: [...state.placeSelections].map(([place_id, slots]) => ({
			place_id,
			day_preferences: slots
		})),
		transport_mode: state.transportMode,
		start_lat: state.globalStart?.lat ?? null,
		start_lng: state.globalStart?.lng ?? null,
		end_lat: state.globalEnd?.lat ?? null,
		end_lng: state.globalEnd?.lng ?? null,
		accommodations: state.accommodations.filter(isCompleteAccommodationDraft).map(draftToStay),
		transfers: [...state.transfers.values()]
	};
}
