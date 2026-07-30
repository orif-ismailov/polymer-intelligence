/**
 * Portal icons — Lucide wrappers that keep the existing `{ size, className }` API
 * so call sites and `@/shared/ui` re-exports stay stable.
 *
 * Prefer adding a new named export here (mapped to a Lucide glyph) rather than
 * pasting raw SVG into a page. Glyphs are chosen for the portal's domain
 * (market / lab / verification / RFQ), not for decorative variety.
 */

import { type ComponentType } from "react";

import {
  AlertCircle,
  AlignLeft,
  Ban,
  Banknote,
  Bell,
  Boxes,
  Building2,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleMinus,
  ClipboardList,
  Clock,
  CloudUpload,
  Copy,
  Download,
  Eye,
  EyeOff,
  Factory,
  FileCheck2,
  FileText,
  FileType,
  FlaskConical,
  FolderCheck,
  GitCompare,
  Globe,
  Handshake,
  Hash,
  Heart,
  Image as LucideImage,
  Inbox,
  Info,
  KeyRound,
  Landmark,
  Lock,
  Mail,
  MapPin,
  MessageSquare,
  Newspaper,
  Package,
  PackageOpen,
  Paperclip,
  PenLine,
  Plus,
  Receipt,
  Scale,
  ScrollText,
  Search,
  Send,
  Share2,
  Shield,
  ShieldAlert,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Star,
  Store,
  Tag,
  TestTube,
  Truck,
  Upload,
  UserRound,
  Users,
  Usb,
  Warehouse,
  X,
  type LucideProps,
} from "lucide-react";

export interface IconProps {
  size?: number;
  className?: string;
}

type LucideGlyph = ComponentType<LucideProps>;

function icon(Glyph: LucideGlyph) {
  function Icon({ size = 14, className }: IconProps) {
    return <Glyph size={size} className={className} aria-hidden="true" strokeWidth={1.75} />;
  }
  Icon.displayName = Glyph.displayName ?? Glyph.name;
  return Icon;
}

/** Filled tick-in-circle — Verified / passed check (mockup badge glyph). */
export const CheckCircleIcon = icon(CircleCheck);
/** Bare tick, for use inside an already-filled circle (steppers). */
export const CheckIcon = icon(Check);
/** Soft negative — «Нет паспорта» and similar non-chosen tiles. */
export const CircleMinusIcon = icon(CircleMinus);
export const FlaskIcon = icon(FlaskConical);
export const TestTubeIcon = icon(TestTube);
export const BoxIcon = icon(Package);
export const PackageOpenIcon = icon(PackageOpen);
export const ClockIcon = icon(Clock);
export const ChevronLeftIcon = icon(ChevronLeft);
export const ChevronRightIcon = icon(ChevronRight);
export const DownloadIcon = icon(Download);
export const FileIcon = icon(FileText);
export const InfoIcon = icon(Info);
export const ChevronDownIcon = icon(ChevronDown);
export const CloseIcon = icon(X);
export const GlobeIcon = icon(Globe);
export const MapPinIcon = icon(MapPin);
export const WarehouseIcon = icon(Warehouse);
export const CalendarIcon = icon(Calendar);
export const EyeIcon = icon(Eye);
export const EyeOffIcon = icon(EyeOff);
/** Outline tick-in-circle — AI-check row / soft success. */
export const CheckCircleOutlineIcon = icon(CheckCircle2);
export const AlertCircleIcon = icon(AlertCircle);
export const AlignLeftIcon = icon(AlignLeft);
export const ShieldCheckIcon = icon(ShieldCheck);
export const ShieldAlertIcon = icon(ShieldAlert);
export const SparkIcon = icon(Sparkles);
export const BuyerIcon = icon(ShoppingBag);
/** Distributor / supplier account type — inventory, not a delivery truck. */
export const SupplierIcon = icon(Boxes);
export const FactoryIcon = icon(Factory);
export const TraderIcon = icon(Handshake);
export const RegistryIcon = icon(Building2);
export const BankIcon = icon(Landmark);
export const TaxIcon = icon(Receipt);
export const DirectorIcon = icon(UserRound);
export const LicenseIcon = icon(ScrollText);
export const LockIcon = icon(Lock);
export const ScaleIcon = icon(Scale);
export const SanctionsIcon = icon(Ban);
export const PlusIcon = icon(Plus);
export const ImageIcon = icon(LucideImage);
export const UploadCloudIcon = icon(CloudUpload);
export const TagIcon = icon(Tag);
export const BanknoteIcon = icon(Banknote);
export const TruckIcon = icon(Truck);
export const CopyIcon = icon(Copy);
/** Publish / go-live moment on the offer preview. */
export const RocketIcon = icon(Upload);
export const ShieldIcon = icon(Shield);
export const SendIcon = icon(Send);
export const ShareIcon = icon(Share2);
export const MessageIcon = icon(MessageSquare);
export const InboxIcon = icon(Inbox);
export const StarIcon = icon(Star);
/** HS / CAS-style codes — a hash, not a network graph. */
export const NodesIcon = icon(Hash);
export const HashIcon = icon(Hash);
export const PdfIcon = icon(FileType);
export const HeartIcon = icon(Heart);
export const ContractSheetIcon = icon(FileCheck2);
export const ClipboardListIcon = icon(ClipboardList);
export const FolderCheckIcon = icon(FolderCheck);
export const GitCompareIcon = icon(GitCompare);
export const PenLineIcon = icon(PenLine);
export const KeyRoundIcon = icon(KeyRound);
export const UsbIcon = icon(Usb);
export const StoreIcon = icon(Store);
export const BellIcon = icon(Bell);
export const NewspaperIcon = icon(Newspaper);
export const PaperclipIcon = icon(Paperclip);
export const SearchIcon = icon(Search);
export const MailIcon = icon(Mail);
export const UsersIcon = icon(Users);
