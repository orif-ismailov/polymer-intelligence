import { Navigate, type RouteObject } from "react-router-dom";

import { CompaniesPage } from "@/pages/companies";
import { CompanyCreatePage, CompanyCreatedPage } from "@/pages/company-create";
import { CompanyManagePage, CompanyViewPage } from "@/pages/company-view";
import { ContractCreatePage, ContractDetailPage, ContractsPage } from "@/pages/contracts";
import { DealDetailPage, DealsPage } from "@/pages/deals";
import { UiKitPage } from "@/pages/dev-ui";
import { HomePage } from "@/pages/home";
import { InquiriesPage, InquiryDetailPage } from "@/pages/inquiries";
import {
  LabHubPage,
  LabRequestDetailPage,
  LabRequestDonePage,
  LabRequestPage,
  LabThreadPage,
} from "@/pages/lab";
import {
  LogisticsRequestDetailPage,
  LogisticsRequestDonePage,
  LogisticsRequestPage,
  LogisticsRequestsPage,
  LogisticsThreadPage,
} from "@/pages/logistics";
import { LoginPage } from "@/pages/login";
import {
  FactoryRfqDonePage,
  FactoryRfqPage,
  ManufacturerChatPage,
} from "@/pages/manufacturers";
import { FavoritesPage, MarketRequestsPage } from "@/pages/market";
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
import { RequestCreatePage, RequestDetailPage, RequestPublishedPage } from "@/pages/requests";
import { SamplesPage } from "@/pages/samples";
import { SellerProfilePage } from "@/pages/sellers";
import { SettingsPage } from "@/pages/settings";
import { VerificationStatusPage } from "@/pages/verification-status";
import { PUBLIC_DIRECTORIES } from "@/shared/config";
import { AppShell } from "@/widgets/app-shell";
import { PublicShell } from "@/widgets/public-shell";

import { NotFoundPage } from "./NotFoundPage";
import { RequestsRouteSwitch } from "./RequestsRouteSwitch";
import { OfferEditRedirect } from "./OfferEditRedirect";
import {
  RedirectToPublicCompany,
  RedirectToPublicNewsArticle,
  RedirectToPublicOffer,
} from "./RedirectToPublic";
import { RedirectIfAuthed } from "./RedirectIfAuthed";
import { RequireAuth } from "./RequireAuth";
import { RequireCompany } from "./RequireCompany";
import { RequireFeature } from "./RequireFeature";
import { RootLayout } from "./RootLayout";

/**
 * Directories that still render a cabinet twin — read-only either way.
 *
 * The list shrinks as directories collapse onto their public URL. `logistics`
 * left when the carrier profile grew a session-aware «Связаться с компанией»
 * CTA: a twin means that component renders at two addresses and `useTierBase()`
 * makes every href tier-dependent, so the login round-trip has to be got right
 * twice. Don't add to this list — see `portal/CLAUDE.md`.
 */
