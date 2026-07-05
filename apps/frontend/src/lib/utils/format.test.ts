import { describe, it, expect } from 'vitest';
import {
	formatDurationSeconds,
	formatDurationMinutes,
	formatTime,
	formatHour,
	formatDateTime
} from './format.js';

describe('formatDurationSeconds', () => {
	it('formats sub-hour durations as minutes only', () => {
		expect(formatDurationSeconds(0)).toBe('0m');
		expect(formatDurationSeconds(59)).toBe('0m');
		expect(formatDurationSeconds(60)).toBe('1m');
		expect(formatDurationSeconds(3540)).toBe('59m');
	});

	it('formats durations of one hour or more with hours and minutes', () => {
		expect(formatDurationSeconds(3600)).toBe('1h 0m');
		expect(formatDurationSeconds(3661)).toBe('1h 1m');
		expect(formatDurationSeconds(7384)).toBe('2h 3m');
	});
});

describe('formatDurationMinutes', () => {
	it('formats sub-hour durations as minutes only', () => {
		expect(formatDurationMinutes(0)).toBe('0m');
		expect(formatDurationMinutes(45)).toBe('45m');
		expect(formatDurationMinutes(59)).toBe('59m');
	});

	it('formats durations of one hour or more with hours and minutes', () => {
		expect(formatDurationMinutes(60)).toBe('1h 0m');
		expect(formatDurationMinutes(90)).toBe('1h 30m');
		expect(formatDurationMinutes(125)).toBe('2h 5m');
	});
});

describe('formatTime', () => {
	it('extracts HH:MM from a time string', () => {
		expect(formatTime('09:30:00')).toBe('09:30');
		expect(formatTime('14:05:42')).toBe('14:05');
	});
});

describe('formatHour', () => {
	it('returns em-dash for null', () => {
		expect(formatHour(null)).toBe('—');
	});

	it('formats single-digit hours with leading zero', () => {
		expect(formatHour(0)).toBe('00:00');
		expect(formatHour(9)).toBe('09:00');
	});

	it('formats double-digit hours', () => {
		expect(formatHour(12)).toBe('12:00');
		expect(formatHour(23)).toBe('23:00');
	});
});

describe('formatDateTime', () => {
	it('returns a deterministic UTC-based string regardless of runtime locale', () => {
		expect(formatDateTime('2025-06-01T10:30:00Z')).toBe('2025-06-01 10:30');
	});

	it('truncates seconds', () => {
		expect(formatDateTime('2025-12-31T23:59:59Z')).toBe('2025-12-31 23:59');
	});

	it('produces the same output on every call (no locale variance)', () => {
		const value = '2026-03-15T08:05:00Z';
		expect(formatDateTime(value)).toBe(formatDateTime(value));
	});
});
