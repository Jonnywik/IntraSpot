"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { mediaApiPath } from "./media-url";

export type MediaImageProps = {
  mediaUrl: string;
  alt: string;
  token?: string | null;
  className?: string;
};

type ImageState =
  | { mediaUrl: string; token?: string | null; src: string }
  | { mediaUrl: string; token?: string | null; error: true };

export function MediaImage({ mediaUrl, alt, token, className }: MediaImageProps) {
  const t = useT();
  const [image, setImage] = useState<ImageState | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const path = mediaApiPath(mediaUrl);
  const matchingImage = image?.mediaUrl === mediaUrl && image.token === token ? image : null;

  useEffect(() => {
    if (!path) return;

    let active = true;
    const controller = new AbortController();

    void api<Blob>(path, { token, responseType: "blob", signal: controller.signal })
      .then((blob) => {
        if (!active || controller.signal.aborted) return;
        const objectUrl = URL.createObjectURL(blob);
        objectUrlRef.current = objectUrl;
        setImage({ mediaUrl, token, src: objectUrl });
      })
      .catch((error: unknown) => {
        if (!active || controller.signal.aborted || (error instanceof Error && error.name === "AbortError")) return;
        setImage({ mediaUrl, token, error: true });
      });

    return () => {
      active = false;
      controller.abort();
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [mediaUrl, path, token]);

  if (matchingImage && "src" in matchingImage) {
    return <Image src={matchingImage.src} alt={alt} className={className} width={1000} height={350} unoptimized />;
  }

  if (!path || (matchingImage && "error" in matchingImage)) {
    return (
      <span
        className={className}
        style={{ display: "block" }}
        role={alt ? "img" : undefined}
        aria-label={alt ? t("Image unavailable: {alt}", { alt }) : undefined}
        aria-hidden={alt ? undefined : true}
      />
    );
  }

  return (
    <span
      className={className}
      style={{ display: "block" }}
      role={alt ? "status" : undefined}
      aria-label={alt ? t("Loading image…") : undefined}
      aria-busy={alt ? true : undefined}
      aria-hidden={alt ? undefined : true}
    />
  );
}
