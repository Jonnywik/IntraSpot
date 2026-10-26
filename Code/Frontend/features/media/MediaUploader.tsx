"use client";

import { useId, useRef, useState, type ChangeEvent } from "react";
import { ApiError, api } from "@/lib/api";
import { useT, type Translate } from "@/lib/i18n";
import type { MediaMutationOut } from "./types";
import styles from "./MediaUploader.module.css";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export type MediaUploaderProps = {
  endpoint: string;
  token: string | null;
  ifMatch?: string;
  disabled?: boolean;
  currentUrl?: string | null;
  onChanged: (result: MediaMutationOut) => void;
  onBusyChange?: (busy: boolean) => void;
  onConflict?: () => void;
};

function apiErrorMessage(error: unknown, action: "upload" | "remove", hasDraftVersion: boolean, t: Translate): string {
  if (error instanceof ApiError) {
    if (action === "upload" && error.code === "media_quota_exceeded") {
      return t("Image storage is full. Ask an administrator to review stored images and free space. Your current image and selected file were not changed.");
    }
    if (error.code === "media_storage_unavailable") {
      return t("Image storage is temporarily unavailable. Your current image and selected file were not changed; try again later.");
    }
    if (action === "upload" && error.status === 413) return t("The image is larger than 5 MiB.");
    if (action === "upload" && [400, 415, 422].includes(error.status)) {
      return t("The image must be a valid static JPEG, PNG, or WebP image under 5 MiB and 12 megapixels.");
    }
    if (error.status === 409 || error.status === 428) {
      return t(hasDraftVersion ? "The saved draft changed. Reload it before changing the banner." : "This image changed. Reload and try again.");
    }
    if (error.status === 401 || error.status === 403) return t("You no longer have permission to change this image.");
  }
  return t(action === "upload" ? "The image could not be uploaded. Please try again." : "The image could not be removed. Please try again.");
}

export function MediaUploader({ endpoint, token, ifMatch, disabled = false, currentUrl, onChanged, onBusyChange, onConflict }: MediaUploaderProps) {
  const t = useT();
  const inputId = useId();
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const inputRef = useRef<HTMLInputElement>(null);
  const requestInFlightRef = useRef(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<"upload" | "remove" | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [statusKey, setStatusKey] = useState<string | null>(null);
  const isDisabled = disabled || busy !== null || !token;

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0] ?? null;
    setSelectedFile(null);
    setErrorKey(null);
    setStatusKey(null);
    if (!file) return;
    if (!IMAGE_TYPES.has(file.type)) {
      setErrorKey("Choose a JPEG, PNG, or WebP image.");
      event.currentTarget.value = "";
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setErrorKey("The image is larger than 5 MiB.");
      event.currentTarget.value = "";
      return;
    }
    setSelectedFile(file);
    setStatusKey("Image selected and ready to upload.");
  }

  async function uploadImage() {
    if (isDisabled || !selectedFile || requestInFlightRef.current) return;
    requestInFlightRef.current = true;
    setBusy("upload");
    setErrorKey(null);
    setStatusKey("Uploading image…");
    try {
      onBusyChange?.(true);
      const result = await api<MediaMutationOut>(endpoint, {
        token,
        method: "POST",
        body: selectedFile,
        ...(ifMatch === undefined ? {} : { ifMatch }),
      });
      onChanged(result);
      setSelectedFile(null);
      if (inputRef.current) inputRef.current.value = "";
      setStatusKey("Image uploaded.");
    } catch (error) {
      if (error instanceof ApiError && (error.status === 409 || error.status === 428)) onConflict?.();
      setStatusKey(null);
      setErrorKey(apiErrorMessage(error, "upload", ifMatch !== undefined, t));
    } finally {
      requestInFlightRef.current = false;
      setBusy(null);
      onBusyChange?.(false);
    }
  }

  async function removeImage() {
    if (isDisabled || !currentUrl || requestInFlightRef.current) return;
    requestInFlightRef.current = true;
    setBusy("remove");
    setErrorKey(null);
    setStatusKey("Removing image…");
    try {
      onBusyChange?.(true);
      const result = await api<MediaMutationOut>(endpoint, {
        token,
        method: "DELETE",
        ...(ifMatch === undefined ? {} : { ifMatch }),
      });
      onChanged(result);
      setSelectedFile(null);
      if (inputRef.current) inputRef.current.value = "";
      setStatusKey("Image removed.");
    } catch (error) {
      if (error instanceof ApiError && (error.status === 409 || error.status === 428)) onConflict?.();
      setStatusKey(null);
      setErrorKey(apiErrorMessage(error, "remove", ifMatch !== undefined, t));
    } finally {
      requestInFlightRef.current = false;
      setBusy(null);
      onBusyChange?.(false);
    }
  }

  return (
    <div className={styles.root}>
      <label className={styles.label} htmlFor={inputId}>{t("Choose image file")}</label>
      <input
        ref={inputRef}
        id={inputId}
        className={styles.input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        disabled={isDisabled}
        aria-describedby={`${hintId}${errorKey ? ` ${errorId}` : ""}`}
        aria-invalid={Boolean(errorKey)}
        onChange={selectFile}
      />
      <p className={styles.hint} id={hintId}>
        {t("JPEG, PNG, or WebP. Maximum file size 5 MiB. Images must be static and no larger than 12 megapixels.")}
      </p>
      <div className={styles.actions}>
        <button className="button button-secondary" type="button" disabled={isDisabled || !selectedFile} onClick={() => void uploadImage()}>
          {busy === "upload" ? t("Uploading image…") : currentUrl ? t("Replace image") : t("Upload image")}
        </button>
        {currentUrl && (
          <button className="button button-danger" type="button" disabled={isDisabled} onClick={() => void removeImage()}>
            {busy === "remove" ? t("Removing image…") : t("Remove image")}
          </button>
        )}
      </div>
      {statusKey && <p className={styles.status} role="status" aria-live="polite">{t(statusKey)}</p>}
      {errorKey && <p className={styles.error} id={errorId} role="alert">{t(errorKey)}</p>}
    </div>
  );
}
