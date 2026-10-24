import { useState } from "react";

import { type Photo as PhotoItem, photoSrc, photoSrcSet } from "../lib/photos";

/**
 * Responsive, lazy-loaded food photo. If the file is missing (photos aren't in Git) or fails to load,
 * it swaps to the matching illustration instead of showing a broken image.
 */
export function Photo({
  photo,
  sizes,
  className = "",
  alt = photo.alt,
  priority = false,
}: {
  photo: PhotoItem;
  /** How wide the image is drawn, e.g. "(min-width: 1024px) 33vw, 100vw". Lets the browser pick a file. */
  sizes: string;
  className?: string;
  alt?: string;
  /** Above-the-fold images load immediately; everything else waits until it scrolls near. */
  priority?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <img src={photo.fallback} alt={alt} className={`h-full w-full object-cover ${className}`} />;
  }
  return (
    <img
      src={photoSrc(photo)}
      srcSet={photoSrcSet(photo)}
      sizes={sizes}
      alt={alt}
      loading={priority ? "eager" : "lazy"}
      fetchPriority={priority ? "high" : "auto"}
      decoding="async"
      onError={() => setFailed(true)}
      className={`h-full w-full object-cover ${className}`}
    />
  );
}
