/**
 * A buyer's analysis request, broadcast to every verified laboratory.
 *
 * Not `entities/lab` — that slice is the STAFF-run partner-lab orders (P6), a
 * different flow with a different audience that this one does not touch.
 */
export interface LabRequest {
  id: number;
  public_id: string;
  number: string;
  buyer_company_id: number;
  product_id: number | null;
  product_text: string;
  grade_text: string | null;
  study_type: string | null;
  /** Keys from `LAB_METHODS`, resolved through i18n — never display strings. */
  methods: string[];
  sample_qty: string | null;
  comment: string | null;
  purpose: string | null;
  is_urgent: boolean;
  desired_date: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  status: LabRequestStatus;
  created_at: string;
  buyer_name: string | null;
  /** Laboratories that opened a conversation — the only signal a broadcast landed. */
  thread_count: number;
}

/** The three dots are the request lifecycle; the form is a wizard of its own. */
export type LabRequestStatus =
  | "submitted"
  | "viewed"
  | "in_progress"
  | "quoted"
  | "closed"
  | "rejected";

/**
 * One open request as a LABORATORY sees it.
 *
 * A separate type rather than `LabRequest` minus the contact block, mirroring
 * the backend: inheriting would mean a field added upstream silently becomes
 * visible to every laboratory.
 */
export interface LabPoolItem {
  id: number;
  number: string;
  buyer_company_id: number;
  buyer_name: string | null;
  product_text: string;
  grade_text: string | null;
  study_type: string | null;
  methods: string[];
  sample_qty: string | null;
  comment: string | null;
  purpose: string | null;
  is_urgent: boolean;
  desired_date: string | null;
  status: LabRequestStatus;
  created_at: string;
  my_thread_id: number | null;
}

export interface LabThread {
  id: number;
  lab_request_id: number;
  request_number: string;
  laboratory_company_id: number;
  counterparty_name: string | null;
  my_role: "buyer" | "laboratory" | "";
  product_text: string;
  created_at: string;
  updated_at: string;
}

export interface LabRequestCreatePayload {
  /** The BUYER's acting company — an account may belong to several. */
  company_id: number;
  product_id?: number | null;
  product_text: string;
  grade_text?: string | null;
  study_type?: string | null;
  methods: string[];
  sample_qty?: string | null;
  comment?: string | null;
  purpose?: string | null;
  is_urgent: boolean;
  desired_date?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
}
