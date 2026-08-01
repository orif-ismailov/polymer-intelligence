/**
 * Shared nav glyphs for the cabinet chrome — used by both the desktop sidebar
 * and the mobile bottom bar so a route's icon is identical in both.
 *
 * Lucide, sized for the 18px nav slot. Glyphs match what each route actually is
 * (RFQs, products, samples…), not a generic document/tag.
 */

import {
  Building2,
  ClipboardList,
  Factory,
  FileCheck2,
  FlaskConical,
  Globe,
  Handshake,
  Heart,
  Home,
  Inbox,
  Newspaper,
  Package,
  PackageOpen,
  Settings,
  Store,
} from "lucide-react";

const props = { size: 18, strokeWidth: 1.75, "aria-hidden": true as const };

export const HomeIcon = <Home {...props} />;
export const BuildingIcon = <Building2 {...props} />;
/** Seller offers — product listings. */
export const TagIcon = <Package {...props} />;
export const CogIcon = <Settings {...props} />;
export const StoreIcon = <Store {...props} />;
/** Manufacturers directory. */
export const ManufacturersIcon = <Factory {...props} />;
/** Buyer↔seller inquiry inbox. */
export const ChatIcon = <Inbox {...props} />;
/** Purchase requests / RFQs. */
export const DocIcon = <ClipboardList {...props} />;
export const NewsIcon = <Newspaper {...props} />;
export const ContractIcon = <FileCheck2 {...props} />;
export const HandshakeIcon = <Handshake {...props} />;
export const HeartIcon = <Heart {...props} />;
export const FlaskNavIcon = <FlaskConical {...props} />;
/** Physical sample requests. */
export const SampleBoxIcon = <PackageOpen {...props} />;
/**
 * The public storefront — the world-facing site, not the cabinet's own market
 * screen. `Store` is already the cabinet catalog; reusing it here would say the
 * two links go to the same place.
 */
export const PublicSiteIcon = <Globe {...props} />;
