import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { offerApi, type CompanyOffer, type OfferFile } from "@/entities/offer";
import { Alert, Badge, Button, Card, CardBody, CardHeader, CardTitle, Spinner } from "@/shared/ui";

/** Server-side cap (FR-M2) — mirrored so the UI can stop before a 422. */
const MAX_PHOTOS = 8;

/** Server-side per-file cap for offer files. */
const MAX_PHOTO_BYTES = 10 * 1024 * 1024;

/** Longest edge after client-side downscale, to keep uploads small. */
const MAX_EDGE_PX = 1600;

const ACCEPTED = ["image/jpeg", "image/png"];

/**
 * Shrink an oversized picture in the browser before uploading. Phone cameras
 * produce 4–8 MB frames that would hit the server cap for no visual gain; there is
 * deliberately no server-side resize at this stage (TZ block F).
 *
 * Returns the original file when it is already small enough or when anything in the
 * canvas path fails — the server remains the authority on size and type.
 */
async function downscale(file: File): Promise<File> {
  if (!ACCEPTED.includes(file.type)) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const longest = Math.max(bitmap.width, bitmap.height);
    if (longest <= MAX_EDGE_PX && file.size <= MAX_PHOTO_BYTES) {
      bitmap.close();
      return file;
    }
    const scale = Math.min(1, MAX_EDGE_PX / longest);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, file.type, 0.85);
    });
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], file.name, { type: file.type });
  } catch {
    return file;
  }
}

/**
 * One photo tile. The bytes come from the owner-scoped endpoint via a Blob (the
 * access token is memory-only, so `<img src>` would go out unauthenticated), which
 * is also the only way to preview photos on a not-yet-approved offer.
 */
function PhotoTile({
  companyId,
  offerId,
  file,
  isCover,
  disabled,
  onRemove,
}: {
  companyId: number;
  offerId: number;
  file: OfferFile;
  isCover: boolean;
  disabled: boolean;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    void offerApi
      .fileBlob(companyId, offerId, file.id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        /* tile falls back to the placeholder */
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [companyId, offerId, file.id]);

  return (
    <div className="relative overflow-hidden rounded-md border border-border bg-surface-inset">
      <div className="aspect-square w-full">
        {url ? (
          <img src={url} alt={file.file_name} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <Spinner />
          </div>
        )}
      </div>
      {isCover ? (
        <Badge tone="brand" className="absolute left-1.5 top-1.5">
          {t("offers.photos.cover")}
        </Badge>
      ) : null}
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label={t("offers.photos.remove")}
        className="absolute right-1.5 top-1.5 rounded-full bg-overlay p-1.5 text-text transition-colors hover:bg-danger hover:text-danger-fg disabled:pointer-events-none disabled:opacity-50"
      >
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <path
            d="M3.5 3.5l7 7M10.5 3.5l-7 7"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </div>
  );
}

interface OfferPhotosProps {
  companyId: number;
  offer: CompanyOffer;
  /** Called with the offer returned by the server after every photo change. */
  onChanged: (offer: CompanyOffer) => void;
}

/**
 * Photo section of the offer form (FR-M2): up to 8 JPEG/PNG, previews, removal,
 * first photo is the cover.
 *
 * Only rendered for an offer that already exists — photos attach to an offer id, so
 * on create the form saves the draft first and the section appears after.
 */
export function OfferPhotos({ companyId, offer, onChanged }: OfferPhotosProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const photos = offer.files.filter((f) => f.kind === "image");
  const remaining = MAX_PHOTOS - photos.length;
  const wasLive = offer.status === "approved";

  async function addFiles(selected: FileList | null): Promise<void> {
    if (!selected || selected.length === 0) return;
    setError(null);

    const chosen = Array.from(selected).slice(0, Math.max(0, remaining));
    if (chosen.length < selected.length) setError(t("offers.photos.tooMany", { max: MAX_PHOTOS }));

    setBusy(true);
    try {
      // Sequential: upload order is display order, and the first photo becomes the
      // cover — parallel requests would race for that slot.
      for (const raw of chosen) {
        if (!ACCEPTED.includes(raw.type)) {
          setError(t("offers.photos.badType"));
          continue;
        }
        const prepared = await downscale(raw);
        if (prepared.size > MAX_PHOTO_BYTES) {
          setError(t("offers.photos.tooLarge"));
          continue;
        }
        onChanged(await offerApi.uploadFile(companyId, offer.id, prepared));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function remove(fileId: number): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      onChanged(await offerApi.deleteFile(companyId, offer.id, fileId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("offers.photos.title")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="text-sm text-text-muted">
          {t("offers.photos.hint", { max: MAX_PHOTOS })}
        </p>

        {wasLive ? <Alert tone="warning" title={t("offers.photos.requeueWarning")} /> : null}
        {error ? <Alert tone="danger" title={error} /> : null}

        {photos.length > 0 ? (
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            {photos.map((file, index) => (
              <PhotoTile
                key={file.id}
                companyId={companyId}
                offerId={offer.id}
                file={file}
                isCover={index === 0}
                disabled={busy}
                onRemove={() => void remove(file.id)}
              />
            ))}
          </div>
        ) : null}

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(",")}
          multiple
          className="hidden"
          onChange={(e) => void addFiles(e.target.files)}
        />
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            loading={busy}
            disabled={remaining <= 0}
            onClick={() => inputRef.current?.click()}
          >
            {t("offers.photos.add")}
          </Button>
          <span className="num text-xs text-text-subtle">
            {photos.length} / {MAX_PHOTOS}
          </span>
        </div>
      </CardBody>
    </Card>
  );
}
