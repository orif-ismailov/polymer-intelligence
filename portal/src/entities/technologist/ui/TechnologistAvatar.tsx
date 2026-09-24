import { cn } from "@/shared/lib";
import { UsersIcon } from "@/shared/ui";

/** Portrait or a neutral glyph — one look for every place an expert appears. */
export function TechnologistAvatar({
  photoUrl,
  size = "md",
  className,
}: {
  photoUrl: string | null;
  size?: "md" | "lg";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-surface-inset text-text-subtle",
        size === "lg" ? "h-20 w-20" : "h-12 w-12",
        className,
      )}
    >
      {photoUrl ? (
        <img src={photoUrl} alt="" loading="lazy" className="h-full w-full object-cover" />
      ) : (
        <UsersIcon size={size === "lg" ? 32 : 20} />
      )}
    </span>
  );
}
