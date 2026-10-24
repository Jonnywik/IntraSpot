export const PERSONA_ACCESS_CHANGED_EVENT = 'intraspot:persona-access-changed';

export function notifyPersonaAccessChanged(userId: string) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(PERSONA_ACCESS_CHANGED_EVENT, { detail: { userId } }));
}
