/**
 * Real E-IMZO bridge over the local CAPIWS WebSocket API (R3 Stage A — TA2.1).
 *
 * CAPIWS is served by the installed E-IMZO desktop module at
 * `wss://127.0.0.1:64443`; the transport itself is `capiwsSocket.ts`, which is
 * what puts `window.CAPIWS` there in the first place. This module wraps the
 * low-level `callFunction` in the small `EimzoBridge` contract
 * (probe → list → sign).
 */

import { EIMZO_API_KEYS, isApiKeyRejection } from "./apikey";
import { ensureCapiwsInstalled } from "./capiwsSocket";
import type { CapiwsApi, CapiwsRequest } from "./capiwsSocket";
import type {
  EimzoBridge,
  EimzoCertificate,
  EimzoKeySession,
  EimzoSignature,
} from "./types";

/** The two file key stores. Hardware tokens are reached through their own plugins. */
export type EimzoStore = "pfx" | "ytks";

/**
 * The module answered, and said no.
 *
 * Distinct from a transport failure: the module IS running. `reason` is its own
 * message (Russian), which is the only thing that distinguishes a wrong store
 * password from a rejected Origin, so it must not be swallowed.
 */
export class CapiwsError extends Error {
  readonly reason: string;
  /** The module's own numeric status, when it sent one. */
  readonly status: number | undefined;

  constructor(operation: string, reason: string, status?: number) {
    super(`eimzo_${operation}_failed: ${reason}`);
    this.name = "CapiwsError";
    this.reason = reason;
    this.status = status;
  }

  /** The module refused our browser Origin — see `apikey.ts`. */
  get isApiKeyRejection(): boolean {
    return isApiKeyRejection(this.reason, this.status);
  }

  /**
   * The person dismissed the native password dialog (or let it lapse).
   *
   * Not a failure of anything — nothing is wrong, they simply did not finish.
   * Worth its own name because the module reports it exactly like a crypto
   * error, and rendering «не удалось подписать» for a closed window sends people
   * hunting for a bug that is not there. Cost most of an afternoon on
   * 25.08.2026: every «не удалось» in that session was this.
   */
  get isCancelled(): boolean {
    return /отмен|bekor|cancel/i.test(this.reason);
  }
}

interface CapiwsResult {
  success?: boolean;
  reason?: string;
  status?: number;
  certificates?: CapiwsCert[];
  keyId?: string;
  pkcs7_64?: string;
  /**
   * The raw signature inside the PKCS#7 (128 hex chars for GOST). The module has
   * always sent it; this field was simply never declared, so `sign()` returned
   * `pkcs7_64` alone and Didox's `/v1/dsvs/timestamp` — which requires both — was
   * unreachable.
   */
  signature_hex?: string;
}

/**
 * A certificate as `list_all_certificates` reports it.
 *
 * Only the first four fields are guaranteed. E-IMZO v6.4.7 sends NOTHING else —
 * the discrete fields below exist on other builds, so they stay optional and take
 * precedence when present, but the alias is the reliable source. See `parseCertificateAlias`.
 */
interface CapiwsCert {
  disk: string;
  path: string;
  name: string;
  alias: string;
  serialNumber?: string;
  validFrom?: string;
  validTo?: string;
  TIN?: string;
  PINFL?: string;
  O?: string;
  CN?: string;
}

/** Subject fields recovered from a certificate `alias`. All optional — see below. */
export interface ParsedCertificateAlias {
  cn?: string;
  org?: string;
  position?: string;
  /** OID 1.2.860.3.16.1.1 — organisation INN/STIR. */
  orgInn?: string;
  /** OID 1.2.860.3.16.1.2 — holder PINFL. */
  pinfl?: string;
  /** UID — the holder's personal INN, NOT the organisation's. */
  personalInn?: string;
  serialNumber?: string;
  validFrom?: string;
  validTo?: string;
}

const ORG_INN_OID = "1.2.860.3.16.1.1";
const PINFL_OID = "1.2.860.3.16.1.2";

/**
 * Unpack the certificate `alias`, which on E-IMZO v6.4.7 is the entire subject DN
 * plus validity, lowercased and comma-joined:
 *
 *   cn=min gunner oletta,1.2.860.3.16.1.2=37357422485008,uid=710975453,
 *   1.2.860.3.16.1.1=562353400,o=ooo treadway inc,t=direktor,
 *   serialnumber=2187131f2,validfrom=2026.08.18 14:55:14,validto=2026.09.17 14:55:14
 *
 * Values arrive LOWERCASED by the module even though the real certificate subject is
 * upper-case; we surface them verbatim rather than inventing a casing rule.
 */
