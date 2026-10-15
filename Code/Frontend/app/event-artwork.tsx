"use client";

import Image from "next/image";
import { useState } from "react";
import type { PrivateEvent, PublicEvent } from "@/lib/types";

type ArtworkEvent =
  | Pick<PublicEvent, "banner_key" | "title">
  | Pick<PrivateEvent, "banner_key" | "title">;

const colors = {
  heritage: { background: "#efe3cf", accent: "#8a5d37", soft: "#d1ad7d" },
  design: { background: "#eee3dc", accent: "#8d3340", soft: "#d7a39a" },
  garden: { background: "#e2eadf", accent: "#3e694f", soft: "#a8c29a" },
  music: { background: "#e3e7f0", accent: "#3f5283", soft: "#a8b6d2" },
  event: { background: "#eee8dc", accent: "#645d53", soft: "#c9bca6" },
};

export function EventArtwork({ event }: { event: ArtworkEvent }) {
  const [heritageImageFailed, setHeritageImageFailed] = useState(false);
  const key = event.banner_key ?? "event";
  const title = event.title || "event";

  if (key === "heritage" && !heritageImageFailed) {
    return (
      <div className="artwork-crop"><Image
        className="event-art"
        src="/artwork/heritage.jpg"
        alt={"Local heritage fixture artwork for " + title}
        width={1000}
        height={350}
        unoptimized
        onError={() => setHeritageImageFailed(true)}
      /></div>
    );
  }

  const palette = colors[key];
  const label = key === "event" ? "EVENT" : key.toUpperCase();

  return (
    <div
      className="event-art"
      role="img"
      aria-label={"Local " + key + " fixture illustration for " + title}
    >
      <svg viewBox="0 0 1000 350" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
        <rect width="1000" height="350" fill={palette.background} />
        <circle cx="830" cy="82" r="118" fill={palette.soft} opacity="0.5" />
        {key === "design" && (
          <g>
            <rect x="96" y="55" width="250" height="206" rx="14" fill="#fffaf2" />
            <rect x="128" y="84" width="74" height="74" rx="8" fill="#b51e2b" />
            <rect x="218" y="84" width="96" height="34" rx="6" fill="#123575" />
            <rect x="218" y="130" width="96" height="28" rx="6" fill={palette.soft} />
            <path d="M128 184h186M128 207h132M128 230h158" stroke={palette.accent} strokeWidth="8" strokeLinecap="round" opacity="0.55" />
            <path d="m445 235 158-158 42 42-158 158-68 26z" fill={palette.accent} />
            <path d="m603 77 28-28a22 22 0 0 1 31 0l11 11a22 22 0 0 1 0 31l-28 28z" fill="#d9b15f" />
          </g>
        )}
        {key === "garden" && (
          <g>
            <path d="M0 252c160-67 280-11 410 14s257-51 590-20v104H0z" fill="#b5c9a7" />
            <path d="M500 252V116" stroke={palette.accent} strokeWidth="13" strokeLinecap="round" />
            <path d="M494 180c-91 6-113-48-115-93 67 3 108 32 115 93Zm14-35c70-3 105-47 114-88-73-3-109 30-114 88Z" fill="#71936d" />
            <path d="M420 252c-53-48-91-50-128-46 14 48 60 78 128 46Zm159 0c49-44 85-49 123-44-13 47-57 77-123 44Z" fill="#91ad82" />
            <circle cx="190" cy="92" r="38" fill="#d7aa53" />
            <path d="M105 242h80m-116 34h88m635-24h80m-27 34h58" stroke={palette.accent} strokeWidth="8" strokeLinecap="round" opacity="0.45" />
          </g>
        )}
        {key === "music" && (
          <g fill={palette.accent}>
            <path d="M217 208V94l145-28v124h-20V91l-105 20v97z" />
            <ellipse cx="190" cy="217" rx="39" ry="26" transform="rotate(-18 190 217)" />
            <ellipse cx="324" cy="188" rx="39" ry="26" transform="rotate(-18 324 188)" />
            <path d="M594 242V96h28v146c0 36-26 58-62 58-32 0-54-18-54-45 0-32 32-50 88-48Zm0 24v-37c-37-2-59 7-59 25 0 11 11 19 27 19 14 0 25-2 32-7Z" />
            <path d="m748 93 12 28 30 3-23 18 7 29-26-16-26 16 7-29-23-18 30-3z" />
            <circle cx="844" cy="223" r="15" />
          </g>
        )}
        {(key === "heritage" || key === "event") && (
          <g>
            <path d="M120 254h430v28H120z" fill={palette.accent} opacity="0.78" />
            <path d="M154 246V152a182 182 0 0 1 364 0v94h-52v-92a130 130 0 0 0-260 0v92z" fill={palette.accent} />
            <path d="M275 244v-72a60 60 0 0 1 120 0v72" fill={palette.soft} />
            <path d="M603 267h224" stroke={palette.accent} strokeWidth="10" strokeLinecap="round" opacity="0.5" />
          </g>
        )}
        <text x="74" y="321" fill={palette.accent} fontFamily="Arial, sans-serif" fontSize="22" fontWeight="700" letterSpacing="4">
          {label} · LOCAL FIXTURE ILLUSTRATION
        </text>
      </svg>
    </div>
  );
}
