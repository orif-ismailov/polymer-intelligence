import { CapiwsBridge } from "./capiws";
import type { EimzoBridge } from "./types";

export type { EimzoBridge, EimzoCertificate } from "./types";

/**
 * Resolve the active E-IMZO bridge: an injected stub (`window.__EIMZO_BRIDGE__`,
 * used by tests + the desktop-less preview) if present, otherwise the real CAPIWS
 * bridge that talks to the locally installed E-IMZO module.
 */
export function getEimzoBridge(): EimzoBridge {
  if (typeof window !== "undefined" && window.__EIMZO_BRIDGE__) {
    return window.__EIMZO_BRIDGE__;
  }
  return new CapiwsBridge();
}
