'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { notifyPersonaAccessChanged, PERSONA_ACCESS_CHANGED_EVENT } from './access-events';
import type { PersonaProjection } from './types';
import styles from './personas.module.css';

type PersonaState = 'idle' | 'loading' | 'loaded' | 'unavailable';

type PersonaActionProps = {
  eventId: string;
  targetUserId: string;
  actorId: string;
  token: string | null;
};

export function PersonaActions(props: PersonaActionProps) {
  return <PersonaActionsSession key={`${props.eventId}:${props.targetUserId}:${props.actorId}:${props.token ?? ''}`} {...props} />;
}

function PersonaActionsSession({ eventId, targetUserId, actorId, token }: PersonaActionProps) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<PersonaState>('idle');
  const [persona, setPersona] = useState<PersonaProjection | null>(null);
  const [confirmingBlock, setConfirmingBlock] = useState(false);
  const [blocking, setBlocking] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [blockError, setBlockError] = useState(false);
  const personaRequest = useRef<AbortController | null>(null);
  const blockRequest = useRef<AbortController | null>(null);
  const confirmation = useRef<HTMLDialogElement>(null);
  const profileToggle = useRef<HTMLButtonElement>(null);
  const blockTrigger = useRef<HTMLButtonElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const focusReturn = useRef<HTMLButtonElement | null>(null);
  const id = useId();
  const contextKey = `${eventId}:${targetUserId}:${actorId}:${token ?? ''}`;

  useEffect(() => {
    let hasLoaded = false;
    const loadPersona = async (clearFirst: boolean) => {
      if (!token) return;
      if (clearFirst || !hasLoaded) {
        setPersona(null);
        setState('loading');
      }
      const controller = new AbortController();
      personaRequest.current?.abort();
      personaRequest.current = controller;
      try {
        const result = await api<PersonaProjection>(
          `/events/${encodeURIComponent(eventId)}/personas/${encodeURIComponent(targetUserId)}`,
          { token, signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        hasLoaded = true;
        setPersona(result);
        setState('loaded');
      } catch {
        if (controller.signal.aborted) return;
        hasLoaded = true;
        setPersona(null);
        setState('unavailable');
      } finally {
        if (personaRequest.current === controller) personaRequest.current = null;
      }
    };

    if (!open || !token) {
      return;
    }

    void loadPersona(true);
    const poll = window.setInterval(() => {
      if (document.visibilityState === 'visible') void loadPersona(false);
    }, 30_000);
    const onFocus = () => void loadPersona(false);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void loadPersona(false);
    };
    const onAccessChange = (event: Event) => {
      const changedUserId = (event as CustomEvent<{ userId?: string }>).detail?.userId;
      if (!changedUserId || changedUserId === targetUserId) void loadPersona(true);
    };
    window.addEventListener('focus', onFocus);
    window.addEventListener(PERSONA_ACCESS_CHANGED_EVENT, onAccessChange);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.clearInterval(poll);
      window.removeEventListener('focus', onFocus);
      window.removeEventListener(PERSONA_ACCESS_CHANGED_EVENT, onAccessChange);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      personaRequest.current?.abort();
      blockRequest.current?.abort();
    };
  }, [contextKey, eventId, open, targetUserId, token]);

  useEffect(() => {
    const dialog = confirmation.current;
    if (!dialog) return;
    if (confirmingBlock && !dialog.open) {
      dialog.showModal();
      cancelButton.current?.focus();
    }
    if (!confirmingBlock && dialog.open) {
      dialog.close();
      const target = focusReturn.current;
      focusReturn.current = null;
      if (target?.isConnected) target.focus();
      else if (profileToggle.current?.isConnected) profileToggle.current.focus();
    }
  }, [confirmingBlock]);

  useEffect(() => () => {
    personaRequest.current?.abort();
    blockRequest.current?.abort();
  }, []);

  if (!token || actorId === targetUserId) return null;

  function closePersona() {
    personaRequest.current?.abort();
    setOpen(false);
    setPersona(null);
    setState('idle');
    setConfirmingBlock(false);
    setBlockError(false);
  }

  async function blockMember() {
    if (!token || blocking) return;
    const controller = new AbortController();
    blockRequest.current?.abort();
    blockRequest.current = controller;
    personaRequest.current?.abort();
    setBlocking(true);
    setBlockError(false);
    setPersona(null);
    setState('unavailable');
    try {
      await api(`/events/${encodeURIComponent(eventId)}/blocks/${encodeURIComponent(targetUserId)}`, {
        token,
        method: 'PUT',
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setBlocked(true);
      setConfirmingBlock(false);
      notifyPersonaAccessChanged(targetUserId);
    } catch {
      if (!controller.signal.aborted) setBlockError(true);
    } finally {
      if (!controller.signal.aborted) setBlocking(false);
      if (blockRequest.current === controller) blockRequest.current = null;
    }
  }

  const blockTitleId = `${id}-block-title`;
  const blockHelpId = `${id}-block-help`;

  return (
    <div className={styles.section}>
      <button
        className="button button-secondary"
        type="button"
        ref={profileToggle}
        aria-expanded={open}
        aria-controls={`${id}-persona`}
        onClick={() => {
          if (open) closePersona();
          else {
            setBlocked(false);
            setBlockError(false);
            setOpen(true);
          }
        }}
      >
        {open ? t('Close text profile') : t('View text profile')}
      </button>

      {open ? (
        <section className={`panel ${styles.personaPanel}`} id={`${id}-persona`} aria-labelledby={`${id}-persona-title`}>
          <h3 id={`${id}-persona-title`}>{t('Text profile')}</h3>
          {state === 'loading' ? <p role="status">{t('Loading text profile…')}</p> : null}
          {state === 'unavailable' ? <p role="status">{t('This text profile is unavailable.')}</p> : null}
          {state === 'loaded' && persona ? (
            <>
              <dl className={styles.personaFields}>
                <dt>{t('Nickname')}</dt><dd>{persona.nickname || t('Not shared')}</dd>
                <dt>{t('Age bracket')}</dt><dd>{persona.age_bracket || t('Not shared')}</dd>
                <dt>{t('Interest or vibe tags')}</dt><dd>{persona.tags.length ? persona.tags.join(', ') : t('No tags shared')}</dd>
                <dt>{t('Pronouns')}</dt><dd>{persona.pronouns || t('Not shared')}</dd>
                <dt>{t('Icebreaker')}</dt><dd>{persona.icebreaker || t('Not shared')}</dd>
              </dl>
            </>
          ) : null}
          {blocked ? <p role="status">{t('Member blocked.')}</p> : (
            <div className={styles.actions}>
              <button
                className="button button-secondary"
                type="button"
                ref={blockTrigger}
                aria-haspopup="dialog"
                onClick={event => {
                  focusReturn.current = event.currentTarget;
                  setConfirmingBlock(true);
                }}
              >
                {t('Block member')}
              </button>
            </div>
          )}
          {blockError ? <p className={styles.error} role="alert">{t('The member could not be blocked. Please try again.')}</p> : null}
        </section>
      ) : null}

      <dialog
        ref={confirmation}
        className={styles.dialog}
        aria-labelledby={blockTitleId}
        aria-describedby={blockHelpId}
        onCancel={event => {
          event.preventDefault();
          setConfirmingBlock(false);
        }}
      >
        <div className="stack">
          <h2 id={blockTitleId}>{t('Block this member?')}</h2>
          <p id={blockHelpId}>{t("Blocking hides each other's text personas. It does not remove either of you from group chats, delete messages, or cancel either registration.")}</p>
          <div className={styles.actions}>
            <button className="button" type="button" onClick={() => void blockMember()} disabled={blocking}>
              {blocking ? t('Blocking…') : t('Block member')}
            </button>
            <button ref={cancelButton} className="button button-secondary" type="button" autoFocus onClick={() => setConfirmingBlock(false)} disabled={blocking}>
              {t('Cancel')}
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
}
