import { createNavigation } from "next-intl/navigation";

import { routing } from "./routing";

/**
 * Locale-aware navigation primitives. Use these instead of next/link and
 * next/navigation throughout the app so every link/redirect keeps the active
 * /[locale]/ prefix. usePathname() here returns the path WITHOUT the locale
 * prefix (handy for active-state checks).
 */
export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation(routing);
