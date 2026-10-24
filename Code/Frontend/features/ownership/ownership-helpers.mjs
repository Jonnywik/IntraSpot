export function canLoadOwnershipData({isDesktop, role, actorEligible, token}) {
  return isDesktop && Boolean(token) && actorEligible && (role === 'owner' || role === 'admin');
}

export function captureDecision(offer, action) {
  return {transferId: offer.id, version: offer.version, action};
}

export function isDecisionCurrent(reviewed, offer) {
  return Boolean(offer && offer.id === reviewed.transferId && offer.version === reviewed.version && offer.status === 'pending');
}

export function decisionPayload(reviewed) {
  return {action: reviewed.action, version: reviewed.version};
}

export function matchesOfferAttempt(current, context, nomineeId) {
  return Boolean(current && current.context === context && current.nomineeId === nomineeId);
}

export function getOrCreateOfferAttempt(current, context, nomineeId, createClientKey) {
  if (matchesOfferAttempt(current, context, nomineeId)) return current;
  const clientKey = createClientKey();
  return {
    context,
    nomineeId,
    clientKey,
    payload: {nominee_id: nomineeId, client_key: clientKey},
  };
}

export function shouldShowAdminOwnershipPanel({dataLoaded, notNominee, requestFailed, hasOwnOffer}) {
  return dataLoaded && !notNominee && (requestFailed || hasOwnOffer);
}

export function parseExactTimestamp(value) {
  if (typeof value !== 'string') return null;
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/i.exec(value);
  if (!match) return null;
  const fraction = match[2] ?? '';
  const milliseconds = fraction.padEnd(3, '0').slice(0, 3);
  const epochMilliseconds = Date.parse(`${match[1]}.${milliseconds}${match[3]}`);
  if (!Number.isFinite(epochMilliseconds)) return null;
  const subMillisecondMicroseconds = Number(fraction.padEnd(6, '0').slice(3, 6));
  return {epochMilliseconds, subMillisecondMicroseconds, fraction};
}

export function isBeforeExpiry(expiresAt, now) {
  const expiry = parseExactTimestamp(expiresAt);
  if (!expiry || !Number.isFinite(now)) return false;
  return now * 1_000 < expiry.epochMilliseconds * 1_000 + expiry.subMillisecondMicroseconds;
}
