import { describe, it, expect } from 'vitest';
import {
	addDays,
	reconcileDays,
	isStayRelevantToRange,
	pruneAccommodationsToRange,
	pruneTransfersToRange,
	resolveDayAnchors,
	isTransitionDay
} from './dayRangeReconciliation.js';
import type { DayConfig, TransferBlock } from '$lib/types/index.js';

function range(checkIn: string, checkOut: string) {
	return { check_in_date: checkIn, check_out_date: checkOut };
}

describe('addDays', () => {
	it('advances by whole days, crossing month boundaries', () => {
		expect(addDays('2026-01-31', 1)).toBe('2026-02-01');
	});
});

describe('reconcileDays', () => {
	it('grows the day list with defaults for new days', () => {
		const result = reconcileDays([], '2026-03-01', 3);
		expect(result.map((d) => d.date)).toEqual(['2026-03-01', '2026-03-02', '2026-03-03']);
		expect(result[0].day_start_hour).toBe(9);
	});

	it('shrinks the day list, dropping trailing days', () => {
		const existing: DayConfig[] = [
			{ date: '2026-03-01', day_start_hour: 8, day_end_hour: 20 },
			{ date: '2026-03-02', day_start_hour: 8, day_end_hour: 20 },
			{ date: '2026-03-03', day_start_hour: 8, day_end_hour: 20 }
		];
		const result = reconcileDays(existing, '2026-03-01', 2);
		expect(result).toHaveLength(2);
	});

	it('preserves per-day hour config and anchor overrides by index when dates realign', () => {
		const existing: DayConfig[] = [
			{ date: '2026-03-01', day_start_hour: 7, day_end_hour: 19, start_lat: 50.1, start_lng: 20.1 }
		];
		const result = reconcileDays(existing, '2026-03-01', 1);
		expect(result[0]).toEqual({
			date: '2026-03-01',
			day_start_hour: 7,
			day_end_hour: 19,
			start_lat: 50.1,
			start_lng: 20.1
		});
	});
});

describe('isStayRelevantToRange', () => {
	it('is relevant when fully inside the trip range', () => {
		expect(
			isStayRelevantToRange(range('2026-03-01', '2026-03-02'), '2026-03-01', '2026-03-03')
		).toBe(true);
	});

	it('is relevant when checkout is the day after the trip ends (last-day END anchor)', () => {
		expect(
			isStayRelevantToRange(range('2026-03-02', '2026-03-04'), '2026-03-01', '2026-03-03')
		).toBe(true);
	});

	it('is relevant when check-in is before the trip starts (first-day START anchor)', () => {
		expect(
			isStayRelevantToRange(range('2026-02-27', '2026-03-01'), '2026-03-01', '2026-03-03')
		).toBe(true);
	});

	it('is irrelevant when the stay ends before the trip starts', () => {
		expect(
			isStayRelevantToRange(range('2026-02-01', '2026-02-05'), '2026-03-01', '2026-03-03')
		).toBe(false);
	});

	it('is irrelevant when the stay starts after the trip ends', () => {
		expect(
			isStayRelevantToRange(range('2026-04-01', '2026-04-05'), '2026-03-01', '2026-03-03')
		).toBe(false);
	});
});

describe('pruneAccommodationsToRange', () => {
	it('keeps a stay only partially overlapping the new (shrunk) range', () => {
		const entries = [{ localKey: 'k1', ...range('2026-03-02', '2026-03-04') }];
		expect(pruneAccommodationsToRange(entries, '2026-03-01', '2026-03-02')).toHaveLength(1);
	});

	it('drops a stay that is fully irrelevant after shrinking', () => {
		const entries = [{ localKey: 'k1', ...range('2026-04-01', '2026-04-03') }];
		expect(pruneAccommodationsToRange(entries, '2026-03-01', '2026-03-02')).toHaveLength(0);
	});
});

describe('pruneTransfersToRange', () => {
	it('drops transfers whose date is no longer among the day dates', () => {
		const transfer: TransferBlock = {
			date: '2026-03-05',
			departure_time: '10:00',
			arrival_time: '11:00'
		};
		const transfers = new Map([[transfer.date, transfer]]);
		const result = pruneTransfersToRange(transfers, ['2026-03-01', '2026-03-02']);
		expect(result.size).toBe(0);
	});

	it('keeps transfers whose date remains a day date', () => {
		const transfer: TransferBlock = {
			date: '2026-03-02',
			departure_time: '10:00',
			arrival_time: '11:00'
		};
		const transfers = new Map([[transfer.date, transfer]]);
		const result = pruneTransfersToRange(transfers, ['2026-03-01', '2026-03-02']);
		expect(result.size).toBe(1);
	});
});

describe('resolveDayAnchors/isTransitionDay', () => {
	it('detects a transition day when START and END come from different stays', () => {
		const entries = [
			{ localKey: 'A', ...range('2026-02-28', '2026-03-02') },
			{ localKey: 'B', ...range('2026-03-02', '2026-03-04') }
		];
		const anchors = resolveDayAnchors(['2026-03-01', '2026-03-02', '2026-03-03'], entries);
		expect(isTransitionDay(anchors[0])).toBe(false);
		expect(isTransitionDay(anchors[1])).toBe(true);
		expect(anchors[1].start?.localKey).toBe('A');
		expect(anchors[1].end?.localKey).toBe('B');
		expect(isTransitionDay(anchors[2])).toBe(false);
	});
});
