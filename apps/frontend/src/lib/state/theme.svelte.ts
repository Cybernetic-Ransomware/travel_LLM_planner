function getInitialDark(): boolean {
	if (typeof window === 'undefined') return false;
	const stored = localStorage.getItem('theme');
	if (stored !== null) return stored === 'dark';
	return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export class ThemeState {
	dark = $state(getInitialDark());

	toggle(): void {
		this.dark = !this.dark;
		localStorage.setItem('theme', this.dark ? 'dark' : 'light');
	}
}
