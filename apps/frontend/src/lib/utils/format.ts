export function formatDurationSeconds(seconds: number): string {
	const h = Math.floor(seconds / 3600);
	const m = Math.floor((seconds % 3600) / 60);
	if (h > 0) return `${h}h ${m}m`;
	return `${m}m`;
}

export function formatDurationMinutes(minutes: number): string {
	const h = Math.floor(minutes / 60);
	const m = minutes % 60;
	if (h > 0) return `${h}h ${m}m`;
	return `${m}m`;
}

export function formatTime(timeStr: string): string {
	return timeStr.slice(0, 5);
}

export function formatHour(hour: number | null): string {
	if (hour === null) return '—';
	return `${String(hour).padStart(2, '0')}:00`;
}
