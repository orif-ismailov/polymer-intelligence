import { useEffect, useRef, useState } from "react";

import { useTranslation } from "react-i18next";

import { offerApi, type OfferFile } from "@/entities/offer";
import { Badge, CloseIcon, ImageIcon, PlusIcon, Spinner } from "@/shared/ui";

import { MAX_PHOTOS, PHOTO_MIME } from "../model/constants";
import { useOfferDraft } from "../model/draftStore";

/**
 * A photo already on the server.
 *
 * The bytes come through the owner-scoped endpoint as a Blob rather than a bare
 * `<img src>`: the access token lives in memory only, so an img request goes out
 * unauthenticated and 401s — and this is exactly the draft-preview case the
 * public catalog URL refuses to serve.
 */
function ServerTile({
  companyId,
  offerId,
  file,
  isCover,
  onRemove,
}: {
  companyId: number;
  offerId: number;
  file: OfferFile;
  isCover: boolean;
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
        /* the tile falls back to the placeholder */
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [companyId, offerId, file.id]);

  return (
    <Tile
      src={url}
      alt={file.file_name}
      isCover={isCover}
      removeLabel={t("offers.photos.remove")}
      onRemove={onRemove}
    />
  );
}

function Tile({
  src,
  alt,
  isCover,
  removeLabel,
  onRemove,
}: {
  src: string | null;
  alt: string;
  isCover: boolean;
  removeLabel: string;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="relative overflow-hidden rounded-md border border-border bg-surface-inset">
      <div className="aspect-square w-full">
        {src ? (
          <img src={src} alt={alt} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-text-subtle">
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
        aria-label={removeLabel}
        className="absolute right-1.5 top-1.5 rounded-full bg-overlay p-1.5 text-text transition-colors hover:bg-danger hover:text-danger-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <CloseIcon size={12} />
      </button>
    </div>
  );
}

interface PhotoGridProps {
  companyId: number;
  onError: (message: string | null) => void;
}

/**
 * «Фото товара» — the thumbnail row with the ＋ tile at its end.
 *
 * Nothing uploads here. On a new offer there is no id for a file to hang off
 * yet, and the mockup asks for photos on sheet 1 of 7 — so both new and staged
 * pictures wait in the draft and are flushed when the offer is published
 * (`useSubmitOffer`). Pictures already on the server are shown alongside and
 * removed the same way: queued, then applied on submit.
 */
export function PhotoGrid({ companyId, onError }: PhotoGridProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const offerId = useOfferDraft((s) => s.offerId);
  const photos = useOfferDraft((s) => s.photos);
  const serverFiles = useOfferDraft((s) => s.serverFiles);
  const addPhotos = useOfferDraft((s) => s.addPhotos);
  const removePhoto = useOfferDraft((s) => s.removePhoto);
  const removeServerFile = useOfferDraft((s) => s.removeServerFile);

  const serverPhotos = serverFiles.filter((f) => f.kind === "image");
  const count = serverPhotos.length + photos.length;
  const remaining = MAX_PHOTOS - count;

  function handleFiles(list: FileList | null): void {
    const chosen = Array.from(list ?? []);
    if (chosen.length === 0) return;
    onError(null);

    const accepted = chosen.filter((f) => PHOTO_MIME.includes(f.type));
    if (accepted.length < chosen.length) onError(t("offers.photos.badType"));

    const fitting = accepted.slice(0, Math.max(0, remaining));
    if (fitting.length < accepted.length) {
      onError(t("offers.photos.tooMany", { max: MAX_PHOTOS }));
    }
    if (fitting.length > 0) addPhotos(fitting);
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept={PHOTO_MIME.join(",")}
        multiple
        className="sr-only"
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />

      <div className="grid grid-cols-4 gap-2">
        {serverPhotos.map((file, index) => (
          <ServerTile
            key={`server-${file.id}`}
            companyId={companyId}
            offerId={offerId as number}
            file={file}
            isCover={index === 0}
            onRemove={() => removeServerFile(file.id)}
          />
        ))}
        {photos.map((entry, index) => (
          <Tile
            key={`staged-${index}-${entry.file.name}`}
            src={entry.previewUrl}
            alt={entry.file.name}
            isCover={serverPhotos.length === 0 && index === 0}
            removeLabel={t("offers.photos.remove")}
            onRemove={() => removePhoto(index)}
          />
        ))}

        {remaining > 0 ? (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            aria-label={t("offers.photos.add")}
            className="flex aspect-square w-full flex-col items-center justify-center gap-1 rounded-md border border-dashed border-border-strong text-text-subtle transition-colors hover:border-brand-line hover:bg-brand-soft hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            data-testid="offer-wizard-add-photo"
          >
            {count === 0 ? <ImageIcon size={20} /> : <PlusIcon size={20} />}
          </button>
        ) : null}
      </div>

      <p className="num mt-2 text-xs text-text-subtle">
        {count} / {MAX_PHOTOS}
      </p>
    </div>
  );
}