const COLLAPSED_DIRECTORIES = ["manufacturers", "logistics"];
const REUSED_DIRECTORIES = PUBLIC_DIRECTORIES.filter(
  (d) => !COLLAPSED_DIRECTORIES.includes(d.slug),
);

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
const appRoutes: RouteObject[] = [
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
      // ── Retired cabinet addresses ────────────────────────────────────────
      //
      // Directories that have collapsed onto their public URL. These are pure
      // redirects to a page anyone may read, so they carry NO guard: declared
      // deeper in the tree they sat behind `RequireAuth` + `RequireCompany`,
      // and an old bookmark opened by someone with no company registered was
      // answered with `/cabinet/onboarding` — a signed-in dead end in place of
      // the public profile the link actually names.
      { path: "manufacturers", element: <Navigate to="/manufacturers" replace /> },
      {
        path: "manufacturers/:companyId",
        element: <RedirectToPublicCompany slug="manufacturers" />,
      },
      { path: "logistics", element: <Navigate to="/logistics" replace /> },
      {
        path: "logistics/:companyId",
        element: <RedirectToPublicCompany slug="logistics" />,
      },
      // News, for the same reason and with the same care about placement: the
      // reader is public now, so an old `/cabinet/news/:id` out of a
      // notification must land on the article, not on a login form.
      { path: "news", element: <Navigate to="/news" replace /> },
      { path: "news/:signalId", element: <RedirectToPublicNewsArticle /> },
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

                  // Marketplace. Browsing a listing and reading a company are
                  // PUBLIC — `/market`, `/market/:id`, `/manufacturers/:id` — and
                  // the signed-in actions now mount on those same pages after
                  // hydration. What survives here is what only exists with a
                  // session: the buyer's own saved offers and RFQ inbox, and the
                  // factory chat / RFQ flows.
                  //
                  // The two `:id` redirects are not decoration: notification
                  // payloads and anything a buyer bookmarked still carry the old
                  // cabinet URLs.
                  { path: "market", element: <Navigate to="/market" replace /> },
                  // Role-gated groups (`RequireFeature`): a feature outside the
                  // active company's account type redirects to /cabinet. The
                  // matrix is entities/company/model/features.ts; the API
                  // enforces the same sets with 403 role_not_allowed.
                  {
                    element: <RequireFeature feature="favorites" />,
                    children: [{ path: "market/favorites", element: <FavoritesPage /> }],
                  },
                  {
                    element: <RequireFeature feature="rfqInbox" />,
                    children: [{ path: "market/requests", element: <MarketRequestsPage /> }],
                  },
                  { path: "market/:offerId", element: <RedirectToPublicOffer /> },

                  // The directory redirects live at the unguarded top of
                  // `/cabinet` — see the note there. What stays here is what
                  // genuinely needs a session AND a company.
                  {
                    element: <RequireFeature feature="factory" />,
                    children: [
                      { path: "manufacturers/rfqs/:rfqId/done", element: <FactoryRfqDonePage /> },
                      { path: "manufacturers/:companyId/chat", element: <ManufacturerChatPage /> },
                      { path: "manufacturers/:companyId/rfq/:offerId", element: <FactoryRfqPage /> },
                    ],
                  },

                  // Reading a carrier is public; asking one for a price is
                  // not. These two need a session AND a company, so unlike
                  // the directory redirects above they stay inside the guards.
                  // The laboratory hub: marketplace analysis requests and the
                  // staff-run partner-lab orders (P6), one page with two tabs.
                  // The route sits behind the WIDER `labOrdering` gate; the
                  // orders tab is shown by the page only for roles that also
                  // hold `labOrders`. The retired list addresses redirect in.
                  //
                  // `lab/threads` and `logistics/threads` stay OUTSIDE the
                  // ordering gates on purpose: a thread is one address for both
                  // sides, and the answering laboratory/carrier is exactly who
                  // the gate excludes — walling the room off from the party the
                  // notification invited would break the conversation.
                  {
                    element: <RequireFeature feature="labOrdering" />,
                    children: [
                      { path: "lab", element: <LabHubPage /> },
                      { path: "lab/requests", element: <Navigate to="/cabinet/lab" replace /> },
                      { path: "lab/requests/new", element: <LabRequestPage /> },
                      {
                        path: "lab/requests/:requestId/done",
                        element: <LabRequestDonePage />,
                      },
                      { path: "lab/requests/:requestId", element: <LabRequestDetailPage /> },
                    ],
                  },
                  // Old bookmark; the hub's gate is wider, so the redirect can
                  // sit outside it and let the target decide.
                  {
                    path: "lab-orders",
                    element: <Navigate to="/cabinet/lab?tab=orders" replace />,
                  },
                  { path: "lab/threads/:threadId", element: <LabThreadPage /> },

                  {
                    element: <RequireFeature feature="logisticsOrdering" />,
                    children: [
                      { path: "logistics/requests", element: <LogisticsRequestsPage /> },
                      { path: "logistics/requests/new", element: <LogisticsRequestPage /> },
                      {
                        path: "logistics/requests/:requestId/done",
                        element: <LogisticsRequestDonePage />,
                      },
                      {
                        path: "logistics/requests/:requestId",
                        element: <LogisticsRequestDetailPage />,
                      },
                    ],
                  },
                  // One address for a conversation, whichever side clicks it.
                  { path: "logistics/threads/:threadId", element: <LogisticsThreadPage /> },

                  // Same components as the storefront, different chrome.
                  { path: "prices", element: <PublicPricesPage /> },
                  // News is NOT here any more — it collapsed onto its public URL
                  // and its retired addresses redirect from the top of this
                  // subtree, above the guards. See the note there.
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
                  {
                    element: <RequireFeature feature="inquiries" />,
                    children: [
                      { path: "inquiries", element: <InquiriesPage /> },
                      { path: "inquiries/:inquiryId", element: <InquiryDetailPage /> },
                    ],
                  },
                  {
                    element: <RequireFeature feature="samples" />,
                    children: [{ path: "samples", element: <SamplesPage /> }],
                  },
                  // «Заявки» means the buyer's purchase requests, or the
                  // broadcast pool for a carrier/lab — see RequestsRouteSwitch.
                  // The index is NOT feature-gated: it IS the pool for the
                  // service roles. Only the buyer wizard/detail below it is.
                  { path: "requests", element: <RequestsRouteSwitch /> },
                  {
                    element: <RequireFeature feature="purchaseRequests" />,
                    children: [
                      { path: "requests/new", element: <Navigate to="/cabinet/requests/new/1" replace /> },
                      { path: "requests/new/done/:requestId", element: <RequestPublishedPage /> },
                      { path: "requests/new/:step", element: <RequestCreatePage /> },
                      { path: "requests/:requestId", element: <RequestDetailPage /> },
                    ],
                  },
                  { path: "notifications", element: <NotificationsPage /> },
                  { path: "companies", element: <CompaniesPage /> },
                  { path: "companies/:companyId/manage", element: <CompanyManagePage /> },
                  { path: "companies/:companyId/verification", element: <VerificationStatusPage /> },
                  { path: "companies/:companyId", element: <CompanyViewPage /> },
                  // The add-product flow is URL-addressable by step. Literal
                  // segments before the `:offerId` param route, or "new" is read
                  // as an offer id.
                  {
                    element: <RequireFeature feature="offers" />,
                    children: [
                      { path: "offers", element: <OffersPage /> },
                      { path: "offers/new", element: <Navigate to="/cabinet/offers/new/1" replace /> },
                      { path: "offers/new/done/:offerId", element: <OfferPublishedPage /> },
                      { path: "offers/new/:step", element: <OfferCreatePage /> },
                      { path: "offers/:offerId/edit/:step", element: <OfferCreatePage /> },
                      { path: "offers/:offerId", element: <OfferEditRedirect /> },
                    ],
                  },
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

/**
 * Everything above, under one pathless layout route.
 *
 * `RootLayout` renders `<ScrollRestoration>`, which has to sit inside the router
 * to see the navigation — so it needs a route of its own, and it has to be THIS
 * one: the storefront, the cabinet, the registration flow and the 404 are four
 * separate top-level entries, and a shell-level mount would miss every page that
 * deliberately renders outside a shell (login, onboarding, the wizards).
 *
 * Wrapping here rather than re-indenting the tree above keeps `appRoutes`
 * readable as the route map it is.
 */
export const routes: RouteObject[] = [{ element: <RootLayout />, children: appRoutes }];
