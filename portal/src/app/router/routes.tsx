import { createBrowserRouter, Navigate } from "react-router-dom";

import { CompaniesPage } from "@/pages/companies";
import { CompanyCreatePage } from "@/pages/company-create";
import { CompanyViewPage } from "@/pages/company-view";
import { ContractCreatePage, ContractDetailPage, ContractsPage } from "@/pages/contracts";
import { UiKitPage } from "@/pages/dev-ui";
import { HomePage } from "@/pages/home";
import { InquiriesPage, InquiryDetailPage } from "@/pages/inquiries";
import { LoginPage } from "@/pages/login";
import { MarketOfferPage, MarketPage } from "@/pages/market";
import { NewsArticlePage, NewsPage } from "@/pages/news";
import { NotificationsPage } from "@/pages/notifications";
import { OfferEditPage } from "@/pages/offer-edit";
import { OffersPage } from "@/pages/offers";
import { OtpPage } from "@/pages/otp";
import { RequestCreatePage, RequestDetailPage, RequestsPage } from "@/pages/requests";
import { SettingsPage } from "@/pages/settings";
import { VerificationStatusPage } from "@/pages/verification-status";
import { AppShell } from "@/widgets/app-shell";

import { NotFoundPage } from "./NotFoundPage";
import { RedirectIfAuthed } from "./RedirectIfAuthed";
import { RequireAuth } from "./RequireAuth";

/**
 * Route tree. Auth screens sit behind `RedirectIfAuthed`; every cabinet page
 * sits behind `RequireAuth` and renders inside the `AppShell` layout.
 *
 * `/dev/ui` (the design-system gallery) is mounted only in dev builds and
 * deliberately sits outside both guards — it renders primitives, no account data.
 */
export const router = createBrowserRouter([
  ...(import.meta.env.DEV ? [{ path: "/dev/ui", element: <UiKitPage /> }] : []),
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
          { path: "/inquiries", element: <InquiriesPage /> },
          { path: "/inquiries/:inquiryId", element: <InquiryDetailPage /> },
          { path: "/requests", element: <RequestsPage /> },
          { path: "/requests/new", element: <RequestCreatePage /> },
          { path: "/requests/:requestId", element: <RequestDetailPage /> },
          { path: "/news", element: <NewsPage /> },
          { path: "/news/:signalId", element: <NewsArticlePage /> },
          { path: "/notifications", element: <NotificationsPage /> },
          { path: "/companies", element: <CompaniesPage /> },
          { path: "/companies/new", element: <Navigate to="/companies/new/1" replace /> },
          { path: "/companies/new/:step", element: <CompanyCreatePage /> },
          { path: "/companies/:companyId", element: <CompanyViewPage /> },
          { path: "/companies/:companyId/verification", element: <VerificationStatusPage /> },
          { path: "/offers", element: <OffersPage /> },
          { path: "/offers/new", element: <OfferEditPage /> },
          { path: "/offers/:offerId", element: <OfferEditPage /> },
          { path: "/contracts", element: <ContractsPage /> },
          { path: "/contracts/new", element: <ContractCreatePage /> },
          { path: "/contracts/:contractId", element: <ContractDetailPage /> },
          { path: "/settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
