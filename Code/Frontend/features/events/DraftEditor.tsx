"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { EventArtwork } from "@/app/event-artwork";
import { FeaturedBadge } from "@/features/featured/FeaturedBadge";
import { Feedback } from "@/components/feedback";
import { MediaUploader } from "@/features/media/MediaUploader";
import type { MediaMutationOut } from "@/features/media/types";
import { ApiError, api } from "@/lib/api";
import { fromUtcToManila, formatDate, formatTime, toUtcFromManila } from "@/lib/date";
import { useT } from "@/lib/i18n";
import { usePreferences } from "@/lib/preferences";
import { useApiResource } from "@/lib/use-api-resource";
import { useSession } from "@/lib/session";
import type { EventDraftInput, PrivateEvent, PublicEvent, Workspace } from "@/lib/types";
import styles from "./draft-editor.module.css";

type BannerKey = NonNullable<EventDraftInput["banner_key"]>;
type EventType = EventDraftInput["event_type"];
type RegistrationMode = EventDraftInput["registration_mode"];
type VersionedPrivateEvent = PrivateEvent;
type EventDraftRequest = EventDraftInput & { tags: string[]; coarse_area: string | null };
type SaveStatus = "saved" | "unsaved" | "saving" | "error" | "conflict";
type DraftForm = {
  title: string;
  summary: string;
  description: string;
  startsAt: string;
  endsAt: string;
  venueName: string;
  venueAddress: string;
  capacity: string;
  bannerKey: BannerKey | "";
  eventType: EventType;
  costLabel: string;
  registrationMode: RegistrationMode;
  reviewWindowMinutes: string;
  tagsText: string;
  coarseArea: string;
};
type NavigationApi = {
  addEventListener(type: "navigate", listener: EventListener): void;
  removeEventListener(type: "navigate", listener: EventListener): void;
};

const SUMMARY_MAX_LENGTH = 200;
const MAX_CAPACITY = 2_147_483_647;
const MAX_EVENT_TAGS = 16;
const MAX_EVENT_TAG_LENGTH = 64;
const MAX_COARSE_AREA_LENGTH = 80;
const EMPTY_FORM: DraftForm = {
  title: "",
  summary: "",
  description: "",
  startsAt: "",
  endsAt: "",
  venueName: "",
  venueAddress: "",
  capacity: "",
  bannerKey: "",
  eventType: "scheduled",
  costLabel: "Free",
  registrationMode: "instant",
  reviewWindowMinutes: "",
  tagsText: "",
  coarseArea: "",
};

const EMPTY_DRAFT_INPUT: EventDraftRequest = {
  summary: "",
  cost_label: "Free",
  registration_mode: "instant",
  review_window_minutes: null,
  event_type: "scheduled",
  tags: [],
  coarse_area: null,
};

function tagsFromText(value: string): string[] {
  return value.split(",").map((tag) => tag.trim()).filter(Boolean);
}

function eventTags(draft: PrivateEvent): string[] {
  if (!("tags" in draft) || !Array.isArray(draft.tags)) return [];
  const tags: readonly unknown[] = draft.tags;
  return tags.filter((tag): tag is string => typeof tag === "string");
}

function eventCoarseArea(draft: PrivateEvent): string {
  return "coarse_area" in draft && typeof draft.coarse_area === "string" ? draft.coarse_area : "";
}

function normalizedLabelLength(value: string): number {
  return Array.from(value.normalize("NFKC").replace(/\s+/gu, " ").trim()).length;
}

function metadataIssues(form: DraftForm): string[] {
  const tags = tagsFromText(form.tagsText);
  const issues: string[] = [];
  if (tags.length > MAX_EVENT_TAGS || tags.some((tag) => normalizedLabelLength(tag) > MAX_EVENT_TAG_LENGTH)) {
    issues.push("Use at most 16 tags, each 1–64 characters.");
  }
  if (normalizedLabelLength(form.coarseArea) > MAX_COARSE_AREA_LENGTH) {
    issues.push("Keep the broad area to 80 characters or fewer.");
  }
  return issues;
}

function formFromDraft(draft: PrivateEvent): DraftForm {
  return {
    title: draft.title ?? "",
    summary: draft.summary,
    description: draft.description ?? "",
    startsAt: fromUtcToManila(draft.starts_at),
    endsAt: fromUtcToManila(draft.ends_at),
    venueName: draft.venue_name ?? "",
    venueAddress: draft.venue_address ?? "",
    capacity: draft.capacity === null ? "" : String(draft.capacity),
    bannerKey: draft.banner_key ?? "",
    eventType: draft.event_type === "flash" ? "flash" : "scheduled",
    costLabel: draft.cost_label,
    registrationMode: draft.registration_mode ?? "instant",
    reviewWindowMinutes: draft.review_window_minutes == null ? "" : String(draft.review_window_minutes),
    tagsText: eventTags(draft).join(", "),
    coarseArea: eventCoarseArea(draft),
  };
}

function inputFromForm(form: DraftForm): EventDraftRequest {
  return {
    title: form.title.trim() || null,
    summary: form.summary,
    description: form.description.trim() ? form.description : null,
    starts_at: form.startsAt ? toUtcFromManila(form.startsAt) : null,
    ends_at: form.endsAt ? toUtcFromManila(form.endsAt) : null,
    venue_name: form.venueName.trim() || null,
    venue_address: form.venueAddress.trim() || null,
    capacity: form.capacity.trim() ? Number(form.capacity) : null,
    banner_key: form.bannerKey || null,
    event_type: form.eventType,
    cost_label: form.costLabel,
    registration_mode: form.registrationMode,
    review_window_minutes:
      form.registrationMode === "approval" && form.reviewWindowMinutes.trim()
        ? Number(form.reviewWindowMinutes)
        : null,
    tags: tagsFromText(form.tagsText),
    coarse_area: form.coarseArea.trim() || null,
  };
}

