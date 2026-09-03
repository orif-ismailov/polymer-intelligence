import { redirect } from "@/i18n/navigation";
import { getLocale } from "next-intl/server";

/**
 * `/admin/settings` — kept as a redirect, not deleted.
 *
 * The settings used to live here as one scroll of thirty rows; they are now one
 * page per area under `/admin/settings/<module>`, listed in the sidebar's
 * Настройки проекта group. This route still exists because links to it do:
 * browser history, a bookmark, a message to a colleague. A 404 would read as
 * "the settings were removed", which is the opposite of what happened.
 *
 * It lands on `news` rather than on an index of the areas — with the seven areas
 * already in the sidebar, an index page would be a second menu for the same
 * seven things, one click further from any of them.
 */
export default async function AdminSettingsIndex() {
  redirect({ href: "/admin/settings/news", locale: await getLocale() });
}
