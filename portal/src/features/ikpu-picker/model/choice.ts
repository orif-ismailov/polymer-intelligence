import type { DidoxIkpuChoice } from "@/entities/edi";

import type { IkpuValue } from "../ui/IkpuPicker";

/**
 * The picker's value as a Didox document takes it — complete or nothing.
 *
 * The code, its package and the seller's origin all reach my.soliq.uz, so a
 * half-made pick is no pick at all.
 */
export function ikpuChoiceOf(ikpu: IkpuValue | null): DidoxIkpuChoice | null {
  if (!ikpu || !ikpu.packageCode || ikpu.origin == null) return null;
  return {
    code: ikpu.code,
    name: ikpu.name,
    package_code: ikpu.packageCode,
    package_name: ikpu.packageName,
    origin: ikpu.origin,
  };
}
