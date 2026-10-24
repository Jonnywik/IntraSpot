'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { notifyPersonaAccessChanged } from './access-events';
import type { OutgoingBlock } from './types';
import styles from './personas.module.css';

type BlockListProps = { token: string; actorId: string };

export function BlockList(props: BlockListProps) {
  return <BlockListSession key={`${props.actorId}:${props.token}`} {...props} />;
}

function BlockListSession({ token, actorId }: BlockListProps) {
  const t = useT();
  const [blocks, setBlocks] = useState<OutgoingBlock[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [unblockingId, setUnblockingId] = useState<string | null>(null);
  const [unblockError, setUnblockError] = useState(false);
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const loadRequest = useRef<AbortController | null>(null);
  const unblockRequest = useRef<AbortController | null>(null);
  const contextKey = `${actorId}:${token}`;

  useEffect(() => {
    const controller = new AbortController();
    loadRequest.current?.abort();
    loadRequest.current = controller;
    void api<OutgoingBlock[]>('/me/blocks', { token, signal: controller.signal })
      .then(result => {
        if (!controller.signal.aborted) setBlocks(result);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
        if (loadRequest.current === controller) loadRequest.current = null;
      });
    return () => {
      controller.abort();
      unblockRequest.current?.abort();
    };
  }, [contextKey, revision, token]);

  useEffect(() => () => {
    loadRequest.current?.abort();
    unblockRequest.current?.abort();
  }, []);

  async function unblock(userId: string) {
    if (!token || unblockingId) return;
    const controller = new AbortController();
    unblockRequest.current?.abort();
    unblockRequest.current = controller;
    setUnblockingId(userId);
    setUnblockError(false);
    setNotice('');
    try {
      await api<null>(`/me/blocks/${encodeURIComponent(userId)}`, {
        token,
        method: 'DELETE',
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setBlocks(current => current?.filter(block => block.user_id !== userId) ?? []);
      setNotice(t('Member unblocked.'));
      notifyPersonaAccessChanged(userId);
    } catch {
      if (!controller.signal.aborted) setUnblockError(true);
    } finally {
      if (!controller.signal.aborted) setUnblockingId(null);
      if (unblockRequest.current === controller) unblockRequest.current = null;
    }
  }

  return (
    <section className={`panel stack ${styles.blockList}`} aria-labelledby="blocked-members-heading">
      <h2 id="blocked-members-heading">{t('Blocked members')}</h2>
      <p>{t('Only the account IDs you blocked appear here. Nicknames are not shown.')}</p>
      {loading ? <p role="status">{t('Loading blocked members')}</p> : null}
      {loadError ? (
        <div role="alert">
          <p>{t('Your block list could not be loaded.')}</p>
          <button className="button button-secondary" type="button" onClick={() => {
            setBlocks(null);
            setLoading(true);
            setLoadError(false);
            setUnblockError(false);
            setNotice('');
            setRevision(value => value + 1);
          }}>
            {t('Retry loading blocks')}
          </button>
        </div>
      ) : null}
      {!loading && !loadError && blocks?.length === 0 ? <p>{t('No members are blocked.')}</p> : null}
      {!loading && !loadError && blocks?.length ? (
        <ul className="stack">
          {blocks.map(block => (
            <li className={styles.blockRow} key={block.user_id}>
              <span className={styles.blockId}>
                <span className={styles.visuallyHidden}>{t('Blocked member ID')}: </span>{block.user_id}
              </span>
              <button
                className="button button-secondary"
                type="button"
                onClick={() => void unblock(block.user_id)}
                disabled={unblockingId !== null}
              >
                {unblockingId === block.user_id ? t('Unblocking…') : t('Unblock')}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {unblockError ? <p className={styles.error} role="alert">{t('Could not unblock this member. Please retry.')}</p> : null}
      {notice ? <p className={styles.status} role="status">{notice}</p> : null}
    </section>
  );
}
