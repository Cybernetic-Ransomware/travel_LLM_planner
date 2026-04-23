import { getContext, setContext } from 'svelte';
import { PlacesState } from './places.svelte.js';
import { ChatState } from './chat.svelte.js';
import { ThemeState } from './theme.svelte.js';

const PLACES_KEY = Symbol('places');
const CHAT_KEY = Symbol('chat');
const THEME_KEY = Symbol('theme');

export function setPlacesContext(): PlacesState {
	const state = new PlacesState();
	setContext(PLACES_KEY, state);
	return state;
}

export function getPlacesContext(): PlacesState {
	return getContext<PlacesState>(PLACES_KEY);
}

export function setChatContext(): ChatState {
	const state = new ChatState();
	setContext(CHAT_KEY, state);
	return state;
}

export function getChatContext(): ChatState {
	return getContext<ChatState>(CHAT_KEY);
}

export function setThemeContext(): ThemeState {
	const state = new ThemeState();
	setContext(THEME_KEY, state);
	return state;
}

export function getThemeContext(): ThemeState {
	return getContext<ThemeState>(THEME_KEY);
}