function publishIssues(form: DraftForm, now = Date.now()): string[] {
  const issues: string[] = [];
  if (!form.title.trim()) issues.push("Add an event title.");
  if (!form.description.trim()) issues.push("Add an event description.");
  if (!form.venueName.trim()) issues.push("Add a venue name.");
  if (!form.venueAddress.trim()) issues.push("Add a venue address.");
  if (!form.bannerKey) issues.push("Choose an artwork theme.");
  if (!form.costLabel.trim()) issues.push("Add a cost label.");
  if (form.summary.length > SUMMARY_MAX_LENGTH) issues.push("Keep the short summary to 200 characters or fewer.");

  let startsAt = Number.NaN;
  let endsAt = Number.NaN;
  try {
    if (form.startsAt) startsAt = new Date(toUtcFromManila(form.startsAt)).getTime();
  } catch {
    startsAt = Number.NaN;
  }
  try {
    if (form.endsAt) endsAt = new Date(toUtcFromManila(form.endsAt)).getTime();
  } catch {
    endsAt = Number.NaN;
  }
  if (!Number.isFinite(startsAt) || startsAt <= now) issues.push("Set a start time in the future.");
  if (form.eventType === "flash" && Number.isFinite(startsAt) && startsAt > now + 24 * 60 * 60 * 1000) {
    issues.push("Flash events must start within 24 hours of publication.");
  }
  if (!Number.isFinite(endsAt)) issues.push("Set an end time after the start.");
  else if (Number.isFinite(startsAt) && endsAt <= startsAt) issues.push("Set an end time after the start.");

  const capacity = Number(form.capacity);
  if (!form.capacity.trim() || !Number.isInteger(capacity) || capacity <= 0 || capacity > MAX_CAPACITY) {
    issues.push("Enter a positive whole-number capacity.");
  }
  if (form.registrationMode === "approval") {
    const reviewWindow = Number(form.reviewWindowMinutes);
    if (!form.reviewWindowMinutes.trim() || !Number.isInteger(reviewWindow) || reviewWindow < 15 || reviewWindow > 2880) {
      issues.push("Enter a review window from 15 to 2,880 minutes.");
    }
  }
  return issues;
}

function isDraftConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409 && error.code === "draft_conflict";
}

function dateTimeLabel(value: string, language: "en" | "fil"): string | null {
  if (!value) return null;
  try {
    const utc = toUtcFromManila(value);
    return `${formatDate(utc, language)} · ${formatTime(utc, language)}`;
  } catch {
    return null;
  }
}

export function DraftEditor() {
  const searchParams = useSearchParams();
  const { token: sessionToken } = useSession();
  const requestedOrgId = searchParams.get("orgId") ?? "";
  const eventId = searchParams.get("eventId") ?? "";

  return (
    <DraftEditorContent
      key={`${eventId}:${sessionToken ?? "signed-out"}`}
      eventId={eventId}
      requestedOrgId={requestedOrgId}
    />
  );
}

