import { api } from "@/shared/api";

import type { LabOrder, LabOrderPayload } from "./types";

export const labApi = {
  list: (companyId: number): Promise<LabOrder[]> =>
    api.get<LabOrder[]>(`/portal/companies/${companyId}/lab-orders`),

  get: (companyId: number, orderId: number): Promise<LabOrder> =>
    api.get<LabOrder>(`/portal/companies/${companyId}/lab-orders/${orderId}`),

  /** Raise a request. There is no status endpoint: staff drive the queue. */
  create: (companyId: number, payload: LabOrderPayload): Promise<LabOrder> =>
    api.post<LabOrder>(`/portal/companies/${companyId}/lab-orders`, payload),
};

export const labKeys = {
  list: (companyId: number) => ["lab-orders", companyId] as const,
  detail: (companyId: number, orderId: number) =>
    ["lab-orders", companyId, orderId] as const,
};
