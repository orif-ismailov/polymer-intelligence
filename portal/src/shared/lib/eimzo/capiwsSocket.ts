/**
 * The CAPIWS transport — a WebSocket client for the local E-IMZO desktop module.
 *
 * ## Why this file exists
 *
 * `capiws.ts` has always read `window.CAPIWS`, and **nothing in this repository
 * ever assigned it.** E-IMZO publishes an `e-imzo.js` that installs the global,
 * but the portal never loaded it, so `CapiwsBridge.api` was `undefined` on every
 * page, `probe()` returned false, and every user — R3 contract signing included —
 * saw "module missing" while the module was sitting there running. This is that
 * missing half, written rather than imported.
 *
 * ## Why write it instead of loading theirs
 *
 * A page whose whole job is to operate the user's private signing key should not
 * pull a third-party script to do it. The protocol is small and fully specified,
 * and owning it means the transport is injectable — the spec drives it with a fake
 * socket, no desktop module required.
 *
 * ## The protocol
 *
 * One call = one socket. Connect, send a JSON frame, read one JSON frame back.
 * **The module then closes the connection itself** — verified in the browser on
 * 25.08.2026: a second frame on the same socket is never answered, and the close
 * arrives with code 1000 right after the first reply. So this is not a style
 * choice and not something to "optimise" into a shared connection; a shared one
 * answers the first call and then fails every later call with `eimzo_no_response`.
 *
 *   → {"plugin":"pfx","name":"list_all_certificates"}
 *   ← {"success":true,"certificates":[…]}
 *   ← close 1000
 *
 * Meta calls (`apikey`, `version`, `apidoc`) carry no `plugin`. A `keyId` from
 * `load_key` stays valid on the NEXT connection, which is what makes signing work
 * at all.
 *
 * `wss://` on 64443 is not a preference: the cabinet is served over HTTPS, and a
 * browser refuses a `ws://` connection from a secure page as mixed content. The
 * module also listens on plain `ws://127.0.0.1:64646`, which is why the CLI driver
 * in `.claude/skills/eimzo` uses that one — it is not in a browser.
 */

const CAPIWS_URL = "wss://127.0.0.1:64443/service/cryptapi";

/** Ordinary calls. Generous, because the module is a desktop app, not a server. */
const DEFAULT_TIMEOUT_MS = 15_000;

/**
 * Calls that open a NATIVE dialog and block on a human: `load_key` asks for the
 * store password, and `create_pkcs7` re-asks on some builds. Fifteen seconds is
 * not enough time to find the window, read it and type — a timeout here reads to
 * the user as "signing is broken" when they simply had not finished typing.
 */
const DIALOG_TIMEOUT_MS = 180_000;

/** Function names that may block on a person. */
const DIALOG_CALLS = new Set(["load_key", "create_pkcs7", "generate_keypair", "save_temporary_pfx"]);

export interface CapiwsRequest {
  /** Omitted for the meta calls (`apikey`, `version`, `apidoc`). */
  plugin?: string;
  name: string;
  arguments?: string[];
}

export interface CapiwsResponse {
  success?: boolean;
  reason?: string;
  status?: number;
  [key: string]: unknown;
}

/** Minimal structural type so a test can pass a fake without a DOM. */
export interface SocketLike {
  send(data: string): void;
  close(): void;
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onclose: ((event: { code?: number }) => void) | null;
}

export type SocketFactory = (url: string) => SocketLike;

function defaultFactory(url: string): SocketLike {
  return new WebSocket(url) as unknown as SocketLike;
}

/**
 * Perform one CAPIWS call.
 *
 * Resolves with whatever the module said — including `{success:false}`, which is a
 * legitimate answer (wrong password, refused Origin) and is classified upstream in
 * `capiws.ts`. Rejects only when we never got an answer at all.
 */
export function capiwsCall(
  request: CapiwsRequest,
  options: { factory?: SocketFactory; timeoutMs?: number } = {},
): Promise<CapiwsResponse> {
  const factory = options.factory ?? defaultFactory;
  const timeoutMs =
    options.timeoutMs ?? (DIALOG_CALLS.has(request.name) ? DIALOG_TIMEOUT_MS : DEFAULT_TIMEOUT_MS);

  return new Promise<CapiwsResponse>((resolve, reject) => {
    let socket: SocketLike;
    try {
      socket = factory(CAPIWS_URL);
    } catch (err) {
      reject(new Error(`eimzo_socket_open_failed: ${String(err)}`));
      return;
    }

    let settled = false;
    const finish = (fn: () => void): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {
        socket.close();
      } catch {
        /* already closing */
      }
      fn();
    };

    const timer = setTimeout(
      () => finish(() => reject(new Error("eimzo_timeout"))),
      timeoutMs,
    );

    socket.onopen = () => {
      try {
        socket.send(JSON.stringify(request));
      } catch (err) {
        finish(() => reject(new Error(`eimzo_send_failed: ${String(err)}`)));
      }
    };

    socket.onmessage = (event) => {
      try {
        finish(() => resolve(JSON.parse(String(event.data)) as CapiwsResponse));
      } catch {
        finish(() => reject(new Error("eimzo_bad_response")));
      }
    };

    // `onerror` carries no usable detail in any browser; the close code is the
    // only signal, so the real diagnosis happens in `onclose`.
    socket.onerror = () => {};

    socket.onclose = (event) => {
      // A clean close before any message means the module accepted the connection
      // and then said nothing — distinct from never connecting at all, which is
      // what "not installed / not running" looks like. (After a reply the module
      // closes with 1000 too, but `finish` has already settled by then.)
      const reason =
        event?.code === 1000 ? "eimzo_no_response" : "eimzo_module_unreachable";
      finish(() => reject(new Error(reason)));
    };
  });
}

/** The shape `capiws.ts` consumes — deliberately identical to E-IMZO's own global. */
export interface CapiwsApi {
  callFunction(
    call: CapiwsRequest,
    onSuccess: (event: unknown, data: CapiwsResponse) => void,
    onError: (error: unknown) => void,
  ): void;
}

/** Adapt the promise transport onto E-IMZO's callback-shaped API. */
export function createCapiwsApi(factory?: SocketFactory): CapiwsApi {
  return {
    callFunction(call, onSuccess, onError) {
      capiwsCall(call, { factory }).then(
        (data) => onSuccess(null, data),
        (err) => onError(err),
      );
    },
  };
}

/**
 * Install the transport on `window.CAPIWS`, unless something already did.
 *
 * Idempotent, and deliberately called lazily from `getEimzoBridge()` rather than
 * from `index.html` or a module top level: this app server-renders, and touching
 * `window` during SSR throws. It also defers the whole thing until someone
 * actually signs, which is the only time the module matters.
 *
 * If E-IMZO's own `e-imzo.js` is present (an operator may add it), that one wins —
 * it is the vendor's, and two clients on one socket would be worse than either.
 */
export function ensureCapiwsInstalled(): CapiwsApi | undefined {
  if (typeof window === "undefined") return undefined;
  const existing = (window as { CAPIWS?: CapiwsApi }).CAPIWS;
  if (existing) return existing;
  const api = createCapiwsApi();
  (window as { CAPIWS?: CapiwsApi }).CAPIWS = api;
  return api;
}
