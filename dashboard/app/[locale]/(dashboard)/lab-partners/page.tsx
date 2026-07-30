"use client";

/**
 * Partner laboratories (/lab-partners) — R5 / P6 T5.2.
 *
 * The directory of labs we send other people's material to. Analysts READ it
 * (they pick a partner when assigning an order); writing is admin-only, because
 * adding a laboratory here is a decision about who gets handed a customer's
 * product.
 *
 * There is no delete. A finished order points at the lab that ran it, and that
 * answer has to survive the partnership ending — so a lab is retired instead.
 *
 * Backed by /api/v1/admin/lab-partners.
 */

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

interface LabPartner {
  id: number;
  name: string;
  contacts: Record<string, string>;
  company_id: number | null;
  note: string | null;
  is_active: boolean;
  created_at: string;
}

interface PartnerForm {
  name: string;
  phone: string;
  email: string;
  address: string;
  contact_name: string;
  note: string;
}

const EMPTY: PartnerForm = {
  name: "",
  phone: "",
  email: "",
  address: "",
  contact_name: "",
  note: "",
};

export default function LabPartnersPage() {
  const t = useTranslations("labPartners");
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === "admin";

  const [form, setForm] = useState<PartnerForm>(EMPTY);
  const [editing, setEditing] = useState<number | null>(null);

  const listQuery = useQuery({
    queryKey: ["admin-lab-partners"],
    queryFn: () => apiFetch<LabPartner[]>("/admin/lab-partners"),
  });

  function reset(): void {
    setForm(EMPTY);
    setEditing(null);
    void queryClient.invalidateQueries({ queryKey: ["admin-lab-partners"] });
  }

  const save = useMutation({
    mutationFn: () => {
      const body = JSON.stringify({
        name: form.name.trim(),
        // Only the fields that were filled in: an empty string in the contacts
        // blob reads as "we have their email and it is blank".
        contacts: Object.fromEntries(
          (
            [
              ["phone", form.phone],
              ["email", form.email],
              ["address", form.address],
              ["contact_name", form.contact_name],
            ] as const
          )
            .filter(([, value]) => value.trim() !== "")
            .map(([key, value]) => [key, value.trim()]),
        ),
        note: form.note.trim() || null,
      });
      return editing == null
        ? apiFetch<LabPartner>("/admin/lab-partners", { method: "POST", body })
        : apiFetch<LabPartner>(`/admin/lab-partners/${editing}`, { method: "PATCH", body });
    },
    onSuccess: reset,
  });

  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      apiFetch<LabPartner>(
        `/admin/lab-partners/${id}/${active ? "activate" : "deactivate"}`,
        { method: "POST" },
      ),
    onSuccess: reset,
  });

  function startEdit(partner: LabPartner): void {
    setEditing(partner.id);
    setForm({
      name: partner.name,
      phone: partner.contacts.phone ?? "",
      email: partner.contacts.email ?? "",
      address: partner.contacts.address ?? "",
      contact_name: partner.contacts.contact_name ?? "",
      note: partner.note ?? "",
    });
  }

  return (
    <div className="p-6">
      <div className="mb-4 flex items-center gap-2">
        <Building2 className="h-5 w-5 text-foreground-muted" />
        <h1 className="text-xl font-semibold">{t("title")}</h1>
      </div>
      <p className="mb-4 text-sm text-foreground-muted">{t("subtitle")}</p>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-background-secondary text-left text-xs text-foreground-muted">
              <tr>
                <th className="px-3 py-2">{t("colName")}</th>
                <th className="px-3 py-2">{t("colContacts")}</th>
                <th className="px-3 py-2">{t("colState")}</th>
              </tr>
            </thead>
            <tbody>
              {listQuery.data?.map((partner) => (
                <tr key={partner.id} className="border-t border-border">
                  <td className="px-3 py-2">
                    <button
                      onClick={() => startEdit(partner)}
                      disabled={!isAdmin}
                      className="text-left hover:text-accent disabled:cursor-default disabled:hover:text-foreground"
                    >
                      {partner.name}
                    </button>
                    {partner.note ? (
                      <p className="text-xs text-foreground-muted">{partner.note}</p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 text-xs text-foreground-muted">
                    {[partner.contacts.contact_name, partner.contacts.phone, partner.contacts.email]
                      .filter(Boolean)
                      .join(" · ") || "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                        partner.is_active
                          ? "bg-green-100 text-green-800"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {t(partner.is_active ? "active" : "retired")}
                    </span>
                    {isAdmin ? (
                      <button
                        onClick={() =>
                          toggle.mutate({ id: partner.id, active: !partner.is_active })
                        }
                        className="ml-2 text-xs text-foreground-muted underline-offset-2 hover:underline"
                      >
                        {t(partner.is_active ? "retire" : "restore")}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
              {listQuery.data?.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-6 text-center text-foreground-muted">
                    {t("empty")}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {isAdmin ? (
          <div className="space-y-3 rounded-lg border border-border p-4">
            <h2 className="font-medium">{editing == null ? t("addTitle") : t("editTitle")}</h2>
            {(
              [
                ["name", t("fieldName")],
                ["contact_name", t("fieldContactName")],
                ["phone", t("fieldPhone")],
                ["email", t("fieldEmail")],
                ["address", t("fieldAddress")],
                ["note", t("fieldNote")],
              ] as const
            ).map(([key, label]) => (
              <div key={key} className="space-y-1">
                <label className="text-xs text-foreground-muted">{label}</label>
                <input
                  value={form[key]}
                  onChange={(e) => setForm((prev) => ({ ...prev, [key]: e.target.value }))}
                  className="w-full rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
                />
              </div>
            ))}
            <div className="flex gap-2">
              <button
                disabled={!form.name.trim() || save.isPending}
                onClick={() => save.mutate()}
                className="rounded border border-border bg-background-tertiary px-3 py-1.5 text-xs font-medium disabled:opacity-50"
              >
                {t("save")}
              </button>
              {editing != null ? (
                <button
                  onClick={reset}
                  className="rounded border border-border px-3 py-1.5 text-xs font-medium"
                >
                  {t("cancel")}
                </button>
              ) : null}
            </div>
            {save.error ? (
              <p className="text-xs text-red-500">{(save.error as Error).message}</p>
            ) : null}
          </div>
        ) : (
          <div className="rounded-lg border border-border p-4">
            <p className="text-sm text-foreground-muted">{t("adminOnly")}</p>
          </div>
        )}
      </div>
    </div>
  );
}
