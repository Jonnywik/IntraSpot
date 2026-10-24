export const DESKTOP_SAFETY_QUERY = '(min-width: 768px)';

export function captureSafetyCommand(contextKey, path, body) {
  const frozenBody = Object.freeze({...body});
  return Object.freeze({contextKey, path, body: frozenBody});
}

export function matchesSafetyCommand(command, contextKey) {
  return Boolean(command && command.contextKey === contextKey);
}

export function isUncertainSafetyFailure(status) {
  return status === null || status === 0 || status === 408 || status === 429 || status >= 500;
}

export function eventReportDecisionOutcome(result, reportId, action, version) {
  const statuses = {dismiss: 'dismissed', hide: 'hidden', remove: 'removed', uphold: 'upheld'};
  if (!result || typeof result !== 'object' || Array.isArray(result) ||
    typeof action !== 'string' || !Object.hasOwn(statuses, action) ||
    !Number.isSafeInteger(version) || version < 1 || !Number.isSafeInteger(result.version) ||
    result.id !== reportId || result.version !== version + 1) return 'uncertain';
  if (result.status === 'expired') return 'expired';
  return result.status === statuses[action] ? 'applied' : 'uncertain';
}

export function parseBoundedEventEvidence(evidence) {
  if (typeof evidence !== 'string' || evidence.length > 4096) return null;

  try {
    const parsed = JSON.parse(evidence);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null;
    const limits = {title: 200, summary: 400, description: 2200, venue_name: 200, venue_address: 500};
    const snapshot = {};
    for (const [field, limit] of Object.entries(limits)) {
      if (typeof parsed[field] === 'string') snapshot[field] = parsed[field].slice(0, limit);
    }
    return Object.keys(snapshot).length ? snapshot : null;
  } catch {
    return null;
  }
}

export function eventReportActions(report, now = Date.now()) {
  const deadline = Date.parse(report?.deadline ?? '');
  if (!['open', 'escalated'].includes(report?.status) || !Number.isFinite(deadline) || deadline <= now ||
    typeof report?.evidence !== 'string') return [];
  if (report.stage === 'organization') return ['dismiss', 'hide'];
  if (report.stage === 'platform') return ['dismiss', 'hide', 'remove', 'uphold'];
  return [];
}
