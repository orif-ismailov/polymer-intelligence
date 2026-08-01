import { Navigate, type RouteObject } from "react-router-dom";

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
import { PublicCompanyPage, PublicDirectoryPage } from "@/pages/public-directory";
import { PublicHomePage } from "@/pages/public-home";
import { PublicMarketPage, PublicOfferPage } from "@/pages/public-market";
import { PublicPricesPage } from "@/pages/public-prices";
import { RequestCreatePage, RequestDetailPage, RequestPublishedPage, RequestsPage } from "@/pages/requests";
import { SamplesPage } from "@/pages/samples";
import { SellerProfilePage } from "@/pages/sellers";
import { SettingsPage } from "@/pages/settings";
import { VerificationStatusPage } from "@/pages/verification-status";
import { PUBLIC_DIRECTORIES } from "@/shared/config";
import { AppShell } from "@/widgets/app-shell";
import { PublicShell } from "@/widgets/public-shell";

import { NotFoundPage } from "./NotFoundPage";
import { OfferEditRedirect } from "./OfferEditRedirect";
import { RedirectIfAuthed } from "./RedirectIfAuthed";
import { RequireAuth } from "./RequireAuth";
import { RequireCompany } from "./RequireCompany";

/** The three directories with no distinct cabinet page — read-only either way. */
const REUSED_DIRECTORIES = PUBLIC_DIRECTORIES.filter((d) => d.slug !== "manufacturers");

/**
 * Route tree, in two namespaces.
 *
 * 1. **Public storefront** at the root — `/`, `/market`, `/prices`, `/news`, the
 *    four company directories. These are the crawlable URLs and the only ones
 *    that are server-rendered.
 * 2. **Cabinet** under `/cabinet` — auth screens behind `RedirectIfAuthed`,
 *    everything else behind `RequireAuth` + `RequireCompany` inside `AppShell`.
 *
 * The storefront is **not** anonymous-only. A session is what lets you ACT —
 * send an inquiry, open an RFQ, publish an offer — not what lets you READ, so a
 * signed-in visitor browses `/market` and a listing's public page like anyone
 * else, and a link sent from outside lands where it points whoever opens it. The
 * guard that used to bounce them to the `/cabinet` twin is gone; the public
 * chrome swaps its two auth buttons for a «Кабинет» link instead.
 *
 * The prefix exists because the two namespaces used to be one, and the cabinet
 * kept colliding with the storefront: `/market/favorites` had to out-rank
 * `/market/:offerId`, `/manufacturers/:id/chat` had to out-rank the public
 * directory's `:companyId`, and both were held apart by comments rather than by
 * structure. Now no public path can be shadowed by a cabinet one — that
 * collision-freedom is the whole job the prefix does.
 *
 * Where a page reads the same signed in or out (`/prices`, `/news`, the three
 * non-manufacturer directories), the cabinet re-renders the SAME component
 * inside `AppShell`; only the chrome differs, and `useTierBase()` keeps each
 * copy's links inside the tier it is rendering in. That duplication is
 * deliberate but temporary — it is being collapsed onto the public URL page by
 * page, so do not add new twins.
 *
 * The registration flow (`onboarding`, `companies/new/*`) is authenticated but
 * sits OUTSIDE both the shell and `RequireCompany` — it is the screen that
 * resolves "you have no company", so gating it on having one would loop.
 *
 * `/dev/ui` (the design-system gallery) is mounted only in dev builds and
 * deliberately sits outside every guard — it renders primitives, no account data.
 *
 * Exported as a plain array rather than a router so both entries can build their
 * own: `createBrowserRouter` in the browser, `createStaticHandler` on the server.
 */
