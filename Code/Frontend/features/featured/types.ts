import type {components} from '@/lib/api.generated';

export type FeaturedRequest = components['schemas']['FeaturedRequestOut'];
export type FeaturedDecision = components['schemas']['FeaturedDecisionOut'];
export type FeaturedRequestStatus = FeaturedRequest['status'];
export type FeaturedDecisionAction = FeaturedDecision['action'];