function DraftEditorContent({
  eventId,
  requestedOrgId,
}: {
  eventId: string;
  requestedOrgId: string;
}) {
  const router = useRouter();
  const t = useT();
  const { preferences: { language } } = usePreferences();
  const { token, authLoading } = useSession();
  const draftResource = useApiResource<VersionedPrivateEvent>(
    eventId && token ? "/events/" + encodeURIComponent(eventId) + "/draft" : null,
    token,
  );
  const [draft, setDraft] = useState<VersionedPrivateEvent | null>(null);
  const [formState, setFormState] = useState<DraftForm | null>(null);
  const [editRevision, setEditRevision] = useState(0);
  const [savedRevision, setSavedRevision] = useState(0);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [mediaBusy, setMediaBusy] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [messageKey, setMessageKey] = useState<string | null>(null);
  const currentDraft = draft ?? draftResource.data;
  const form = formState ?? (currentDraft ? formFromDraft(currentDraft) : EMPTY_FORM);
  const formRef = useRef<DraftForm | null>(null);
  const draftRef = useRef<VersionedPrivateEvent | null>(null);
  const editRevisionRef = useRef(editRevision);
  const savedRevisionRef = useRef(savedRevision);
  const activeSaveRevisionRef = useRef(-1);
  const saveInFlightRef = useRef(false);
  const queuedSaveRef = useRef(false);
  const accountSwitchAcceptedRef = useRef(false);
  const mutationInFlightRef = useRef(false);
  const mediaBusyRef = useRef(false);
  const mediaStartRevisionRef = useRef<number | null>(null);

  const orgId = currentDraft?.org_id || requestedOrgId;
  const workspaceResource = useApiResource<Workspace>(
    orgId && token ? "/organizations/" + encodeURIComponent(orgId) + "/workspace" : null,
    token,
  );
  const workspace = workspaceResource.data;
  const isManager = workspace?.role === "owner" || workspace?.role === "admin";
  const isRejected = workspace?.accreditation_status === "rejected";
  const canCreate = Boolean(isManager && workspace && !isRejected);
  const canEdit = Boolean(
    currentDraft &&
    isManager &&
    !isRejected &&
    currentDraft.status === "draft",
  );
  const isDirty = editRevision !== savedRevision;
  const hasUnsavedChanges = isDirty || saving || saveStatus === "conflict";
  const hasDraftVersion = Boolean(currentDraft?.draft_version);
  const metadataValidation = metadataIssues(form);
  const issues = [...publishIssues(form), ...metadataValidation];
  const mediaMutationDisabled = Boolean(
    !canEdit ||
    !hasDraftVersion ||
    mediaBusy ||
    isDirty ||
    saving ||
    publishing ||
    reloading ||
    saveStatus !== "saved",
  );

  useEffect(() => {
    formRef.current = form;
    draftRef.current = currentDraft;
    editRevisionRef.current = editRevision;
    savedRevisionRef.current = savedRevision;
  }, [form, currentDraft, editRevision, savedRevision]);

  function updateForm(nextForm: DraftForm) {
    if (publishing || mediaBusyRef.current) return;
    formRef.current = nextForm;
    setFormState(nextForm);
    const nextRevision = editRevisionRef.current + 1;
    editRevisionRef.current = nextRevision;
    setEditRevision(nextRevision);
    setMessageKey(null);
    if (saveStatus !== "conflict") {
      setErrorKey(null);
      if (!saveInFlightRef.current) setSaveStatus("unsaved");
    }
  }

  function updateField<K extends keyof DraftForm>(field: K, value: DraftForm[K]) {
    updateForm({ ...(formRef.current ?? form), [field]: value });
  }

  function updateEventType(eventType: EventType) {
    const nextForm = { ...(formRef.current ?? form), eventType };
    if (eventType === "flash") {
      nextForm.registrationMode = "instant";
      nextForm.reviewWindowMinutes = "";
    }
    updateForm(nextForm);
  }

  async function createDraft() {
    if (!token || !orgId || !workspace || !canCreate || mutationInFlightRef.current) return;
    mutationInFlightRef.current = true;
    setCreating(true);
    setErrorKey(null);
    setMessageKey(null);
    try {
      const created = await api<VersionedPrivateEvent>(
        "/organizations/" + encodeURIComponent(orgId) + "/events",
        { token, method: "POST", body: EMPTY_DRAFT_INPUT },
      );
      setDraft(created);
      draftRef.current = created;
      const createdForm = formFromDraft(created);
      formRef.current = createdForm;
      setFormState(createdForm);
      editRevisionRef.current = 0;
      savedRevisionRef.current = 0;
      setEditRevision(0);
      setSavedRevision(0);
      setSaveStatus(created.draft_version ? "saved" : "error");
      setErrorKey(created.draft_version ? null : "This draft is missing its save version. Reload it before making changes.");
      router.replace("/draft?" + new URLSearchParams({ orgId, eventId: created.id }).toString());
    } catch {
      setErrorKey("The draft could not be created. Try again.");
    } finally {
      mutationInFlightRef.current = false;
      setCreating(false);
    }
  }

  const saveLatestDraft = useCallback(async () => {
    if (accountSwitchAcceptedRef.current || mediaBusyRef.current) return;
    if (saveInFlightRef.current) {
      if (editRevisionRef.current > activeSaveRevisionRef.current) queuedSaveRef.current = true;
      return;
    }
    const initialDraft = draftRef.current ?? currentDraft;
    if (!token || !initialDraft || !canEdit || !isDirty) return;
    if (!initialDraft.draft_version) {
      setSaveStatus("error");
      setErrorKey("This draft is missing its save version. Reload it before making changes.");
      return;
    }

    saveInFlightRef.current = true;
    setSaving(true);
    setErrorKey(null);
    setMessageKey(null);
    let snapshot: DraftForm = formRef.current ?? form;
    let snapshotRevision = editRevisionRef.current;
    try {
      while (true) {
        if (accountSwitchAcceptedRef.current) {
          queuedSaveRef.current = false;
          break;
        }
        const metadataError = metadataIssues(snapshot)[0];
        if (metadataError) {
          setSaveStatus("error");
          setErrorKey(metadataError);
          queuedSaveRef.current = false;
          break;
        }
        const versionedDraft = draftRef.current;
        if (!versionedDraft?.draft_version) {
          setSaveStatus("error");
          setErrorKey("This draft is missing its save version. Reload it before making changes.");
          queuedSaveRef.current = false;
          break;
        }
        activeSaveRevisionRef.current = snapshotRevision;
        setSaveStatus("saving");
        try {
          const updated = await api<VersionedPrivateEvent>(
            "/events/" + encodeURIComponent(versionedDraft.id) + "/draft",
            {
              method: "PATCH",
              body: inputFromForm(snapshot),
              token,
              ifMatch: versionedDraft.draft_version,
            },
          );
          if (accountSwitchAcceptedRef.current) {
            queuedSaveRef.current = false;
            break;
          }
          draftRef.current = updated;
          setDraft(updated);
          savedRevisionRef.current = snapshotRevision;
          setSavedRevision(snapshotRevision);
          setErrorKey(null);
          if (editRevisionRef.current === snapshotRevision) {
            setSaveStatus("saved");
            setMessageKey("Draft saved.");
          } else {
            setSaveStatus("unsaved");
          }

          const hasQueuedEdits = queuedSaveRef.current && editRevisionRef.current > snapshotRevision;
          queuedSaveRef.current = false;
          if (!hasQueuedEdits) break;
          snapshot = formRef.current ?? form;
          snapshotRevision = editRevisionRef.current;
        } catch (error) {
          queuedSaveRef.current = false;
          if (accountSwitchAcceptedRef.current) break;
          if (isDraftConflict(error)) {
            setSaveStatus("conflict");
            setErrorKey("This draft changed in another window. Your edits are preserved. Reload the saved draft to continue.");
          } else {
            setSaveStatus("error");
            setErrorKey("Your changes could not be saved. Your edits are still here. Select Save draft to retry.");
          }
          break;
        }
      }
    } finally {
      activeSaveRevisionRef.current = -1;
      saveInFlightRef.current = false;
      setSaving(false);
    }
  }, [canEdit, currentDraft, form, isDirty, token]);

  useEffect(() => {
    if (!token || !canEdit || publishing || !isDirty || saveStatus === "error" || saveStatus === "conflict") return;
    if (saving && editRevision <= activeSaveRevisionRef.current) return;
    const timer = window.setTimeout(() => {
      void saveLatestDraft();
    }, 900);
    return () => window.clearTimeout(timer);
  }, [token, canEdit, isDirty, editRevision, saveStatus, saving, publishing, saveLatestDraft]);

  async function reloadSavedDraft() {
    const current = draftRef.current ?? currentDraft;
    if (!token || !current || reloading || saving || publishing || mediaBusyRef.current || mutationInFlightRef.current) return;
    if (!window.confirm(t("Reload the saved draft and replace the contents currently in this editor?"))) return;
    setReloading(true);
    setErrorKey(null);
    try {
      const latest = await api<VersionedPrivateEvent>(
        "/events/" + encodeURIComponent(current.id) + "/draft",
        { token },
      );
      draftRef.current = latest;
      setDraft(latest);
      const latestForm = formFromDraft(latest);
      formRef.current = latestForm;
      setFormState(latestForm);
      editRevisionRef.current = 0;
      savedRevisionRef.current = 0;
      setEditRevision(0);
      setSavedRevision(0);
      setSaveStatus(latest.draft_version ? "saved" : "error");
      setErrorKey(latest.draft_version ? null : "This draft is missing its save version. Reload it before making changes.");
      setMessageKey("The saved draft has been reloaded.");
    } catch {
      setSaveStatus("conflict");
      setErrorKey("The saved draft could not be reloaded. Your current edits are still here.");
    } finally {
      setReloading(false);
    }
  }

  async function publishDraft() {
    const latestDraft = draftRef.current ?? currentDraft;
    const latestForm = formRef.current ?? form;
    if (
      !token ||
      !latestDraft ||
      !canEdit ||
      workspace?.accreditation_status !== "approved" ||
      latestDraft.status !== "draft" ||
      !latestDraft.draft_version ||
      saving ||
      publishing ||
      mediaBusyRef.current ||
      editRevisionRef.current !== savedRevisionRef.current ||
      saveStatus !== "saved" ||
      publishIssues(latestForm).length > 0 ||
      mutationInFlightRef.current
    ) return;
    if (!window.confirm(t("Publish this saved event now?"))) return;

    mutationInFlightRef.current = true;
    setPublishing(true);
    setErrorKey(null);
    setMessageKey(null);
    try {
      const published = await api<PublicEvent>(
        "/events/" + encodeURIComponent(latestDraft.id) + "/publish",
        { token, method: "POST", ifMatch: latestDraft.draft_version },
      );
      const publishedDraft = {
        ...latestDraft,
        status: "published",
        published_at: published.published_at,
      } as VersionedPrivateEvent;
      draftRef.current = publishedDraft;
      setDraft(publishedDraft);
      setMessageKey("This event is now published.");
    } catch (error) {
      if (isDraftConflict(error)) {
        setSaveStatus("conflict");
        setErrorKey("This draft changed in another window. Your edits are preserved. Reload the saved draft to continue.");
      } else {
        setErrorKey("The event could not be published. Your saved draft is still available.");
      }
    } finally {
      mutationInFlightRef.current = false;
      setPublishing(false);
    }
  }

  const onBannerBusyChange = useCallback((busy: boolean) => {
    mediaBusyRef.current = busy;
    mediaStartRevisionRef.current = busy ? editRevisionRef.current : null;
    setMediaBusy(busy);
  }, []);
  const onBannerConflict = useCallback(() => {
    setSaveStatus("conflict");
  }, []);
  const onBannerChanged = useCallback((result: MediaMutationOut) => {
    const latestDraft = draftRef.current ?? currentDraft;
    if (!latestDraft) return;

    const nextDraft: VersionedPrivateEvent = {
      ...latestDraft,
      banner_url: result.media_url,
      ...(result.draft_version ? { draft_version: result.draft_version } : {}),
    };
    draftRef.current = nextDraft;
    setDraft(nextDraft);

    if (!result.draft_version) {
      setSaveStatus("conflict");
      setErrorKey("The banner changed, but its save version is missing. Reload the saved draft before continuing.");
      return;
    }

    const latestForm = formRef.current ?? form;
    const mediaStartRevision = mediaStartRevisionRef.current;
    if (
      result.media_url &&
      !latestForm.bannerKey &&
      mediaStartRevision !== null &&
      editRevisionRef.current === mediaStartRevision &&
      savedRevisionRef.current === mediaStartRevision
    ) {
      const nextForm = { ...latestForm, bannerKey: "heritage" as BannerKey };
      formRef.current = nextForm;
      setFormState(nextForm);
    }
  }, [currentDraft, form]);

  useEffect(() => {
    if (!hasUnsavedChanges) return;
    function warnBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = "";
    }
    function confirmInternalNavigation(event: MouseEvent) {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest("a[href]");
      if (!(anchor instanceof HTMLAnchorElement) || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
      const destination = new URL(anchor.href, window.location.href);
      if (destination.origin !== window.location.origin || destination.href === window.location.href) return;
      if (window.confirm(t("You have edits that are not fully saved. Leave this draft editor?"))) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    }
    function confirmTraversalNavigation(event: Event) {
      const navigateEvent = event as Event & {
        navigationType?: string;
        destination?: { url: string };
        hashChange?: boolean;
      };
      if (navigateEvent.navigationType !== "traverse" || !event.cancelable || navigateEvent.hashChange) return;
      const url = navigateEvent.destination?.url;
      if (!url) return;
      const destination = new URL(url, window.location.href);
      if (destination.origin !== window.location.origin || destination.href === window.location.href) return;
      if (window.confirm(t("You have edits that are not fully saved. Leave this draft editor?"))) return;
      event.preventDefault();
    }
    function confirmAccountChange(event: Event) {
      if (!window.confirm(t("Switching accounts will discard unsaved changes. Continue?"))) {
        event.preventDefault();
        return;
      }
      queueMicrotask(() => {
        if (!event.defaultPrevented) accountSwitchAcceptedRef.current = true;
      });
    }
    const navigation = (window as Window & { navigation?: NavigationApi }).navigation;
    window.addEventListener("beforeunload", warnBeforeUnload);
    window.addEventListener("intraspot:before-account-change", confirmAccountChange);
    document.addEventListener("click", confirmInternalNavigation, true);
    navigation?.addEventListener("navigate", confirmTraversalNavigation);
    return () => {
      window.removeEventListener("beforeunload", warnBeforeUnload);
      window.removeEventListener("intraspot:before-account-change", confirmAccountChange);
      document.removeEventListener("click", confirmInternalNavigation, true);
      navigation?.removeEventListener("navigate", confirmTraversalNavigation);
    };
  }, [hasUnsavedChanges, t]);

  if (authLoading) {
    return <p className={styles.loading} role="status">{t("Checking your account…")}</p>;
  }
  if (!token) {
    return (
      <div className={styles.root}>
        <section className={styles.card}>
          <p className={styles.eyebrow}>{t("Event authoring")}</p>
          <h1>{t("Sign in to edit an event")}</h1>
          <p className={styles.muted}>{t("Sign in using the site header to continue.")}</p>
        </section>
      </div>
    );
  }

  const loading = Boolean(eventId && draftResource.loading) || Boolean(orgId && workspaceResource.loading);
  if (loading) return <p className={styles.loading} role="status">{t("Loading your event workspace…")}</p>;
  if (eventId && draftResource.error) {
    return <Feedback error={draftResource.error} onRetry={draftResource.reload} />;
  }
  if (orgId && workspaceResource.error) {
    return <Feedback error={workspaceResource.error} onRetry={workspaceResource.reload} />;
  }
  if (!orgId) {
    return (
      <div className={styles.root}>
        <section className={styles.card}>
          <p className={styles.eyebrow}>{t("Event authoring")}</p>
          <h1>{t("Choose an organization")}</h1>
          <p className={styles.muted}>{t("Open the event editor from an organization workspace.")}</p>
        </section>
      </div>
    );
  }
  if (!workspace) return <p className={styles.loading} role="status">{t("Loading your organization workspace…")}</p>;

  const accreditationLabel =
    workspace.accreditation_status === "approved"
      ? t("Organization approved")
      : workspace.accreditation_status === "pending"
        ? t("Organization pending")
        : t("Organization rejected");
  const canPublish = Boolean(
    canEdit &&
    currentDraft?.status === "draft" &&
    workspace.accreditation_status === "approved" &&
    hasDraftVersion &&
    issues.length === 0 &&
    !isDirty &&
    !mediaBusy &&
    !saving &&
    !publishing &&
    saveStatus === "saved",
  );
  const saveStatusLabel = !hasDraftVersion
    ? t("Safe saving is unavailable until the draft version is loaded.")
    : saveStatus === "conflict"
      ? t("This draft has a newer saved version.")
      : saveStatus === "error"
        ? t("The latest changes still need to be saved.")
        : saving && isDirty
          ? t("Saving this version; newer edits are waiting.")
          : saving
            ? t("Saving draft…")
            : isDirty
              ? t("Unsaved changes. Saving in a moment.")
              : t("Your draft is saved.");

  if (!currentDraft && isRejected) {
    return (
      <div className={styles.root}>
        <header className={styles.heading}>
          <p className={styles.eyebrow}>{t("Event authoring")}</p>
          <h1>{t("Organization workspace")}</h1>
        </header>
        <section className={styles.card}>
          <span className="status-chip cancelled">{accreditationLabel}</span>
          <p>{t("This workspace is read-only after the organization review was rejected.")}</p>
        </section>
      </div>
    );
  }

  if (!currentDraft) {
    return (
      <div className={styles.root}>
        <header className={styles.heading}>
          <div>
            <p className={styles.eyebrow}>{t("Event authoring")}</p>
            <h1>{t("Create an event draft")}</h1>
            <p className={styles.muted}>{t("Drafts may be prepared while organization review is pending.")}</p>
          </div>
          <span className={`status-chip ${workspace.accreditation_status === "pending" ? "pending" : "confirmed"}`}>
            {accreditationLabel}
          </span>
        </header>
        <p className={styles.mobileNotice} role="note">{t("Event draft management is available on desktop. Open this page on a wider screen to create or edit a draft.")}</p>
        <section className={`${styles.card} ${styles.createCard}`}>
          <div>
            <p className={styles.eyebrow}>{t("Start with a private draft")}</p>
            <h2>{t("Create an event draft")}</h2>
            <p className={styles.muted}>
              {canCreate
                ? t("Creating a draft is explicit. You can save and preview it before the organization is approved.")
                : t("Only an organization owner or admin can create an event draft.")}
            </p>
          </div>
          {errorKey && <p className={styles.error} role="alert">{t(errorKey)}</p>}
          <button className="button" type="button" disabled={!canCreate || creating} onClick={createDraft}>
            {creating ? t("Creating draft…") : t("Create draft")}
          </button>
        </section>
      </div>
    );
  }

  const readOnly = !canEdit;
  const readOnlyReason =
    currentDraft.status === "published"
      ? t("Published events cannot be edited here.")
      : isRejected
        ? t("This event is read-only because the organization review was rejected.")
        : t("Only an organization owner or admin can edit this draft.");
  const previewTitle = form.title.trim() || t("Untitled event");
  const startsLabel = dateTimeLabel(form.startsAt, language);
  const endsLabel = dateTimeLabel(form.endsAt, language);

  if (readOnly) {
    return (
      <div className={styles.root}>
        <header className={styles.heading}>
          <div>
            <p className={styles.eyebrow}>{t("Event authoring")}</p>
            <h1>{currentDraft.status === "published" ? t("Event preview") : t("Organization workspace")}</h1>
            <p className={styles.muted}>{currentDraft.organization_name}</p>
          </div>
          <div className={styles.badges}>
            <span className="status-chip">{accreditationLabel}</span>
            <span className={`status-chip ${currentDraft.status === "published" ? "confirmed" : "pending"}`}>
              {currentDraft.status === "published" ? t("Published") : t("Draft")}
            </span>
          </div>
        </header>
        <section className={styles.card}>
          <p className={styles.muted}>{readOnlyReason}</p>
          {messageKey === "This event is now published." && (
            <p className={styles.success} role="status">{t(messageKey)}</p>
          )}
          {currentDraft.status === "published" && (
            <Link href={`/events?eventId=${encodeURIComponent(currentDraft.id)}`} className="text-action">
              {t("View published event")}
            </Link>
          )}
        </section>
        <EventPreview
          t={t}
          event={currentDraft}
          token={token}
          title={currentDraft.title || t("Untitled event")}
          summary={currentDraft.summary}
          description={currentDraft.description ?? ""}
          startsLabel={currentDraft.starts_at ? `${formatDate(currentDraft.starts_at, language)} · ${formatTime(currentDraft.starts_at, language)}` : null}
          endsLabel={currentDraft.ends_at ? `${formatDate(currentDraft.ends_at, language)} · ${formatTime(currentDraft.ends_at, language)}` : null}
          venueName={currentDraft.venue_name ?? ""}
          venueAddress={currentDraft.venue_address ?? ""}
          capacity={currentDraft.capacity === null ? "" : String(currentDraft.capacity)}
          costLabel={currentDraft.cost_label}
          registrationMode={currentDraft.registration_mode ?? "instant"}
          reviewWindowMinutes={currentDraft.review_window_minutes == null ? "" : String(currentDraft.review_window_minutes)}
          tags={eventTags(currentDraft)}
          coarseArea={eventCoarseArea(currentDraft)}
        />
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <header className={styles.heading}>
        <div>
          <p className={styles.eyebrow}>{t("Event authoring")}</p>
          <h1>{t("Edit event draft")}</h1>
          <p className={styles.muted}>{currentDraft.organization_name}</p>
        </div>
        <div className={styles.badges}>
          <span className={`status-chip ${workspace.accreditation_status === "pending" ? "pending" : "confirmed"}`}>
            {accreditationLabel}
          </span>
          <span className="status-chip">{t("Private draft")}</span>
        </div>
      </header>

      <p className={styles.mobileNotice} role="note">
        {t("Event draft management is available on desktop. Open this page on a wider screen to edit or publish.")}
      </p>

      <form
        className={styles.editorGrid}
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          void saveLatestDraft();
        }}
        noValidate
      >
        <fieldset className={styles.sections} disabled={publishing || reloading || mediaBusy}>
          <legend className={styles.visuallyHidden}>{t("Event fields")}</legend>
          <section className={styles.card} aria-labelledby="draft-basics-heading">
            <div className={styles.sectionHeading}>
              <span className={styles.step}>01</span>
              <div>
                <h2 id="draft-basics-heading">{t("Event details")}</h2>
                <p className={styles.muted}>{t("Give attendees the essentials at a glance.")}</p>
              </div>
            </div>
            <div className={styles.fieldGrid}>
              <label className={styles.field}>
                {t("Event type")}
                <select
                  aria-label={t("Event type")}
                  aria-describedby={form.eventType === "flash" ? "draft-flash-time-help" : undefined}
                  value={form.eventType}
                  onChange={(event) => updateEventType(event.currentTarget.value as EventType)}
                >
                  <option value="scheduled">{t("Scheduled event")}</option>
                  <option value="flash">{t("Flash event")}</option>
                </select>
                {form.eventType === "flash" && (
                  <span id="draft-flash-time-help" className={styles.fieldHint}>
                    {t("Flash events must start within 24 hours of publication.")}
                  </span>
                )}
              </label>
              <label className={styles.field}>
                {t("Event title")}
                <input maxLength={200} value={form.title} onChange={(event) => updateField("title", event.target.value)} />
              </label>
              <label className={styles.field}>
                {t("Short summary")}
                <input
                  value={form.summary}
                  maxLength={SUMMARY_MAX_LENGTH}
                  aria-label={t("Short summary")}
                  aria-describedby="draft-summary-help"
                  onChange={(event) => updateField("summary", event.target.value)}
                />
                <span id="draft-summary-help" className={styles.fieldHint}>
                  {t("{count}/200 characters", { count: form.summary.length })}
                </span>
              </label>
              <label className={styles.field}>
                {t("Artwork theme")}
                <select value={form.bannerKey} onChange={(event) => updateField("bannerKey", event.target.value as BannerKey | "")}>
                  <option value="">{t("Choose a theme")}</option>
                  <option value="heritage">{t("Heritage")}</option>
                  <option value="design">{t("Design")}</option>
                  <option value="garden">{t("Garden")}</option>
                  <option value="music">{t("Music")}</option>
                </select>
              </label>
              <label className={styles.field}>
                {t("Cost label")}
                <input maxLength={100} value={form.costLabel} onChange={(event) => updateField("costLabel", event.target.value)} />
              </label>
            </div>
            <div className={`${styles.field} ${styles.descriptionField}`}>
              <MediaUploader
                endpoint={`/events/${encodeURIComponent(currentDraft.id)}/banner`}
                token={token}
                ifMatch={currentDraft.draft_version ?? undefined}
                disabled={mediaMutationDisabled}
                currentUrl={currentDraft.banner_url ?? null}
                onChanged={onBannerChanged}
                onBusyChange={onBannerBusyChange}
                onConflict={onBannerConflict}
              />
            </div>
            <label className={`${styles.field} ${styles.descriptionField}`}>
              {t("Tags (optional)")}
              <input
                value={form.tagsText}
                  aria-label={t("Tags (optional)")}
                aria-describedby="draft-tags-help"
                aria-invalid={metadataValidation.includes("Use at most 16 tags, each 1–64 characters.")}
                onChange={(event) => updateField("tagsText", event.target.value)}
              />
              <span id="draft-tags-help" className={styles.fieldHint}>
                {t("Separate tags with commas. Add up to 16 tags, each 1–64 characters.")}
              </span>
            </label>
            <label className={`${styles.field} ${styles.descriptionField}`}>
              {t("Description")}
              <textarea aria-label={t("Description")} rows={6} value={form.description} onChange={(event) => updateField("description", event.target.value)} />
            </label>
          </section>

          <section className={styles.card} aria-labelledby="draft-schedule-heading">
            <div className={styles.sectionHeading}>
              <span className={styles.step}>02</span>
              <div>
                <h2 id="draft-schedule-heading">{t("Schedule and venue")}</h2>
                <p className={styles.muted}>{t("Times are entered in Manila time.")}</p>
              </div>
            </div>
            <div className={styles.fieldGrid}>
              <label className={styles.field}>
                {t("Starts at (Manila time)")}
                <input type="datetime-local" value={form.startsAt} onChange={(event) => updateField("startsAt", event.target.value)} />
              </label>
              <label className={styles.field}>
                {t("Ends at (Manila time)")}
                <input type="datetime-local" value={form.endsAt} onChange={(event) => updateField("endsAt", event.target.value)} />
              </label>
              <label className={styles.field}>
                {t("Venue name")}
                <input maxLength={200} value={form.venueName} onChange={(event) => updateField("venueName", event.target.value)} />
              </label>
              <label className={styles.field}>
                {t("Venue address")}
                <input maxLength={500} value={form.venueAddress} onChange={(event) => updateField("venueAddress", event.target.value)} />
              </label>
              <label className={styles.field}>
                {t("Broad area (optional)")}
                <input
                  maxLength={MAX_COARSE_AREA_LENGTH}
                  aria-label={t("Broad area (optional)")}
                  value={form.coarseArea}
                  aria-describedby="draft-area-help"
                  aria-invalid={metadataValidation.includes("Keep the broad area to 80 characters or fewer.")}
                  onChange={(event) => updateField("coarseArea", event.target.value)}
                />
                <span id="draft-area-help" className={styles.fieldHint}>
                  {t("Use a broad place name, not an address.")}
                </span>
              </label>
              <label className={styles.field}>
                {t("Capacity")}
                <input type="number" min={1} max={MAX_CAPACITY} step={1} value={form.capacity} onChange={(event) => updateField("capacity", event.target.value)} />
              </label>
            </div>
          </section>

          <section className={styles.card} aria-labelledby="draft-registration-heading">
            <div className={styles.sectionHeading}>
              <span className={styles.step}>03</span>
              <div>
                <h2 id="draft-registration-heading">{t("Registration")}</h2>
                <p className={styles.muted}>{t("Choose how attendee requests are handled.")}</p>
              </div>
            </div>
            <div className={styles.fieldGrid}>
              <label className={styles.field}>
                {t("Registration mode")}
                <select
                  aria-label={t("Registration mode")}
                  value={form.registrationMode}
                  disabled={form.eventType === "flash"}
                  onChange={(event) => updateField("registrationMode", event.target.value as RegistrationMode)}
                >
                  <option value="instant">{t("Instant acceptance")}</option>
                  {form.eventType !== "flash" && <option value="approval">{t("Organization approval")}</option>}
                </select>
                {form.eventType === "flash" && (
                  <span className={styles.fieldHint}>
                    {t("Flash events use instant registration and have no review window.")}
                  </span>
                )}
              </label>
              {form.registrationMode === "approval" && (
                <label className={styles.field}>
                  {t("Review window (15–2,880 minutes)")}
                  <input
                    type="number"
                    min={15}
                    max={2880}
                    step={1}
                    value={form.reviewWindowMinutes}
                    aria-label={t("Review window (15–2,880 minutes)")}
                    aria-describedby="review-window-help"
                    onChange={(event) => updateField("reviewWindowMinutes", event.target.value)}
                  />
                  <span id="review-window-help" className={styles.fieldHint}>
                    {t("Review deadlines are capped at the event start.")}
                  </span>
                </label>
              )}
            </div>
          </section>
        </fieldset>

        <aside className={styles.sidebar} aria-label={t("Draft status and preview")}>
          <section className={`${styles.card} ${styles.actionCard}`} aria-labelledby="draft-save-heading">
            <div className={styles.actionHeading}>
              <div>
                <p className={styles.eyebrow}>{t("Workspace actions")}</p>
                <h2 id="draft-save-heading">{t("Draft status")}</h2>
              </div>
              <span className={`status-chip ${saveStatus === "conflict" ? "cancelled" : saveStatus === "error" ? "cancelled" : isDirty || saving ? "pending" : "confirmed"}`}>
                {saving ? t("Saving") : saveStatus === "conflict" ? t("Conflict") : saveStatus === "error" ? t("Needs attention") : isDirty ? t("Unsaved") : t("Saved")}
              </span>
            </div>
            <p className={styles.statusText} role="status" aria-live="polite">{saveStatusLabel}</p>
            {errorKey && <p className={styles.error} role="alert">{t(errorKey)}</p>}
            {messageKey && <p className={styles.success} role="status">{t(messageKey)}</p>}
            <div className={styles.actions}>
              <button
                className="button button-secondary"
                type="submit"
                disabled={!isDirty || saving || publishing || mediaBusy || saveStatus === "conflict" || !hasDraftVersion}
                aria-label={t("Save draft")}
              >
                {t("Save draft")}
              </button>
              {workspace.accreditation_status === "pending" ? (
                <button className="button" type="button" disabled aria-describedby="publish-reason">
                  {t("Publish")}
                </button>
              ) : (
                <button className="button" type="button" disabled={!canPublish || mediaBusy} onClick={() => void publishDraft()}>
                  {t("Publish")}
                </button>
              )}
            </div>
            {saveStatus === "conflict" || !hasDraftVersion ? (
              <button className={styles.textButton} type="button" disabled={reloading || mediaBusy} onClick={() => void reloadSavedDraft()}>
                {reloading ? t("Reloading saved draft…") : t("Reload saved draft")}
              </button>
            ) : null}
            {workspace.accreditation_status === "pending" ? (
              <p id="publish-reason" className={styles.fieldHint}>{t("Publishing is disabled until a platform administrator approves this organization.")}</p>
            ) : issues.length > 0 ? (
              <div className={styles.validation} aria-label={t("Publish checklist")}>
                <p>{t("Complete these items before publishing:")}</p>
                <ul>{issues.map((issue) => <li key={issue}>{t(issue)}</li>)}</ul>
              </div>
            ) : isDirty || saving ? (
              <p className={styles.fieldHint}>{t("Save all changes before publishing.")}</p>
            ) : null}
            {errorKey === "The event could not be published. Your saved draft is still available." && (
              <p className={styles.fieldHint}>{t("The draft remains saved. You can retry Publish when ready.")}</p>
            )}
          </section>

          <EventPreview
            t={t}
            event={{ banner_key: form.bannerKey || null, banner_url: currentDraft.banner_url ?? null, event_type: form.eventType, title: previewTitle }}
            token={token}
            title={previewTitle}
            summary={form.summary}
            description={form.description}
            startsLabel={startsLabel}
            endsLabel={endsLabel}
            venueName={form.venueName}
            venueAddress={form.venueAddress}
            capacity={form.capacity}
            costLabel={form.costLabel}
            registrationMode={form.registrationMode}
            reviewWindowMinutes={form.reviewWindowMinutes}
            tags={tagsFromText(form.tagsText)}
            coarseArea={form.coarseArea.trim()}
          />
        </aside>
      </form>

    </div>
  );
}

