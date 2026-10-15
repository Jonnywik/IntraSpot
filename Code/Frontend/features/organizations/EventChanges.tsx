'use client';

import { useState, type FormEvent } from 'react';
import { Feedback } from '@/components/feedback';
import { api } from '@/lib/api';
import { formatDate, formatTime, fromUtcToManila, toUtcFromManila } from '@/lib/date';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { EventChangeInput, PrivateEvent, RegistrationReview as RegistrationReviewItem } from '@/lib/types';

type SelectionMode = EventChangeInput['selection_mode'];
type ChangeForm = {
  startsAt: string;
  endsAt: string;
  venueName: string;
  venueAddress: string;
  capacity: string;
  costLabel: string;
  reconfirmDeadline: string;
};
type MaterialFields = Pick<EventChangeInput,
  'starts_at' | 'ends_at' | 'venue_name' | 'venue_address' | 'capacity' | 'cost_label'
>;

function isSeatHolder(status: string) {
  return status === 'confirmed' || status === 'pending' || status === 'reconfirmation_required';
}

function manilaDate(value: string) {
  if (!value) return 'Not set';
  try {
    const utc = toUtcFromManila(value);
    return `${formatDate(utc)} · ${formatTime(utc)} (Manila)`;
  } catch {
    return 'Enter a valid Manila date and time';
  }
}

function validateProposedSchedule(startsAt: string, endsAt: string, reconfirmDeadline: string) {
  const startsAtMs = Date.parse(startsAt);
  const endsAtMs = Date.parse(endsAt);
  const deadlineMs = Date.parse(reconfirmDeadline);
  const now = Date.now();
  if (startsAtMs <= now) throw new Error('The proposed event start must be in the future.');
  if (endsAtMs <= startsAtMs) throw new Error('The event end must be after its start.');
  if (deadlineMs <= now || deadlineMs >= startsAtMs) {
    throw new Error('The reconfirmation deadline must be in the future and before the proposed event start.');
  }
}

