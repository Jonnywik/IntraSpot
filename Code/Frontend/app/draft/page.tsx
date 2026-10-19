"use client";

import { Suspense } from "react";
import { DraftEditor } from "@/features/events/DraftEditor";
import { useT } from "@/lib/i18n";

export default function DraftPage() {
  const t = useT();
  return (
    <>
      <div className="desktop-only">
        <Suspense fallback={<p className="panel muted" role="status">{t('Loading your event workspace…')}</p>}>
          <DraftEditor />
        </Suspense>
      </div>
      <p className="panel desktop-required" role="note">
        {t('Event draft management is available on desktop. Open this page on a wider screen to create or edit a draft.')}
      </p>
    </>
  );
}