function EventPreview({
  t,
  event,
  token,
  title,
  summary,
  description,
  startsLabel,
  endsLabel,
  venueName,
  venueAddress,
  capacity,
  costLabel,
  registrationMode,
  reviewWindowMinutes,
  tags,
  coarseArea,
}: {
  t: ReturnType<typeof useT>;
  event: Pick<PrivateEvent, "banner_key" | "banner_url" | "event_type" | "title"> & {is_featured?: boolean};
  token?: string | null;
  title: string;
  summary: string;
  description: string;
  startsLabel: string | null;
  endsLabel: string | null;
  venueName: string;
  venueAddress: string;
  capacity: string;
  costLabel: string;
  registrationMode: RegistrationMode;
  reviewWindowMinutes: string;
  tags: string[];
  coarseArea: string;
}) {
  return (
    <section className={`${styles.card} ${styles.previewCard}`} aria-label={t("Event preview")}>
      <div className={styles.previewHeading}>
        <div>
          <p className={styles.eyebrow}>{t("Live preview")}</p>
          <h2>{t("How attendees will see your event")}</h2>
        </div>
        <span className={styles.previewDot} aria-hidden="true" />
      </div>
      <EventArtwork event={event} token={token} />
      <div className={styles.previewContent}>
        {event.is_featured && <FeaturedBadge />}
        {event.event_type === "flash" && (
          <span className={styles.eventTypeBadge}>{t("Flash event")}</span>
        )}
        <h3>{title}</h3>
        <p className={summary ? styles.summary : styles.muted}>{summary || t("No summary added yet.")}</p>
        <p className={description ? styles.description : styles.muted}>{description || t("No description added yet.")}</p>
      </div>
      <dl className={styles.facts}>
        <div><dt>{t("Starts")}</dt><dd>{startsLabel || t("Date and time not set")}</dd></div>
        <div><dt>{t("Ends")}</dt><dd>{endsLabel || t("Date and time not set")}</dd></div>
        <div><dt>{t("Venue")}</dt><dd>{venueName || t("Venue not set")}{venueAddress ? ` · ${venueAddress}` : ""}</dd></div>
        {coarseArea && <div><dt>{t("Broad area")}</dt><dd>{coarseArea}</dd></div>}
        {tags.length > 0 && <div><dt>{t("Tags")}</dt><dd>{tags.join(", ")}</dd></div>}
        <div><dt>{t("Capacity")}</dt><dd>{capacity ? t("{count} attendees", { count: capacity }) : t("Capacity not set")}</dd></div>
        <div><dt>{t("Cost")}</dt><dd>{costLabel || t("Cost not set")}</dd></div>
        <div><dt>{t("Registration")}</dt><dd>
          {registrationMode === "approval"
            ? t("Organization approval · {minutes} minute review window", { minutes: reviewWindowMinutes || t("not set") })
            : t("Instant acceptance")}
        </dd></div>
      </dl>
      <p className={styles.previewNote}>{t("This preview updates as you edit. Saving keeps it private until you publish.")}</p>
    </section>
  );
}
