import { createBrowserRouter, Navigate } from "react-router-dom";

import { CompaniesPage } from "@/pages/companies";
import { CompanyCreatePage } from "@/pages/company-create";
import { CompanyViewPage } from "@/pages/company-view";
import { HomePage } from "@/pages/home";
import { LoginPage } from "@/pages/login";
import { MarketOfferPage, MarketPage } from "@/pages/market";
import { OfferEditPage } from "@/pages/offer-edit";
import { OffersPage } from "@/pages/offers";
import { OtpPage } from "@/pages/otp";
import { SettingsPage } from "@/pages/settings";
import { VerificationStatusPage } from "@/pages/verification-status";
import { AppShell } from "@/widgets/app-shell";

import { NotFoundPage } from "./NotFoundPage";
import { RedirectIfAuthed } from "./RedirectIfAuthed";
import { RequireAuth } from "./RequireAuth";

/**
 * Route tree. Auth screens sit behind `RedirectIfAuthed`; every cabinet page
 * sits behind `RequireAuth` and renders inside the `AppShell` layout.
 */
export const router = createBrowserRouter([
  {
    element: <RedirectIfAuthed />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/login/code", element: <OtpPage /> },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <HomePage /> },
          { path: "/market", element: <MarketPage /> },
          { path: "/market/:offerId", element: <MarketOfferPage /> },
          { path: "/companies", element: <CompaniesPage /> },
          { path: "/companies/new", element: <Navigate to="/companies/new/1" replace /> },
          { path: "/companies/new/:step", element: <CompanyCreatePage /> },
          { path: "/companies/:companyId", element: <CompanyViewPage /> },
          { path: "/companies/:companyId/verification", element: <VerificationStatusPage /> },
          { path: "/offers", element: <OffersPage /> },
          { path: "/offers/new", element: <OfferEditPage /> },
          { path: "/offers/:offerId", element: <OfferEditPage /> },
          { path: "/settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
