'use client';

import { useState, type FormEvent } from 'react';
import { Feedback } from '@/components/feedback';
import { ApiError, api } from '@/lib/api';
import { useT } from '@/lib/i18n';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { Profile } from '@/lib/types';
import attendeeStyles from '@/features/attendee-pages.module.css';
import profileStyles from '@/features/profile-mobile.module.css';

type ProfileFields = { nickname: string; ageBracket: string; tags: string };
type ProfileValidationError = { field: keyof ProfileFields; message: string } | null;

function profileCompletion(fields: ProfileFields): number {
  const nickname = fields.nickname.trim();
  const ageBracket = fields.ageBracket.trim();
  const tags = fields.tags.split(',').map(tag => tag.trim()).filter(Boolean);
  return [
    nickname.length > 0 && nickname.length <= 64,
    ageBracket.length > 0 && ageBracket.length <= 32,
    tags.length > 0 && tags.length <= 32 && tags.every(tag => tag.length <= 64),
  ].filter(Boolean).length;
}

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

function visibleApiError(error: ApiError, t: ReturnType<typeof useT>): Error {
  if (error.status === 401) return new Error(t('Your local session could not be verified. {message}', { message: t(error.message) }));
  if (error.status === 403) return new Error(t('Forbidden ({status}). {message}', { status: error.status, message: t(error.message) }));
  if (error.status === 422) return new Error(t('Profile validation failed. {message}', { message: t(error.message) }));
  return new Error(t(error.message));
}

export default function ProfilePage() {
  const t = useT();
  const { actor, token, authLoading, refreshActor } = useSession();
  const profile = useApiResource<Profile>(token ? '/me/profile' : null, token);
  const pageClass = `${attendeeStyles.profilePage} ${profileStyles.page}`;

  const heading = <header className={`page-heading ${attendeeStyles.profileHeading}`}>
    <p className="eyebrow">{t('Your account')}</p>
    <h1>{t('Profile')}</h1>
    <p className="muted">{t('Set a nickname, age bracket, and at least one interest or vibe tag.')}</p>
  </header>;

  if (authLoading) return <section className={pageClass}>{heading}<Feedback loading /></section>;

  if (!actor || !token) return (
    <section className={pageClass}>
      {heading}
      <section className="panel stack">
        <h2>{t('Profile unavailable as a guest')}</h2>
        <p>{t('Sign in using the site header to edit your profile. You can continue browsing as a guest.')}</p>
      </section>
    </section>
  );

  if (profile.error) return (
    <section className={pageClass}>
      {heading}
      <Feedback error={visibleApiError(profile.error, t)} onRetry={profile.reload} />
    </section>
  );

  if (profile.loading || !profile.data) return <section className={pageClass}>{heading}<Feedback loading /></section>;

  return <section className={pageClass}>
    {heading}
    <ProfileEditor key={token} token={token} profile={profile.data} refreshActor={refreshActor} />
  </section>;
}

