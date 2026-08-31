import type { components, paths } from './generated/api.js';

export type SingleDaySaveTripRequest = components['schemas']['SingleDaySaveTripRequest'];
export type MultiDaySaveTripRequest = components['schemas']['MultiDaySaveTripRequest'];
export type SaveTripRequest =
	paths['/api/v1/core/trips/']['post']['requestBody']['content']['application/json'];

export type SingleDayTripSummaryOut = components['schemas']['SingleDayTripSummaryOut'];
export type MultiDayTripSummaryOut = components['schemas']['MultiDayTripSummaryOut'];
export type TripSummaryOut =
	paths['/api/v1/core/trips/']['get']['responses'][200]['content']['application/json'][number];

export type SingleDayTripOut = components['schemas']['SingleDayTripDetailOut'];
export type MultiDayTripOut = components['schemas']['MultiDayTripDetailOut'];
export type TripOut =
	paths['/api/v1/core/trips/{trip_id}']['get']['responses'][200]['content']['application/json'];

export type TripRevisionSummaryOut = components['schemas']['TripRevisionSummaryOut'];
export type TripRevisionListOut = components['schemas']['TripRevisionListOut'];
export type SingleDayTripRevisionOut = components['schemas']['SingleDayTripRevisionDetailOut'];
export type MultiDayTripRevisionOut = components['schemas']['MultiDayTripRevisionDetailOut'];
export type TripRevisionOut =
	paths['/api/v1/core/trips/{trip_id}/revisions/{revision}']['get']['responses'][200]['content']['application/json'];
export type RestoreRevisionRequest = components['schemas']['RestoreRevisionRequest'];
export type RevisionSource = TripRevisionSummaryOut['source'];
