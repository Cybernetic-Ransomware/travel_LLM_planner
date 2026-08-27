import { describe, it, expect } from 'vitest';
import {
	toggleDaySlot,
	checkedDayIndices,
	pruneSlotsToRange,
	placeDaySelectionKind
} from './placeDaySlots.js';
import type { DaySlot } from '$lib/types/index.js';

describe('toggleDaySlot', () => {
	it('adds a new bare slot when checking an unset day', () => {
		expect(toggleDaySlot([], 2, true)).toEqual([{ day_index: 2 }]);
	});

	it('is a no-op when the day is already checked, preserving preferred hours', () => {
		const current: DaySlot[] = [{ day_index: 1, preferred_hour_from: 10, preferred_hour_to: 14 }];
		expect(toggleDaySlot(current, 1, true)).toBe(current);
	});

	it('removes the whole slot object when unchecking', () => {
		const current: DaySlot[] = [
			{ day_index: 0, preferred_hour_from: 9, preferred_hour_to: 12 },
			{ day_index: 1 }
		];
		expect(toggleDaySlot(current, 0, false)).toEqual([{ day_index: 1 }]);
	});

	it('preserves untouched slots when toggling a different day', () => {
		const current: DaySlot[] = [{ day_index: 0, preferred_hour_from: 9, preferred_hour_to: 12 }];
		const next = toggleDaySlot(current, 3, true);
		expect(next[0]).toEqual({ day_index: 0, preferred_hour_from: 9, preferred_hour_to: 12 });
		expect(next).toContainEqual({ day_index: 3 });
	});
});

describe('checkedDayIndices', () => {
	it('extracts day indices only', () => {
		const slots: DaySlot[] = [{ day_index: 0 }, { day_index: 1, preferred_hour_from: 8 }];
		expect(checkedDayIndices(slots)).toEqual([0, 1]);
	});
});

describe('pruneSlotsToRange', () => {
	it('drops slots at or beyond the new day count', () => {
		const slots: DaySlot[] = [{ day_index: 0 }, { day_index: 1 }, { day_index: 2 }];
		expect(pruneSlotsToRange(slots, 2)).toEqual([{ day_index: 0 }, { day_index: 1 }]);
	});

	it('keeps preferred hours on surviving slots', () => {
		const slots: DaySlot[] = [{ day_index: 0, preferred_hour_from: 9, preferred_hour_to: 11 }];
		expect(pruneSlotsToRange(slots, 5)).toEqual(slots);
	});
});

describe('placeDaySelectionKind', () => {
	it('classifies zero slots as AUTO', () => {
		expect(placeDaySelectionKind([])).toBe('AUTO');
	});

	it('classifies one slot as PINNED', () => {
		expect(placeDaySelectionKind([{ day_index: 0 }])).toBe('PINNED');
	});

	it('classifies two or more slots as FLEXIBLE', () => {
		expect(placeDaySelectionKind([{ day_index: 0 }, { day_index: 1 }])).toBe('FLEXIBLE');
	});
});
