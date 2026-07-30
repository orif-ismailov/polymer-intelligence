/**
 * Real E-IMZO bridge over the local CAPIWS WebSocket API (R3 Stage A — TA2.1).
 *
 * CAPIWS is served by the installed E-IMZO desktop module at
 * `wss://127.0.0.1:64443`. This wraps its low-level `callFunction` in the small
 * `EimzoBridge` contract (probe → list → sign). The exact call/response shapes
 * follow the published e-imzo.js protocol; because CI/dev have no local module,
 * the tested path is the injected stub — this real path is validated during ops
 * integration against a machine with E-IMZO installed.
 */

import type { EimzoBridge, EimzoCertificate } from "./types";

interface CapiwsResult {
  success?: boolean;
  reason?: string;
  certificates?: CapiwsCert[];
  keyId?: string;
  pkcs7_64?: string;
}

interface CapiwsCert {
  disk: string;
  path: string;
  name: string;
  alias: string;
  serialNumber?: string;
  validTo?: string;
  TIN?: string;
  O?: string;
  CN?: string;
}

interface CapiwsCall {
  plugin: string;
  name: string;
  arguments?: string[];
}

interface CapiwsApi {
  callFunction(
    call: CapiwsCall,
    onSuccess: (event: unknown, data: CapiwsResult) => void,
    onError: (error: unknown) => void,
  ): void;
}

declare global {
  interface Window {
    CAPIWS?: CapiwsApi;
    __EIMZO_BRIDGE__?: EimzoBridge;
  }
}

function call(api: CapiwsApi, request: CapiwsCall): Promise<CapiwsResult> {
  return new Promise((resolve, reject) => {
    try {
      api.callFunction(
        request,
        (_event, data) => resolve(data),
        (error) => reject(error instanceof Error ? error : new Error(String(error))),
      );
    } catch (err) {
      reject(err instanceof Error ? err : new Error(String(err)));
    }
  });
}

function subjectOf(cert: CapiwsCert): string {
  return [cert.O, cert.CN].filter(Boolean).join(" — ") || cert.alias || cert.name;
}

export class CapiwsBridge implements EimzoBridge {
  private get api(): CapiwsApi | undefined {
    return typeof window !== "undefined" ? window.CAPIWS : undefined;
  }

  async probe(): Promise<boolean> {
    const api = this.api;
    if (!api) return false;
    try {
      await call(api, { plugin: "pfx", name: "list_all_certificates" });
      return true;
    } catch {
      return false;
    }
  }

  async listCertificates(): Promise<EimzoCertificate[]> {
    const api = this.api;
    if (!api) return [];
    const data = await call(api, { plugin: "pfx", name: "list_all_certificates" });
    const certs = data.certificates ?? [];
    return certs.map((c) => ({
      id: JSON.stringify({ disk: c.disk, path: c.path, name: c.name, alias: c.alias }),
      subjectName: subjectOf(c),
      tin: c.TIN,
      name: c.CN,
      validTo: c.validTo,
    }));
  }

  async sign(certId: string, challenge: string): Promise<string> {
    const api = this.api;
    if (!api) throw new Error("eimzo_module_unavailable");
    const { disk, path, name, alias } = JSON.parse(certId) as {
      disk: string;
      path: string;
      name: string;
      alias: string;
    };
    const loaded = await call(api, {
      plugin: "pfx",
      name: "load_key",
      arguments: [disk, path, name, alias],
    });
    if (!loaded.keyId) throw new Error("eimzo_key_load_failed");
    const data = window.btoa(unescape(encodeURIComponent(challenge)));
    const signed = await call(api, {
      plugin: "pkcs7",
      name: "create_pkcs7",
      arguments: [data, loaded.keyId, "no"],
    });
    if (!signed.pkcs7_64) throw new Error("eimzo_sign_failed");
    return signed.pkcs7_64;
  }
}