export function EventChanges({event, onChanged}: {
  event: PrivateEvent;
  onChanged: () => void;
}) {
  const {token} = useSession();
  const [currentEvent, setCurrentEvent] = useState<PrivateEvent>(event);
  const [form, setForm] = useState<ChangeForm>(() => ({
    startsAt: event.starts_at ? fromUtcToManila(event.starts_at) : '',
    endsAt: event.ends_at ? fromUtcToManila(event.ends_at) : '',
    venueName: event.venue_name ?? '',
    venueAddress: event.venue_address ?? '',
    capacity: event.capacity === null ? '' : String(event.capacity),
    costLabel: event.cost_label,
    reconfirmDeadline: '',
  }));
  const [selectionMode, setSelectionMode] = useState<SelectionMode>('exact');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState('');

  const originalStart = currentEvent.starts_at ? fromUtcToManila(currentEvent.starts_at) : '';
  const originalEnd = currentEvent.ends_at ? fromUtcToManila(currentEvent.ends_at) : '';
  const originalVenueName = currentEvent.venue_name ?? '';
  const originalVenueAddress = currentEvent.venue_address ?? '';
  const proposedCapacity = form.capacity.trim() === '' ? null : Number(form.capacity);
  const capacityValid = proposedCapacity !== null && Number.isInteger(proposedCapacity) && proposedCapacity > 0;
  const capacityChanged = capacityValid && proposedCapacity !== currentEvent.capacity;
  const capacityReduced = capacityChanged && proposedCapacity !== null && currentEvent.capacity !== null &&
    proposedCapacity < currentEvent.capacity;
  const reviewPath = open && capacityReduced && token
    ? `/events/${encodeURIComponent(currentEvent.id)}/registration-review`
    : null;
  const occupied = useApiResource<RegistrationReviewItem[]>(reviewPath, token);
  const seatHolders = (occupied.data ?? []).filter(item => isSeatHolder(item.registration.status));
  const seatsToRemove = capacityReduced && proposedCapacity !== null && occupied.data !== null
    ? Math.max(0, seatHolders.length - proposedCapacity)
    : 0;
  const eligibleIds = new Set(seatHolders.map(item => item.registration.id));
  const selectedCurrentIds = selectedIds.filter(id => eligibleIds.has(id));

  function updateField<K extends keyof ChangeForm>(field: K, value: ChangeForm[K]) {
    setForm(previous => ({...previous, [field]: value}));
    setError(null);
    setMessage('');
  }

  function toggleRegistration(id: string) {
    setSelectedIds(previous => previous.includes(id)
      ? previous.filter(selected => selected !== id)
      : [...previous, id]);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || saving) return;
    setSaving(true);
    setError(null);
    setMessage('');

    try {
      if (!capacityValid || proposedCapacity === null) throw new Error('Capacity must be a positive whole number.');
      if (!form.startsAt || !form.endsAt) throw new Error('Set both a future start and end time.');
      if (!form.reconfirmDeadline) throw new Error('Set a reconfirmation deadline in Manila time.');

      const startsAt = toUtcFromManila(form.startsAt);
      const endsAt = toUtcFromManila(form.endsAt);
      const reconfirmDeadline = toUtcFromManila(form.reconfirmDeadline);
      validateProposedSchedule(startsAt, endsAt, reconfirmDeadline);

      const fields: MaterialFields = {};
      if (form.startsAt !== originalStart) fields.starts_at = startsAt;
      if (form.endsAt !== originalEnd) fields.ends_at = endsAt;
      if (form.venueName !== originalVenueName) fields.venue_name = form.venueName.trim() || null;
      if (form.venueAddress !== originalVenueAddress) fields.venue_address = form.venueAddress.trim() || null;
      if (capacityChanged && proposedCapacity !== null) fields.capacity = proposedCapacity;
      if (form.costLabel !== currentEvent.cost_label) fields.cost_label = form.costLabel.trim();
      if (!Object.keys(fields).length) throw new Error('Change at least one material event field before submitting.');

      if (capacityReduced) {
        if (occupied.loading) throw new Error('Wait for the current occupied registrations to load.');
        if (occupied.error || occupied.data === null) throw new Error('Refresh the occupied registrations before reducing capacity.');
        if (seatsToRemove > 0) {
          const enoughSelected = selectionMode === 'exact'
            ? selectedCurrentIds.length === seatsToRemove
            : selectedCurrentIds.length >= seatsToRemove;
          if (!enoughSelected) {
            throw new Error(selectionMode === 'exact'
              ? `Select exactly ${seatsToRemove} occupied registration${seatsToRemove === 1 ? '' : 's'}.`
              : `Select at least ${seatsToRemove} occupied registration${seatsToRemove === 1 ? '' : 's'} for the pool.`);
          }
        }
      }

      const request: EventChangeInput = {
        ...fields,
        reconfirm_deadline: reconfirmDeadline,
        selection_mode: selectionMode,
        selected_registration_ids: capacityReduced && seatsToRemove > 0 ? selectedCurrentIds : [],
      };
      const updatedEvent = await api<PrivateEvent>(`/events/${encodeURIComponent(currentEvent.id)}/changes`, {
        token,
        method: 'POST',
        body: request,
      });

      setCurrentEvent(updatedEvent);
      setForm({
        startsAt: updatedEvent.starts_at ? fromUtcToManila(updatedEvent.starts_at) : '',
        endsAt: updatedEvent.ends_at ? fromUtcToManila(updatedEvent.ends_at) : '',
        venueName: updatedEvent.venue_name ?? '',
        venueAddress: updatedEvent.venue_address ?? '',
        capacity: updatedEvent.capacity === null ? '' : String(updatedEvent.capacity),
        costLabel: updatedEvent.cost_label,
        reconfirmDeadline: '',
      });
      setSelectedIds([]);
      setMessage('Material changes submitted. Confirmed attendees and anyone already reconfirming must respond to the new revision; pending reviews remain pending.');
      occupied.reload();
      onChanged();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The material change could not be submitted.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <details className="panel" onToggle={event => setOpen(event.currentTarget.open)}>
      <summary>Propose a material event change</summary>
      {open && (
        <form className="stack" onSubmit={submit} noValidate>
          <p className="muted">
            Confirmed attendees and anyone already reconfirming must respond to a material change. Pending reviews stay pending and are not asked to reconfirm; their review deadlines may be capped at the new event start. The deadline is required and must be before the event starts.
          </p>
          <div className="form-grid">
            <label className="field">
              Starts at (Manila time)
              <input type="datetime-local" value={form.startsAt} onChange={event => updateField('startsAt', event.target.value)} />
            </label>
            <label className="field">
              Ends at (Manila time)
              <input type="datetime-local" value={form.endsAt} onChange={event => updateField('endsAt', event.target.value)} />
            </label>
            <label className="field">
              Venue name
              <input value={form.venueName} onChange={event => updateField('venueName', event.target.value)} />
            </label>
            <label className="field">
              Venue address
              <input value={form.venueAddress} onChange={event => updateField('venueAddress', event.target.value)} />
            </label>
            <label className="field">
              Capacity
              <input type="number" min={1} step={1} required value={form.capacity} onChange={event => updateField('capacity', event.target.value)} />
            </label>
            <label className="field">
              Cost label
              <input value={form.costLabel} onChange={event => updateField('costLabel', event.target.value)} />
            </label>
            <label className="field">
              Reconfirmation deadline (Manila time)
              <input
                type="datetime-local"
                required
                value={form.reconfirmDeadline}
                onChange={event => updateField('reconfirmDeadline', event.target.value)}
              />
            </label>
            <label className="field">
              Capacity selection mode
              <select aria-label="Capacity selection mode" value={selectionMode} onChange={event => setSelectionMode(event.target.value as SelectionMode)}>
                <option value="exact">Exact selection</option>
                <option value="newest_in_pool">Newest in selected pool</option>
              </select>
            </label>
          </div>
          <p className="muted">
            {selectionMode === 'exact'
              ? 'Exact selection cancels only the registrations you select, and requires exactly the number of seats that must be removed.'
              : 'Newest in selected pool cancels only within the registrations you select; the server chooses the required number from that pool by reverse confirmation/admission order.'}
          </p>

          <section className="panel stack" aria-label="Review the proposed event">
            <h3>Review the merged event details</h3>
            <p className="muted">This preview combines your edits with unchanged event details. Only changed material fields are sent.</p>
            <p><strong>Starts:</strong> {manilaDate(form.startsAt)}</p>
            <p><strong>Ends:</strong> {manilaDate(form.endsAt)}</p>
            <p><strong>Venue:</strong> {form.venueName.trim() || 'Not set'}</p>
            <p><strong>Address:</strong> {form.venueAddress.trim() || 'Not set'}</p>
            <p><strong>Capacity:</strong> {form.capacity.trim() || 'Enter a positive whole number'}</p>
            <p><strong>Cost:</strong> {form.costLabel.trim() || 'Not set'}</p>
            <p><strong>Reconfirmation deadline:</strong> {manilaDate(form.reconfirmDeadline)}</p>
          </section>

          {capacityReduced && (
            <section className="panel stack" aria-label="Choose registrations affected by capacity reduction">
              <h3>Capacity reduction</h3>
              <Feedback loading={occupied.loading} error={occupied.error} onRetry={occupied.reload}>
                {occupied.data !== null && (
                  <>
                    <p>
                      {seatHolders.length} occupied seats, including pending reviews and reconfirmations. New capacity: {proposedCapacity}. {' '}
                      {seatsToRemove} registration{seatsToRemove === 1 ? '' : 's'} must be selected.
                    </p>
                    {seatsToRemove > 0 && (
                      <div className="feed">
                        {seatHolders.map(item => {
                          const registration = item.registration;
                          const selected = selectedCurrentIds.includes(registration.id);
                          return (
                            <label className="event-card actions" key={registration.id}>
                              <input
                                type="checkbox"
                                style={{width: 'auto'}}
                                checked={selected}
                                onChange={() => toggleRegistration(registration.id)}
                              />
                              <span>Registrant {registration.id.slice(0, 8)}</span>
                              <span className={`status-chip ${registration.status}`}>{registration.status.replace(/_/g, ' ')}</span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </>
                )}
              </Feedback>
            </section>
          )}

          {error && <p className="error" role="alert">{error}</p>}
          {message && <p role="status">{message}</p>}
          <div className="actions">
            <button className="button" type="submit" disabled={saving}>
              {saving ? 'Submitting…' : 'Submit material change'}
            </button>
          </div>
        </form>
      )}
    </details>
  );
}
