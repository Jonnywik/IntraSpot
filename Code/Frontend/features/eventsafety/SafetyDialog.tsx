'use client';

import {useEffect, useId, useRef, type ReactNode} from 'react';
import styles from './eventsafety.module.css';
import type {Translate} from './types-ui';

export function SafetyDialog({
  open,
  title,
  description,
  children,
  confirmLabel,
  confirmDisabled = false,
  onCancel,
  onConfirm,
  returnFocusRef,
  t,
}: {
  open: boolean;
  title: string;
  description: string;
  children?: ReactNode;
  confirmLabel: string;
  confirmDisabled?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  returnFocusRef: {current: HTMLElement | null};
  t: Translate;
}) {
  const id = useId();
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  const wasOpenRef = useRef(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const returnTarget = returnFocusRef.current;
    if (open && !dialog.open) {
      dialog.showModal();
      wasOpenRef.current = true;
      cancelRef.current?.focus();
    } else if (!open && dialog.open) {
      dialog.close();
    }
    if (!open && wasOpenRef.current) {
      wasOpenRef.current = false;
      window.requestAnimationFrame(() => {
        if (returnTarget?.isConnected) returnTarget.focus();
      });
    }
    return () => {
      if (dialog.open) dialog.close();
      if (wasOpenRef.current) {
        wasOpenRef.current = false;
        window.requestAnimationFrame(() => {
          if (returnTarget?.isConnected) returnTarget.focus();
        });
      }
    };
  }, [open, returnFocusRef]);

  return (
    <dialog
      ref={dialogRef}
      className={styles.dialog}
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-description`}
      onCancel={event => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form className={styles.dialogForm} onSubmit={event => { event.preventDefault(); onConfirm(); }}>
        <h3 id={`${id}-title`}>{title}</h3>
        <p id={`${id}-description`}>{description}</p>
        {children}
        <div className={styles.actions}>
          <button ref={cancelRef} className="button button-secondary" type="button" onClick={onCancel}>
            {t('Cancel')}
          </button>
          <button className="button button-danger" type="submit" disabled={confirmDisabled}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