function ProfileEditor({ token, profile, refreshActor }: {
  token: string;
  profile: Profile;
  refreshActor: () => Promise<void>;
}) {
  const t = useT();
  const [fields, setFields] = useState<ProfileFields>(() => fieldsFromProfile(profile));
  const [clientError, setClientError] = useState<ProfileValidationError>(null);
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
      const details = visibleApiError(asApiError(error, t('The session could not be refreshed. Retry.')), t);
      setRefreshError(new Error(t('Your profile was saved, but the session could not be refreshed. {message}', { message: details.message })));
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
    const invalid: ProfileValidationError = !nickname ? { field: 'nickname', message: t('Enter a nickname.') }
      : nickname.length > 64 ? { field: 'nickname', message: t('Nickname must be 64 characters or fewer.') }
        : !ageBracket ? { field: 'ageBracket', message: t('Enter an age bracket, not a full birth date.') }
          : ageBracket.length > 32 ? { field: 'ageBracket', message: t('Age bracket must be 32 characters or fewer.') }
            : tags.length === 0 ? { field: 'tags', message: t('Add at least one interest or vibe tag.') }
              : tags.length > 32 ? { field: 'tags', message: t('Use 32 tags or fewer.') }
                : tags.some(tag => tag.length > 64) ? { field: 'tags', message: t('Each tag must be 64 characters or fewer.') }
                  : null;
    if (invalid) {
      setClientError(invalid);
      setSaveError(null);
      setSuccess(false);
      event?.currentTarget.querySelector<HTMLInputElement>(`#profile-${invalid.field}`)?.focus();
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
      setSaveError(asApiError(error, t('The profile could not be saved. Retry when the local backend is ready.')));
    } finally {
      setSaving(false);
    }
  }

  const retrySave = () => void saveProfile();
  const completedFields = profileCompletion(fields);

  return <section className="stack">
      {clientError && <p className={`panel error ${profileStyles.validationError}`} id="profile-validation-error" role="alert">{clientError.message}</p>}
      {saveError && <Feedback
        error={visibleApiError(saveError, t)}
        onRetry={saveError.status === 401 || saveError.status === 403 || saveError.status === 422 ? undefined : retrySave}
      />}
      {success && <p className="panel" role="status">{t('Profile saved.')}</p>}
      {refreshError && <Feedback error={refreshError} onRetry={() => void refreshCurrentActor()} />}
      <aside className={`panel ${attendeeStyles.profileNotice} ${profileStyles.privacyNotice}`} aria-label={t('Profile privacy and registration requirements')}>
        <p>{t('Your profile is private by default. You can browse events before completing it, but requesting a registration requires a nickname, an age bracket, and at least one interest or vibe tag.')}</p>
      </aside>
      <section className={`panel ${profileStyles.completion}`} aria-labelledby="profile-completion-heading">
        <p className={profileStyles.completionTitle} id="profile-completion-heading">{t('Profile completion')}</p>
        <progress className={profileStyles.completionBar} aria-labelledby="profile-completion-heading" max={3} value={completedFields}>
          {completedFields} / 3
        </progress>
        <p className={profileStyles.completionCount} role="status" aria-live="polite">
          {t('{count} of 3 required profile fields complete', { count: completedFields })}
        </p>
      </section>
      <form className={`panel stack ${attendeeStyles.profileForm} ${profileStyles.form}`} noValidate onSubmit={event => void saveProfile(event)}>
        <label className="field">
          <span>{t('Nickname')}</span>
          <input
            id="profile-nickname"
            name="nickname"
            autoComplete="nickname"
            maxLength={64}
            required
            disabled={saving || refreshingActor}
            aria-invalid={clientError?.field === 'nickname' || undefined}
            aria-describedby={clientError?.field === 'nickname' ? 'profile-validation-error' : undefined}
            value={fields.nickname}
            onChange={event => updateField('nickname', event.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('Age bracket')}</span>
          <input
            id="profile-ageBracket"
            name="ageBracket"
            maxLength={32}
            disabled={saving || refreshingActor}
            aria-label={t('Age bracket')}
            aria-invalid={clientError?.field === 'ageBracket' || undefined}
            aria-describedby={clientError?.field === 'ageBracket' ? 'profile-age-help profile-validation-error' : 'profile-age-help'}
            placeholder={t('For example, 18-24')}
            required
            value={fields.ageBracket}
            onChange={event => updateField('ageBracket', event.target.value)}
          />
          <small id="profile-age-help">{t('Enter a bracket only; do not enter a full birth date.')}</small>
        </label>
        <label className="field">
          <span>{t('Interest or vibe tags')}</span>
          <input
            id="profile-tags"
            name="tags"
            required
            disabled={saving || refreshingActor}
            aria-label={t('Interest or vibe tags')}
            aria-invalid={clientError?.field === 'tags' || undefined}
            value={fields.tags}
            onChange={event => updateField('tags', event.target.value)}
            aria-describedby={clientError?.field === 'tags' ? 'profile-tags-help profile-validation-error' : 'profile-tags-help'}
          />
          <small id="profile-tags-help">{t('Separate tags with commas. Add at least one.')}</small>
        </label>
        <div className="actions">
          <button className="button" type="submit" disabled={saving || refreshingActor}>
            {saving ? t('Saving profile…') : t('Save profile')}
          </button>
          {(saving || refreshingActor) && <span role="status">{t('Saving your profile…')}</span>}
        </div>
      </form>
    </section>;
}
