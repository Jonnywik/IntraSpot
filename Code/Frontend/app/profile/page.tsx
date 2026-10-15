'use client';

import { useState, type FormEvent } from 'react';
import { Feedback } from '@/components/feedback';
import { ApiError, api } from '@/lib/api';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { Profile } from '@/lib/types';

type ProfileFields = { nickname: string; ageBracket: string; tags: string };

function fieldsFromProfile(profile: Profile): ProfileFields {
  return {
    nickname: profile.nickname ?? '',
    ageBracket: profile.age_bracket ?? '',
    tags: profile.tags.join(', '),
  };
}

function asApiError(error: unknown, fallback: string): ApiError {
  return error instanceof ApiError ? error : new ApiError(0, 'request_failed', fallback);
}

function visibleApiError(error: ApiError): Error {
  if (error.status === 401) return new Error(`Your local session could not be verified. ${error.message}`);
  if (error.status === 403) return new Error(`Forbidden (${error.status}). ${error.message}`);
  if (error.status === 422) return new Error(`Profile validation failed. ${error.message}`);
  return error;
}

export default function ProfilePage() {
  const { actor, token, authLoading, refreshActor } = useSession();
  const profile = useApiResource<Profile>(token ? '/me/profile' : null, token);

  const heading = <header className="page-heading">
    <p className="eyebrow">Your account</p>
    <h1>Profile</h1>
    <p className="muted">Set a nickname, age bracket, and at least one interest or vibe tag.</p>
  </header>;

  if (authLoading) return <>{heading}<Feedback loading /></>;

  if (!actor || !token) return <>
    {heading}
    <section className="panel stack">
      <h2>Profile unavailable as a guest</h2>
      <p>Choose a local fictional account in the site header to edit its profile. You can continue browsing as a guest.</p>
    </section>
  </>;

  if (profile.error) return <>
    {heading}
    <Feedback error={visibleApiError(profile.error)} onRetry={profile.reload} />
  </>;

  if (profile.loading || !profile.data) return <>{heading}<Feedback loading /></>;

  return <>
    {heading}
    <ProfileEditor key={token} token={token} profile={profile.data} refreshActor={refreshActor} />
  </>;
}

function ProfileEditor({ token, profile, refreshActor }: {
  token: string;
  profile: Profile;
  refreshActor: () => Promise<void>;
}) {
  const [fields, setFields] = useState<ProfileFields>(() => fieldsFromProfile(profile));
  const [clientError, setClientError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<ApiError | null>(null);
  const [success, setSuccess] = useState(false);
  const [refreshError, setRefreshError] = useState<Error | null>(null);
  const [saving, setSaving] = useState(false);
  const [refreshingActor, setRefreshingActor] = useState(false);

  function updateField(field: keyof ProfileFields, value: string) {
    setFields(current => ({ ...current, [field]: value }));
    setClientError(null);
    setSaveError(null);
    setSuccess(false);
    setRefreshError(null);
  }

  async function refreshCurrentActor() {
    setRefreshingActor(true);
    setRefreshError(null);
    try {
      await refreshActor();
    } catch (error) {
      const details = visibleApiError(asApiError(error, 'The session could not be refreshed. Retry.'));
      setRefreshError(new Error(`Your profile was saved, but the session could not be refreshed. ${details.message}`));
    } finally {
      setRefreshingActor(false);
    }
  }

  async function saveProfile(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!token) return;

    const nickname = fields.nickname.trim();
    const ageBracket = fields.ageBracket.trim();
    const tags = fields.tags.split(',').map(tag => tag.trim()).filter(Boolean);
    const invalid = !nickname ? 'Enter a nickname.'
      : nickname.length > 64 ? 'Nickname must be 64 characters or fewer.'
        : !ageBracket ? 'Enter an age bracket, not a full birth date.'
          : ageBracket.length > 32 ? 'Age bracket must be 32 characters or fewer.'
            : tags.length === 0 ? 'Add at least one interest or vibe tag.'
              : tags.length > 32 ? 'Use 32 tags or fewer.'
                : tags.some(tag => tag.length > 64) ? 'Each tag must be 64 characters or fewer.'
                  : null;
    if (invalid) {
      setClientError(invalid);
      setSaveError(null);
      setSuccess(false);
      return;
    }

    setSaving(true);
    setClientError(null);
    setSaveError(null);
    setRefreshError(null);
    setSuccess(false);
    try {
      const updated = await api<Profile>('/me/profile', {
        token,
        method: 'PATCH',
        body: { nickname, age_bracket: ageBracket, tags },
      });
      setFields({
        nickname: updated.nickname ?? '',
        ageBracket: updated.age_bracket ?? '',
        tags: updated.tags.join(', '),
      });
      setSuccess(true);
      await refreshCurrentActor();
    } catch (error) {
      setSaveError(asApiError(error, 'The profile could not be saved. Retry when the local backend is ready.'));
    } finally {
      setSaving(false);
    }
  }

  const retrySave = () => void saveProfile();

  return <>
    <div className="stack">
      {clientError && <p className="panel error" role="alert">{clientError}</p>}
      {saveError && <Feedback
        error={visibleApiError(saveError)}
        onRetry={saveError.status === 401 || saveError.status === 403 || saveError.status === 422 ? undefined : retrySave}
      />}
      {success && <p className="panel" role="status">Profile saved.</p>}
      {refreshError && <Feedback error={refreshError} onRetry={() => void refreshCurrentActor()} />}
      <form className="panel stack" onSubmit={event => void saveProfile(event)}>
        <label className="field">
          <span>Nickname</span>
          <input
            autoComplete="nickname"
            maxLength={64}
            required
            value={fields.nickname}
            onChange={event => updateField('nickname', event.target.value)}
          />
        </label>
        <label className="field">
          <span>Age bracket</span>
          <input
            maxLength={32}
            aria-label="Age bracket"
            aria-describedby="profile-age-help"
            placeholder="For example, 18-24"
            required
            value={fields.ageBracket}
            onChange={event => updateField('ageBracket', event.target.value)}
          />
          <small id="profile-age-help">Enter a bracket only; do not enter a full birth date.</small>
        </label>
        <label className="field">
          <span>Interest or vibe tags</span>
          <input
            required
            aria-label="Interest or vibe tags"
            value={fields.tags}
            onChange={event => updateField('tags', event.target.value)}
            aria-describedby="profile-tags-help"
          />
          <small id="profile-tags-help">Separate tags with commas. Add at least one.</small>
        </label>
        <div className="actions">
          <button className="button" type="submit" disabled={saving || refreshingActor}>
            {saving ? 'Saving profile…' : 'Save profile'}
          </button>
          {(saving || refreshingActor) && <span role="status">Saving your profile…</span>}
        </div>
      </form>
    </div>
  </>;
}
