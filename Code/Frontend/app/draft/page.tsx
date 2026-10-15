"use client";

import { Suspense } from "react";
import { DraftEditor } from "@/features/events/DraftEditor";

export default function DraftPage() {
  return (
    <>
      <div className="desktop-only">
        <Suspense fallback={<p className="panel muted" role="status">Loading event editor…</p>}>
          <DraftEditor />
        </Suspense>
      </div>
      <p className="panel desktop-required" role="status">
        Event management is available on a desktop browser. Use a larger screen to create, edit, or publish event drafts.
      </p>
    </>
  );
}
