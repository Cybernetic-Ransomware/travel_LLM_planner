import type { DaySlot } from '$lib/types/index.js';

// Toggling an already-checked day is a no-op, so it never loses preferred_hour_from/to on the existing slot.
export function toggleDaySlot(current: DaySlot[], dayIndex: number, checked: boolean): DaySlot[] {
	if (checked) {
		if (current.some((s) => s.day_index === dayIndex)) return current;
		return [...current, { day_index: dayIndex }];
	}
	return current.filter((s) => s.day_index !== dayIndex);
}

export function checkedDayIndices(slots: DaySlot[]): number[] {
	return slots.map((s) => s.day_index);
}

export function pruneSlotsToRange(slots: DaySlot[], numDays: number): DaySlot[] {
	return slots.filter((s) => s.day_index < numDays);
}

export type PlaceDaySelectionKind = 'AUTO' | 'PINNED' | 'FLEXIBLE';

// Mirrors PlaceDayPreference.day_preferences semantics: 0 slots = auto, 1 = pinned, 2+ = flexible.
export function placeDaySelectionKind(slots: DaySlot[]): PlaceDaySelectionKind {
	if (slots.length === 0) return 'AUTO';
	if (slots.length === 1) return 'PINNED';
	return 'FLEXIBLE';
}
