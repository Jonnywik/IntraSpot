export type OwnershipAction = 'accept' | 'decline' | 'revoke';
export type OwnershipOfferSnapshot = {id: string; version: number; status: string};
export type ReviewedOwnershipDecision = {transferId: string; version: number; action: OwnershipAction};
export type OwnershipCreateAttempt = {
  context: object;
  nomineeId: string;
  clientKey: string;
  payload: {nominee_id: string; client_key: string};
};

export function canLoadOwnershipData(input: {
  isDesktop: boolean;
  role: string;
  actorEligible: boolean;
  token: string | null | undefined;
}): boolean;
export function captureDecision(offer: OwnershipOfferSnapshot, action: OwnershipAction): ReviewedOwnershipDecision;
export function isDecisionCurrent(reviewed: ReviewedOwnershipDecision, offer: OwnershipOfferSnapshot | null | undefined): boolean;
export function decisionPayload(reviewed: ReviewedOwnershipDecision): {action: OwnershipAction; version: number};
export function matchesOfferAttempt(current: OwnershipCreateAttempt | null, context: object, nomineeId: string): boolean;
export function getOrCreateOfferAttempt(
  current: OwnershipCreateAttempt | null,
  context: object,
  nomineeId: string,
  createClientKey: () => string,
): OwnershipCreateAttempt;
export function shouldShowAdminOwnershipPanel(input: {
  dataLoaded: boolean;
  notNominee: boolean;
  requestFailed: boolean;
  hasOwnOffer: boolean;
}): boolean;
export function parseExactTimestamp(value: string): {
  epochMilliseconds: number;
  subMillisecondMicroseconds: number;
  fraction: string;
} | null;
export function isBeforeExpiry(expiresAt: string, now: number): boolean;