export const routes: RouteObject[] = [
  ...(import.meta.env.DEV ? [{ path: "/dev/ui", element: <UiKitPage /> }] : []),

  // ── Public storefront. Server-rendered, open to everyone. ──────────────────
  {
    element: <PublicShell />,
    children: [
      { path: "/", element: <PublicHomePage /> },
      { path: "/market", element: <PublicMarketPage /> },
      { path: "/market/:offerId", element: <PublicOfferPage /> },
      { path: "/prices", element: <PublicPricesPage /> },
      { path: "/news", element: <NewsPage /> },
      { path: "/news/:signalId", element: <NewsArticlePage /> },
      // The four directories share one page component, keyed by slug.
      // Declared as literal paths rather than `/:slug` so an unknown segment
      // falls through to the 404 instead of rendering an empty directory.
      ...PUBLIC_DIRECTORIES.flatMap((dir) => [
        { path: `/${dir.slug}`, element: <PublicDirectoryPage slug={dir.slug} /> },
        {
          path: `/${dir.slug}/:companyId`,
          element: <PublicCompanyPage slug={dir.slug} />,
        },
      ]),
    ],
  },

  // ── Cabinet. Client-rendered, noindex, session required. ───────────────────
  {
    path: "/cabinet",
    children: [
      {
        element: <RedirectIfAuthed />,
        children: [
          { path: "login", element: <LoginPage /> },
          { path: "login/code", element: <OtpPage /> },
        ],
      },
      {
        element: <RequireAuth />,
        children: [
          // Registration: full-screen, no shell, no company required.
          { path: "onboarding", element: <OnboardingPage /> },
          { path: "companies/new", element: <Navigate to="/cabinet/companies/new/1" replace /> },
          { path: "companies/new/done/:companyId", element: <CompanyCreatedPage /> },
          { path: "companies/new/:step", element: <CompanyCreatePage /> },
          {
            element: <RequireCompany />,
            children: [
              {
                element: <AppShell />,
                children: [
                  { index: true, element: <HomePage /> },

                  // Marketplace. The literal-before-param ordering that used to
                  // be load-bearing here is now just readability: nothing public
                  // shares this namespace.
                  { path: "market", element: <MarketPage /> },
                  { path: "market/favorites", element: <FavoritesPage /> },
                  { path: "market/requests", element: <MarketRequestsPage /> },
                  { path: "market/:offerId", element: <MarketOfferPage /> },

                  // Manufacturers: a real cabinet directory, plus the RFQ/chat
                  // surfaces that only exist for a signed-in company.
                  { path: "manufacturers", element: <ManufacturersPage /> },
                  { path: "manufacturers/rfqs/:rfqId/done", element: <FactoryRfqDonePage /> },
                  { path: "manufacturers/:companyId", element: <ManufacturerDetailPage /> },
                  { path: "manufacturers/:companyId/chat", element: <ManufacturerChatPage /> },
                  { path: "manufacturers/:companyId/rfq/:offerId", element: <FactoryRfqPage /> },

                  // Same components as the storefront, different chrome.
                  { path: "prices", element: <PublicPricesPage /> },
                  { path: "news", element: <NewsPage /> },
                  { path: "news/:signalId", element: <NewsArticlePage /> },
                  ...REUSED_DIRECTORIES.flatMap((dir) => [
                    { path: dir.slug, element: <PublicDirectoryPage slug={dir.slug} /> },
                    {
                      path: `${dir.slug}/:companyId`,
                      element: <PublicCompanyPage slug={dir.slug} />,
                    },
                  ]),

                  { path: "sellers/:companyId", element: <SellerProfilePage /> },
                  { path: "deals", element: <DealsPage /> },
                  { path: "deals/:dealId", element: <DealDetailPage /> },
                  { path: "inquiries", element: <InquiriesPage /> },
                  { path: "inquiries/:inquiryId", element: <InquiryDetailPage /> },
                  { path: "samples", element: <SamplesPage /> },
                  { path: "lab-orders", element: <LabOrdersPage /> },
                  { path: "requests", element: <RequestsPage /> },
                  { path: "requests/new", element: <Navigate to="/cabinet/requests/new/1" replace /> },
                  { path: "requests/new/done/:requestId", element: <RequestPublishedPage /> },
                  { path: "requests/new/:step", element: <RequestCreatePage /> },
                  { path: "requests/:requestId", element: <RequestDetailPage /> },
                  { path: "notifications", element: <NotificationsPage /> },
                  { path: "companies", element: <CompaniesPage /> },
                  { path: "companies/:companyId/manage", element: <CompanyManagePage /> },
                  { path: "companies/:companyId/verification", element: <VerificationStatusPage /> },
                  { path: "companies/:companyId", element: <CompanyViewPage /> },
                  { path: "offers", element: <OffersPage /> },
                  // The add-product flow is URL-addressable by step. Literal
                  // segments before the `:offerId` param route, or "new" is read
                  // as an offer id.
                  { path: "offers/new", element: <Navigate to="/cabinet/offers/new/1" replace /> },
                  { path: "offers/new/done/:offerId", element: <OfferPublishedPage /> },
                  { path: "offers/new/:step", element: <OfferCreatePage /> },
                  { path: "offers/:offerId/edit/:step", element: <OfferCreatePage /> },
                  { path: "offers/:offerId", element: <OfferEditRedirect /> },
                  { path: "contracts", element: <ContractsPage /> },
                  { path: "contracts/new", element: <ContractCreatePage /> },
                  { path: "contracts/:contractId", element: <ContractDetailPage /> },
                  { path: "settings", element: <SettingsPage /> },
                  { path: "*", element: <NotFoundPage /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },

  // Public 404. Previously the only catch-all lived inside `AppShell`, behind
  // both guards, so an anonymous visitor to an unknown URL was bounced to the
  // login screen instead of being told the page does not exist.
  { path: "*", element: <NotFoundPage /> },
];
