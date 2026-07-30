import { useState } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { ManufacturerListCard, useManufacturers } from "@/entities/manufacturer";
import {
  Button,
  EmptyState,
  ErrorView,
  FactoryIcon,
  Input,
  PageHeader,
  Skeleton,
} from "@/shared/ui";

const PAGE_SIZE = 24;

/** `/manufacturers` — verified factories directory (`docs/new-design/manufacturer_flow.jpeg`). */
export function ManufacturersPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);

  const query = useManufacturers(q.trim(), offset, PAGE_SIZE);
  const items = query.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader title={t("manufacturers.title")} subtitle={t("manufacturers.subtitle")} />

      <Input
        placeholder={t("manufacturers.search")}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOffset(0);
        }}
        aria-label={t("manufacturers.search")}
      />

      {query.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </div>
      ) : query.isError ? (
        <ErrorView
          title={t("errors.loadFailed")}
          retryLabel={t("common.retry")}
          onRetry={() => void query.refetch()}
        />
      ) : items.length > 0 ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((m) => (
              <ManufacturerListCard
                key={m.id}
                manufacturer={m}
                onOpen={() => navigate(`/manufacturers/${m.id}`)}
              />
            ))}
          </div>
          <div className="flex items-center justify-between">
            <Button
              variant="secondary"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              {t("common.prev")}
            </Button>
            <Button
              variant="secondary"
              disabled={items.length < PAGE_SIZE}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              {t("common.next")}
            </Button>
          </div>
        </>
      ) : (
        <EmptyState
          icon={<FactoryIcon size={28} />}
          title={t("manufacturers.empty")}
          description={t("manufacturers.emptyBody")}
        />
      )}
    </div>
  );
}
