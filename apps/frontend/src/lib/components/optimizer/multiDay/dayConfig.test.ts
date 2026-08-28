import { describe, it, expect } from 'vitest';
import {
	hydrateBoundary,
	serializeBoundary,
	resolveBoundarySeconds,
	isValidBoundaryPair,
	defaultDayConfig,
	isDayConfigValid
} from './dayConfig.js';

describe('hydrateBoundary/serializeBoundary', () => {
	it('hydrates hour mode when time is null', () => {
		expect(hydrateBoundary(9, null)).toEqual({ mode: 'hour', hour: 9, time: null });
	});

	it('hydrates exact mode when time is set', () => {
		expect(hydrateBoundary(21, '14:30')).toEqual({ mode: 'exact', hour: 21, time: '14:30' });
	});

	it('serializes hour mode with time null', () => {
		expect(serializeBoundary({ mode: 'hour', hour: 8, time: null }, false)).toEqual({
			hour: 8,
			time: null
		});
	});

	it('serializes exact mode carrying the time through', () => {
		expect(serializeBoundary({ mode: 'exact', hour: 21, time: '18:00' }, true)).toEqual({
			hour: 21,
			time: '18:00'
		});
	});

	it('never serializes day_end_hour=24 together with an explicit end time', () => {
		const result = serializeBoundary({ mode: 'exact', hour: 24, time: '23:00' }, true);
		expect(result.time).toBe('23:00');
		expect(result.hour).not.toBe(24);
	});

	it('does not clamp hour=24 for a start boundary (only end is restricted)', () => {
		const result = serializeBoundary({ mode: 'exact', hour: 24, time: '01:00' }, false);
		expect(result.hour).toBe(24);
	});
});

describe('resolveBoundarySeconds', () => {
	it('resolves hour mode to hour*3600', () => {
		expect(resolveBoundarySeconds({ mode: 'hour', hour: 9, time: null })).toBe(9 * 3600);
	});

	it('resolves exact mode from the time string', () => {
		expect(resolveBoundarySeconds({ mode: 'exact', hour: 9, time: '14:30' })).toBe(
			14 * 3600 + 30 * 60
		);
	});

	it('resolves hour=24 to 86400 seconds (end-of-day sentinel)', () => {
		expect(resolveBoundarySeconds({ mode: 'hour', hour: 24, time: null })).toBe(24 * 3600);
	});
});

describe('isValidBoundaryPair', () => {
	it('accepts a normal hour-mode pair', () => {
		expect(
			isValidBoundaryPair(
				{ mode: 'hour', hour: 8, time: null },
				{ mode: 'hour', hour: 20, time: null }
			)
		).toEqual({ valid: true });
	});

	it('accepts a normal exact-mode pair', () => {
		expect(
			isValidBoundaryPair(
				{ mode: 'exact', hour: 9, time: '08:00' },
				{ mode: 'exact', hour: 21, time: '19:30' }
			)
		).toEqual({ valid: true });
	});

	it('rejects exact end time of 00:00 regardless of HTML min attribute', () => {
		const result = isValidBoundaryPair(
			{ mode: 'hour', hour: 8, time: null },
			{ mode: 'exact', hour: 21, time: '00:00' }
		);
		expect(result.valid).toBe(false);
		expect(result.errorKey).toBe('day_end_time_midnight_invalid');
	});

	it('accepts end hour=24 in hour mode', () => {
		expect(
			isValidBoundaryPair(
				{ mode: 'hour', hour: 8, time: null },
				{ mode: 'hour', hour: 24, time: null }
			)
		).toEqual({ valid: true });
	});

	it('rejects start === end', () => {
		const result = isValidBoundaryPair(
			{ mode: 'hour', hour: 9, time: null },
			{ mode: 'hour', hour: 9, time: null }
		);
		expect(result.valid).toBe(false);
		expect(result.errorKey).toBe('day_range_invalid');
	});

	it('rejects start > end', () => {
		const result = isValidBoundaryPair(
			{ mode: 'exact', hour: 9, time: '20:00' },
			{ mode: 'exact', hour: 9, time: '08:00' }
		);
		expect(result.valid).toBe(false);
		expect(result.errorKey).toBe('day_range_invalid');
	});
});

describe('defaultDayConfig', () => {
	it('builds a config with backend-matching hour defaults', () => {
		expect(defaultDayConfig('2026-01-01')).toEqual({
			date: '2026-01-01',
			day_start_hour: 9,
			day_end_hour: 21
		});
	});
});

describe('isDayConfigValid', () => {
	it('accepts the default day config', () => {
		expect(isDayConfigValid(defaultDayConfig('2026-01-01'))).toBe(true);
	});

	it('rejects a day whose exact end time is midnight', () => {
		expect(
			isDayConfigValid({
				date: '2026-01-01',
				day_start_hour: 9,
				day_end_hour: 21,
				day_end_time: '00:00'
			})
		).toBe(false);
	});

	it('rejects a day whose effective start is not before its effective end', () => {
		expect(isDayConfigValid({ date: '2026-01-01', day_start_hour: 20, day_end_hour: 9 })).toBe(
			false
		);
	});
});
