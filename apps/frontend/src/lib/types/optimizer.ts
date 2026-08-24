import type { components, paths } from './generated/api.js';

export type TransportMode = components['schemas']['TransportMode'];
export type TransportModeNoTransit = Exclude<TransportMode, 'TRANSIT'>;

export type OptimizeRequest =
	paths['/api/v1/core/optimizer/route']['post']['requestBody']['content']['application/json'];
export type OptimizeResponse =
	paths['/api/v1/core/optimizer/route']['post']['responses'][200]['content']['application/json'];

export type RouteStep = components['schemas']['RouteStep'];
export type SkippedPlace = components['schemas']['SkippedPlace'];

export type DayConfig = components['schemas']['DayConfig'];
export type DaySlot = components['schemas']['DaySlot'];
export type PlaceDayPreference = components['schemas']['PlaceDayPreference'];

export type AccommodationStay = components['schemas']['AccommodationStay'];
export type TransferBlock = components['schemas']['TransferBlock'];
export type TransferEndpoint = components['schemas']['TransferEndpoint'];
export type TransferSegment = components['schemas']['TransferSegment'];
export type DayRouteSegment = components['schemas']['DayRouteSegment'];
export type DayPlan = components['schemas']['DayPlan-Output'];

export type MultiDayRequest =
	paths['/api/v1/core/optimizer/trip']['post']['requestBody']['content']['application/json'];
export type MultiDayResponse =
	paths['/api/v1/core/optimizer/trip']['post']['responses'][200]['content']['application/json'];
