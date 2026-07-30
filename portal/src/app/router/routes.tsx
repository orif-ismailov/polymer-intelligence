import { createBrowserRouter, Navigate } from "react-router-dom";

import { CompaniesPage } from "@/pages/companies";
import { CompanyCreatePage, CompanyCreatedPage } from "@/pages/company-create";
import { CompanyManagePage, CompanyViewPage } from "@/pages/company-view";
import { ContractCreatePage, ContractDetailPage, ContractsPage } from "@/pages/contracts";
import { DealDetailPage, DealsPage } from "@/pages/deals";
import { UiKitPage } from "@/pages/dev-ui";
import { HomePage } from "@/pages/home";
import { InquiriesPage, InquiryDetailPage } from "@/pages/inquiries";
import { LabOrdersPage } from "@/pages/lab-orders";
import { LoginPage } from "@/pages/login";
import {
  FactoryRfqDonePage,
  FactoryRfqPage,
  ManufacturerChatPage,
  ManufacturerDetailPage,
  ManufacturersPage,
} from "@/pages/manufacturers";
import {
  FavoritesPage,
  MarketOfferPage,
  MarketPage,
  MarketRequestsPage,
} from "@/pages/market";
import { NewsArticlePage, NewsPage } from "@/pages/news";
import { NotificationsPage } from "@/pages/notifications";
import { OfferCreatePage, OfferPublishedPage } from "@/pages/offer-create";
import { OffersPage } from "@/pages/offers";
import { OnboardingPage } from "@/pages/onboarding";
import { OtpPage } from "@/pages/otp";
import { RequestCreatePage, RequestDetailPage, RequestPublishedPage, RequestsPage } from "@/pages/requests";
import { SamplesPage } from "@/pages/samples";
import { SellerProfilePage } from "@/pages/sellers";
import { SettingsPage } from "@/pages/settings";
import { VerificationStatusPage } from "@/pages/verification-status";
import { AppShell } from "@/widgets/app-shell";

import { NotFoundPage } from "./NotFoundPage";
import { OfferEditRedirect } from "./OfferEditRedirect";
import { RedirectIfAuthed } from "./RedirectIfAuthed";
import { RequireAuth } from "./RequireAuth";
import { RequireCompany } from "./RequireCompany";

/**
 * Route tree. Auth screens sit behind `RedirectIfAuthed`; cabinet pages sit
 * behind `RequireAuth` + `RequireCompany` and render inside the `AppShell`
 * layout.
 *
 * The registration flow (`/onboarding`, `/companies/new/*`) is authenticated but
 * sits OUTSIDE both the shell and `RequireCompany` — it is the screen that
 * resolves "you have no company", so gating it on having one would loop.
 *
 * `/dev/ui` (the design-system gallery) is mounted only in dev builds and
 * deliberately sits outside every guard — it renders primitives, no account data.
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
      // Registration: full-screen, no shell, no company required.
      { path: "/onboarding", element: <OnboardingPage /> },
      { path: "/companies/new", element: <Navigate to="/companies/new/1" replace /> },
      { path: "/companies/new/done/:companyId", element: <CompanyCreatedPage /> },
      { path: "/companies/new/:step", element: <CompanyCreatePage /> },
      {
        element: <RequireCompany />,
        children: [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <HomePage /> },
          { path: "/market", element: <MarketPage /> },
          { path: "/market/requests", element: <MarketRequestsPage /> },
          // Literal before the :offerId param route, or "favorites" is read as an id.
          { path: "/market/favorites", element: <FavoritesPage /> },
          { path: "/market/:offerId", element: <MarketOfferPage /> },
          { path: "/sellers/:companyId", element: <SellerProfilePage /> },
          { path: "/manufacturers", element: <ManufacturersPage /> },
          // Literal segments before the `:companyId` param route, same reason
          // as `/market/favorites` above.
          { path: "/manufacturers/rfqs/:rfqId/done", element: <FactoryRfqDonePage /> },
          { path: "/manufacturers/:companyId/chat", element: <ManufacturerChatPage /> },
          { path: "/manufacturers/:companyId/rfq/:offerId", element: <FactoryRfqPage /> },
          { path: "/manufacturers/:companyId", element: <ManufacturerDetailPage /> },
          { path: "/deals", element: <DealsPage /> },
          { path: "/deals/:dealId", element: <DealDetailPage /> },
          { path: "/inquiries", element: <InquiriesPage /> },
          { path: "/samples", element: <SamplesPage /> },
          { path: "/lab-orders", element: <LabOrdersPage /> },
          { path: "/inquiries/:inquiryId", element: <InquiryDetailPage /> },
          { path: "/requests", element: <RequestsPage /> },
          { path: "/requests/new", element: <Navigate to="/requests/new/1" replace /> },
          { path: "/requests/new/done/:requestId", element: <RequestPublishedPage /> },
          { path: "/requests/new/:step", element: <RequestCreatePage /> },
          { path: "/requests/:requestId", element: <RequestDetailPage /> },
          { path: "/news", element: <NewsPage /> },
          { path: "/news/:signalId", element: <NewsArticlePage /> },
          { path: "/notifications", element: <NotificationsPage /> },
          { path: "/companies", element: <CompaniesPage /> },
          { path: "/companies/:companyId/manage", element: <CompanyManagePage /> },
          { path: "/companies/:companyId/verification", element: <VerificationStatusPage /> },
          { path: "/companies/:companyId", element: <CompanyViewPage /> },
          { path: "/offers", element: <OffersPage /> },
          // The add-product flow is URL-addressable by step. Literal segments
          // before the `:offerId` param route, or "new" is read as an offer id.
          { path: "/offers/new", element: <Navigate to="/offers/new/1" replace /> },
          { path: "/offers/new/done/:offerId", element: <OfferPublishedPage /> },
          { path: "/offers/new/:step", element: <OfferCreatePage /> },
          { path: "/offers/:offerId/edit/:step", element: <OfferCreatePage /> },
          { path: "/offers/:offerId", element: <OfferEditRedirect /> },
          { path: "/contracts", element: <ContractsPage /> },
          { path: "/contracts/new", element: <ContractCreatePage /> },
          { path: "/contracts/:contractId", element: <ContractDetailPage /> },
          { path: "/settings", element: <SettingsPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
        ],
      },
    ],
  },
]);
