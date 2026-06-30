"use client";

/**
 * Admin Products page (/admin/products)
 *
 * Admin-only manager for the polymer product catalog (GET/POST/PATCH /admin/products).
 * Adding a product here makes it appear in the Telegram Web App selectors (which read
 * /webapp/reference/products) without a client release.
 *
 * Non-admin: redirects to dashboard home (UI gate; backend require_admin is the boundary).
 * No hardcoded hex.
 */

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "@/i18n/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/hooks/useAuth";
import { ApiError, apiFetch } from "@/lib/api";

interface Product {
  id: number;
  code: string;
  name_ru: string;
  name_uz: string | null;
  category: string;
  sort_order: number;
  is_active: boolean;
}

// ─── Add-product form ──────────────────────────────────────────────────────────

function AddProductForm() {
  const t = useTranslations("adminProducts");
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [nameRu, setNameRu] = useState("");
  const [nameUz, setNameUz] = useState("");
  const [sortOrder, setSortOrder] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      apiFetch<Product>("/admin/products", {
        method: "POST",
        body: JSON.stringify({
          code: code.trim(),
          name_ru: nameRu.trim(),
          name_uz: nameUz.trim() || null,
          sort_order: sortOrder ? Number(sortOrder) : 0,
        }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-products"] });
      setCode("");
      setNameRu("");
      setNameUz("");
      setSortOrder("");
      setError(null);
      setOpen(false);
    },
    onError: (e) => {
      setError(e instanceof ApiError && e.status === 409 ? t("duplicateCode") : t("createError"));
    },
  });

  const canSubmit = code.trim() !== "" && nameRu.trim() !== "" && !mutation.isPending;
  const inputCls =
    "w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted focus:outline-none focus:ring-2 focus:ring-accent";

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 self-start rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-foreground hover:opacity-90"
      >
        <Plus size={16} aria-hidden="true" /> {t("add")}
      </button>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) mutation.mutate();
      }}
      className="flex flex-col gap-3 rounded-lg border border-border bg-background-secondary p-4"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs font-semibold text-foreground-muted">
          {t("form.code")}
          <input className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} placeholder={t("form.codePlaceholder")} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-foreground-muted">
          {t("form.sortOrder")}
          <input className={inputCls} type="number" min="0" value={sortOrder} onChange={(e) => setSortOrder(e.target.value)} placeholder="0" />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-foreground-muted">
          {t("form.nameRu")}
          <input className={inputCls} value={nameRu} onChange={(e) => setNameRu(e.target.value)} placeholder={t("form.nameRuPlaceholder")} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-semibold text-foreground-muted">
          {t("form.nameUz")}
          <input className={inputCls} value={nameUz} onChange={(e) => setNameUz(e.target.value)} />
        </label>
      </div>

      {error && <p className="text-sm text-urgency-high">{error}</p>}

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-md bg-accent px-3 py-2 text-sm font-semibold text-accent-foreground hover:opacity-90 disabled:opacity-50"
        >
          {mutation.isPending ? t("saving") : t("form.submit")}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setError(null);
          }}
          className="rounded-md border border-border px-3 py-2 text-sm text-foreground-muted hover:text-foreground"
        >
          {t("form.cancel")}
        </button>
      </div>
    </form>
  );
}

// ─── Products table ─────────────────────────────────────────────────────────

function ProductsTable() {
  const t = useTranslations("adminProducts");
  const qc = useQueryClient();
  const { data: products = [], isLoading, error } = useQuery<Product[]>({
    queryKey: ["admin-products"],
    queryFn: () => apiFetch<Product[]>("/admin/products"),
  });

  const toggle = useMutation({
    mutationFn: (p: Product) =>
      apiFetch<Product>(`/admin/products/${p.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: !p.is_active }),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["admin-products"] }),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-12 rounded-lg bg-background-tertiary animate-pulse" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-urgency-high/30 bg-urgency-high/10 p-4 text-sm text-urgency-high">
        {t("loadError")}
      </div>
    );
  }

  if (products.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <Boxes size={32} className="text-foreground-muted" aria-hidden="true" />
        <p className="text-sm text-foreground-muted">{t("empty")}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-background-tertiary">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">{t("table.code")}</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">{t("table.nameRu")}</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">{t("table.nameUz")}</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">{t("table.sortOrder")}</th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">{t("table.status")}</th>
            <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-foreground-muted">{t("table.actions")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {products.map((p) => (
            <tr key={p.id} className="bg-background-secondary hover:bg-background-tertiary transition-colors">
              <td className="px-4 py-3 font-medium text-foreground">{p.code}</td>
              <td className="px-4 py-3 text-foreground">{p.name_ru}</td>
              <td className="px-4 py-3 text-foreground-muted">{p.name_uz ?? "—"}</td>
              <td className="px-4 py-3 text-foreground-muted">{p.sort_order}</td>
              <td className="px-4 py-3">
                {p.is_active ? (
                  <span className="inline-flex items-center rounded-full border border-accent/30 px-2 py-0.5 text-xs font-semibold text-accent">
                    {t("statusActive")}
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded-full border border-border px-2 py-0.5 text-xs font-semibold text-foreground-muted">
                    {t("statusInactive")}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-right">
                <button
                  type="button"
                  onClick={() => toggle.mutate(p)}
                  disabled={toggle.isPending}
                  className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground-muted hover:text-foreground disabled:opacity-50"
                >
                  {p.is_active ? t("hide") : t("show")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

function AdminProductsPageContent() {
  const t = useTranslations("adminProducts");
  const router = useRouter();
  const { role, isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated && role !== "admin") {
      router.replace("/");
    }
  }, [isAuthenticated, role, router]);

  if (role && role !== "admin") {
    return null;
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <Boxes size={24} className="text-foreground-muted" aria-hidden="true" />
        <div>
          <h1 className="text-xl font-semibold text-foreground">{t("pageTitle")}</h1>
          <p className="mt-0.5 text-sm text-foreground-muted">{t("pageSubtitle")}</p>
        </div>
      </div>

      <AddProductForm />
      <ProductsTable />
    </div>
  );
}

export default function AdminProductsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-4 p-6">
          <div className="h-8 w-40 rounded bg-background-tertiary animate-pulse" />
          <div className="h-12 rounded bg-background-tertiary animate-pulse" />
        </div>
      }
    >
      <AdminProductsPageContent />
    </Suspense>
  );
}