export function parseCertificateAlias(alias: string | undefined): ParsedCertificateAlias {
  const fields: Record<string, string> = {};
  for (const part of (alias ?? "").split(",")) {
    const eq = part.indexOf("=");
    if (eq < 0) continue;
    fields[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
  }
  return {
    cn: fields.cn,
    org: fields.o,
    position: fields.t,
    orgInn: fields[ORG_INN_OID],
    pinfl: fields[PINFL_OID],
    personalInn: fields.uid,
    serialNumber: fields.serialnumber,
    validFrom: fields.validfrom,
    validTo: fields.validto,
  };
}

/**
 * Map raw CAPIWS certificates onto the bridge contract, de-duplicated.
 *
 * The dedup is load-bearing on macOS: the key volume IS `/Volumes/DSKEYS`, so it is
 * both a mount point and a `DSKEYS` subdirectory of `/Volumes`, and
 * `list_all_certificates` merges the two roots with a leaky dedup — one file really
 * does come back twice under different `(disk, path)` pairs. `name + alias` identifies
 * the certificate; `disk`/`path` only say which door we walked through, and either
 * one loads the same key.
 */
export function mapCapiwsCertificates(
  certs: CapiwsCert[],
  store: EimzoStore = "pfx",
): EimzoCertificate[] {
  const seen = new Set<string>();
  const out: EimzoCertificate[] = [];
  for (const cert of certs) {
    const key = `${cert.name}|${cert.alias}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const parsed = parseCertificateAlias(cert.alias);
    const org = cert.O ?? parsed.org;
    const name = cert.CN ?? parsed.cn;
    out.push({
      // `store` and `serialNumber` ride along because ytks.load_key needs both —
      // its signature is (disk, path, name, alias, serialNumber), one more than pfx.
      id: JSON.stringify({
        store,
        disk: cert.disk,
        path: cert.path,
        name: cert.name,
        alias: cert.alias,
        serialNumber: cert.serialNumber ?? parsed.serialNumber,
      }),
      subjectName: [org, name].filter(Boolean).join(" — ") || cert.name,
      tin: cert.TIN ?? parsed.orgInn,
      name,
      org,
      pinfl: cert.PINFL ?? parsed.pinfl,
      personalInn: parsed.personalInn,
      position: parsed.position,
      serialNumber: cert.serialNumber ?? parsed.serialNumber,
      validTo: cert.validTo ?? parsed.validTo,
    });
  }
  return out;
}

type CapiwsCall = CapiwsRequest;

declare global {
  interface Window {
    CAPIWS?: CapiwsApi;
    __EIMZO_BRIDGE__?: EimzoBridge;
  }
}

/** Raw call — resolves whatever the module said, including `{success:false}`. */
function rawCall(api: CapiwsApi, request: CapiwsCall): Promise<CapiwsResult> {
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

/**
 * Checked call. Throws `CapiwsError` when the module reports failure.
 *
 * This used to resolve regardless, so every module-level refusal became a silent
 * empty result: a rejected Origin read as "no certificates", a wrong password as a
 * bare `eimzo_key_load_failed`.
 */
async function call(api: CapiwsApi, request: CapiwsCall): Promise<CapiwsResult> {
  const data = await rawCall(api, request);
  if (data?.success === false) {
    throw new CapiwsError(request.name, data.reason ?? "unknown", data.status);
  }
  return data;
}

/**
 * Register our Origin with the module. Memoised: the module keeps the registration
 * process-wide, so one handshake per page load is enough — until the module
 * restarts, which is what `resetHandshake` is for.
 *
 * **A FAILURE is never memoised.** Caching the rejected promise meant a user who
 * opened the cabinet before starting E-IMZO was told «модуль не найден» for the
 * rest of that page's life: every later attempt re-awaited the same settled
 * failure while the module sat there answering raw calls perfectly. `resetHandshake`
 * did not save them either — it fires only for an api-key REJECTION, never for a
 * transport error. Observed live on 24.08.2026.
 */
let handshakePromise: Promise<void> | null = null;

function handshake(api: CapiwsApi): Promise<void> {
  handshakePromise ??= rawCall(api, {
    name: "apikey",
    arguments: [...EIMZO_API_KEYS],
  })
    .then(() => undefined)
    .catch((err: unknown) => {
      handshakePromise = null;
      throw err;
    });
  return handshakePromise;
}

/** Test seam: the memoisation is the behaviour under test, not an internal. */
export const handshakeForTest = handshake;

export function resetHandshake(): void {
  handshakePromise = null;
}

/**
 * Run `fn`, and if the module rejects our Origin, handshake again and retry once.
 *
 * The retry matters because the registration dies with the module: a user who
 * restarts E-IMZO with the cabinet still open would otherwise be stuck until reload.
 */
async function withHandshake<T>(api: CapiwsApi, fn: () => Promise<T>): Promise<T> {
  await handshake(api);
  try {
    return await fn();
  } catch (err) {
    if (!(err instanceof CapiwsError) || !err.isApiKeyRejection) throw err;
    resetHandshake();
    await handshake(api);
    return fn();
  }
}

/** How a certificate id decodes — see `mapCapiwsCertificates`. */
interface CertHandle {
  store?: EimzoStore;
  disk: string;
  path: string;
  name: string;
  alias: string;
  serialNumber?: string;
}

/** UTF-8 → base64, which is what every `create_pkcs7` argument must be. */
function toBase64(text: string): string {
  return window.btoa(unescape(encodeURIComponent(text)));
}

export class CapiwsBridge implements EimzoBridge {
  /**
   * The transport, installed on first use.
   *
   * This is the line that was missing: `window.CAPIWS` is not set by anything
   * else in the app, so before `ensureCapiwsInstalled` this getter returned
   * `undefined` forever and every signing attempt reported "module missing".
   * Installing lazily (rather than from `index.html`) keeps SSR away from
   * `window`.
   */
  private get api(): CapiwsApi | undefined {
    return ensureCapiwsInstalled();
  }

  /**
   * Is the module reachable?
   *
   * True as soon as it ANSWERS — a `CapiwsError` means it is running and talking,
   * just refusing this request, and reporting that as "module missing" would send
   * the user to install software they already have. Only an absent `window.CAPIWS`
   * or a dead socket is a missing module.
   */
  async probe(): Promise<boolean> {
    const api = this.api;
    if (!api) return false;
    try {
      await withHandshake(api, () =>
        call(api, { plugin: "pfx", name: "list_all_certificates" }),
      );
      return true;
    } catch (err) {
      return err instanceof CapiwsError;
    }
  }

  /**
   * Certificates from BOTH file stores.
   *
   * `ytks` is a real E-IMZO key format; listing only `pfx` left those users staring
   * at an empty picker. One store failing is tolerated (not every build ships both),
   * but if both fail the error propagates — an empty list must mean "no keys", never
   * "we could not ask".
   */
  async listCertificates(): Promise<EimzoCertificate[]> {
    const api = this.api;
    if (!api) return [];
    const stores: EimzoStore[] = ["pfx", "ytks"];
    const results = await Promise.allSettled(
      stores.map((store) =>
        withHandshake(api, () =>
          call(api, { plugin: store, name: "list_all_certificates" }),
        ).then((data) => mapCapiwsCertificates(data.certificates ?? [], store)),
      ),
    );
    const firstFailure = results.find((r) => r.status === "rejected");
    if (firstFailure && results.every((r) => r.status === "rejected")) {
      throw firstFailure.reason;
    }

    const seen = new Set<string>();
    const out: EimzoCertificate[] = [];
    for (const result of results) {
      if (result.status !== "fulfilled") continue;
      for (const cert of result.value) {
        const { name, alias } = JSON.parse(cert.id) as { name: string; alias: string };
        const key = `${name}|${alias}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(cert);
      }
    }
    return out;
  }

  /**
   * Hold one key open across several signatures.
   *
   * `load_key` is the call that opens the native password dialog, so signing
   * twice through `sign()` prompts twice for the same key. The Didox rail does
   * exactly that — one signature over the INN to mint a session, another over the
   * document — and two dialogs for one user action reads as a bug.
   */
  async openSession(certId: string): Promise<EimzoKeySession> {
    const api = this.api;
    if (!api) throw new Error("eimzo_module_unavailable");
    const { store, disk, path, name, alias, serialNumber } = JSON.parse(certId) as CertHandle;
    const plugin: EimzoStore = store ?? "pfx";
    // ytks.load_key takes a fifth argument; pfx.load_key does not.
    const loadArgs =
      plugin === "ytks" ? [disk, path, name, alias, serialNumber ?? ""] : [disk, path, name, alias];

    // Opens a NATIVE password dialog and blocks until the user answers it.
    const loaded = await withHandshake(api, () =>
      call(api, { plugin, name: "load_key", arguments: loadArgs }),
    );
    if (!loaded.keyId) throw new Error("eimzo_key_load_failed");
    const keyId = loaded.keyId;

    const signBase64 = async (dataB64: string): Promise<EimzoSignature> => {
      // 'no' embeds the signed content, so a verifier can echo it back and match
      // it against what it expected.
      const signed = await call(api, {
        plugin: "pkcs7",
        name: "create_pkcs7",
        arguments: [dataB64, keyId, "no"],
      });
      if (!signed.pkcs7_64) throw new Error("eimzo_sign_failed");
      return {
        pkcs7_64: signed.pkcs7_64,
        // Absent on no build we have seen, but a missing hex would surface far
        // away as an opaque Didox rejection, so it degrades to "" here instead of
        // `undefined` leaking into a request body.
        signature_hex: signed.signature_hex ?? "",
      };
    };

    return {
      signBase64,
      sign: (challenge: string) => signBase64(toBase64(challenge)),
      async close(): Promise<void> {
        // Best effort: a failed unload must never turn a completed signature into
        // an error. The module would drop the key on its own eventually anyway.
        await rawCall(api, { plugin, name: "unload_key", arguments: [keyId] }).catch(() => {});
      },
    };
  }

  async sign(certId: string, challenge: string): Promise<EimzoSignature> {
    const session = await this.openSession(certId);
    try {
      return await session.sign(challenge);
    } finally {
      void session.close();
    }
  }

  async signBase64(certId: string, dataB64: string): Promise<EimzoSignature> {
    const session = await this.openSession(certId);
    try {
      return await session.signBase64(dataB64);
    } finally {
      void session.close();
    }
  }
}
