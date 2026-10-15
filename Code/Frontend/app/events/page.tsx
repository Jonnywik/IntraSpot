"use client";

import { Suspense } from "react";
import { EventDetail } from "@/features/events/EventDetail";

export default function EventsPage() {
  return (
    <Suspense fallback={<p className="panel muted" role="status">Loading event details…</p>}>
      <EventDetail />
    </Suspense>
  );
}
