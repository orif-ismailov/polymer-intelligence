/** In-portal notification — i18n keys + params, never pre-rendered text. */
export interface PortalNotification {
  id: number;
  kind: string;
  title_key: string;
  body_key: string;
  params: Record<string, unknown>;
  entity: string | null;
  entity_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPage {
  items: PortalNotification[];
  next_cursor: number | null;
}

export interface MarkReadBody {
  ids?: number[];
  all?: boolean;
}
