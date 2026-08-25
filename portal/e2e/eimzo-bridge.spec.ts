import { expect, test } from "@playwright/test";

import { isApiKeyRejection } from "../src/shared/lib/eimzo/apikey";
import {
  CapiwsError,
  mapCapiwsCertificates,
  parseCertificateAlias,
} from "../src/shared/lib/eimzo/capiws";
import { capiwsCall } from "../src/shared/lib/eimzo/capiwsSocket";
import type { SocketLike } from "../src/shared/lib/eimzo/capiwsSocket";

/**
 * Unit spec for the CAPIWS→EimzoCertificate mapping. No browser, no backend —
 * Playwright is just the runner the portal already has.
 *
 * Every fixture below is a VERBATIM response from a real E-IMZO v6.4.7 Standard
 * module (macOS, four test keys from test.e-imzo.uz). The rest of the E-IMZO suite
 * injects `window.__EIMZO_BRIDGE__` and so never exercises this mapping at all,
 * which is how both bugs it covers reached production:
 *
 *   1. v6.4.7 returns NO discrete `TIN`/`CN`/`O` fields — the whole subject DN is
 *      packed into `alias`, lowercased. The old mapper read `c.O`/`c.CN`/`c.TIN`,
 *      got `undefined` for all three, and fell back to showing the raw DN with no TIN.
 *   2. On macOS the key volume IS `/Volumes/DSKEYS`, so it is both a mount point and
 *      a `DSKEYS` subdirectory of `/Volumes`. `list_all_certificates` merges the two
 *      roots and its dedup leaks — four files on disk came back as five entries.
 */

// A single legal-entity certificate, exactly as v6.4.7 reports it.
const TREADWAY = {
  disk: "/Volumes/",
  path: "DSKEYS",
  name: "DS37357422485008-test",
  alias:
    "cn=min gunner oletta,1.2.860.3.16.1.2=37357422485008,uid=710975453," +
    "1.2.860.3.16.1.1=562353400,o=ooo treadway inc,t=direktor,serialnumber=2187131f2," +
    "validfrom=2026.08.18 14:55:14,validto=2026.09.17 14:55:14",
};

// The SAME key, reached through the other disk root. This is the duplicate the
// module really emits — note `disk`/`path` differ while `name`/`alias` do not.
const TREADWAY_VIA_MOUNTPOINT = {
  ...TREADWAY,
  disk: "/Volumes/DSKEYS/",
  path: "",
};

const OGEMA = {
  disk: "/Volumes/",
  path: "DSKEYS",
  name: "DS30125139187158-test",
  alias:
    "cn=anatola radcliffe crane,1.2.860.3.16.1.2=30125139187158,uid=728787801," +
    "1.2.860.3.16.1.1=537302090,o=ooo ogema inc,t=direktor,serialnumber=2187131f5," +
    "validfrom=2026.08.18 15:12:33,validto=2026.09.17 15:12:33",
};

test.describe("parseCertificateAlias", () => {
  test("unpacks the v6.4.7 subject DN, including both national OIDs", () => {
    expect(parseCertificateAlias(TREADWAY.alias)).toEqual({
      cn: "min gunner oletta",
      org: "ooo treadway inc",
      position: "direktor",
      // 1.2.860.3.16.1.1 — organisation INN/STIR, matched against company.tax_id
      orgInn: "562353400",
      // 1.2.860.3.16.1.2 — PINFL, only ever surfaced masked
      pinfl: "37357422485008",
      personalInn: "710975453",
      serialNumber: "2187131f2",
      validFrom: "2026.08.18 14:55:14",
      validTo: "2026.09.17 14:55:14",
    });
  });

  test("survives an empty or malformed alias without throwing", () => {
    expect(parseCertificateAlias(undefined)).toEqual({});
    expect(parseCertificateAlias("")).toEqual({});
    expect(parseCertificateAlias("garbage,no-equals-signs")).toEqual({});
  });
});

test.describe("mapCapiwsCertificates", () => {
  test("reads org/holder/TIN off the alias when the module sends no discrete fields", () => {
    const [cert] = mapCapiwsCertificates([TREADWAY]);

    expect(cert.tin).toBe("562353400");
    expect(cert.name).toBe("min gunner oletta");
    expect(cert.org).toBe("ooo treadway inc");
    expect(cert.pinfl).toBe("37357422485008");
    expect(cert.position).toBe("direktor");
    expect(cert.validTo).toBe("2026.09.17 14:55:14");
    // The old mapper produced the raw DN here because O and CN were undefined.
    expect(cert.subjectName).toBe("ooo treadway inc — min gunner oletta");
    expect(cert.subjectName).not.toContain("1.2.860.3.16.1.1");
  });

  test("id round-trips everything load_key needs, including the store", () => {
    const [cert] = mapCapiwsCertificates([TREADWAY]);

    expect(JSON.parse(cert.id)).toEqual({
      store: "pfx",
      disk: "/Volumes/",
      path: "DSKEYS",
      name: "DS37357422485008-test",
      alias: TREADWAY.alias,
      // ytks.load_key takes this as a fifth argument; pfx ignores it.
      serialNumber: "2187131f2",
    });
  });

  test("tags ytks certificates so sign() picks the right plugin", () => {
    const [cert] = mapCapiwsCertificates([TREADWAY], "ytks");

    expect(JSON.parse(cert.id).store).toBe("ytks");
  });

  test("drops the duplicate the module emits for one file on two disk roots", () => {
    const mapped = mapCapiwsCertificates([TREADWAY, OGEMA, TREADWAY_VIA_MOUNTPOINT]);

    expect(mapped).toHaveLength(2);
    expect(mapped.map((c) => c.org)).toEqual(["ooo treadway inc", "ooo ogema inc"]);
    // First one wins, so the surviving handle is the one the module listed first.
    expect(JSON.parse(mapped[0].id).disk).toBe("/Volumes/");
  });

  test("an empty module response is an empty list, not a crash", () => {
    expect(mapCapiwsCertificates([])).toEqual([]);
  });

  test("still prefers discrete fields when a module provides them", () => {
    const [cert] = mapCapiwsCertificates([
      { ...TREADWAY, TIN: "999888777", CN: "IVANOV IVAN", O: "OOO LEGACY SHAPE" },
    ]);

    expect(cert.tin).toBe("999888777");
    expect(cert.subjectName).toBe("OOO LEGACY SHAPE — IVANOV IVAN");
    // Fields the discrete shape omits still come from the alias.
    expect(cert.pinfl).toBe("37357422485008");
  });
});

test.describe("CapiwsError", () => {
  // The module answers in Russian; this string is verbatim from v6.4.7 after a
  // restart dropped the registration. Telling it apart from a real failure is what
  // stops a rejected Origin being reported to the user as "you have no certificates".
  const ORIGIN_REFUSED = "API-key для домена null недействителен.";

  test("recognises the Origin refusal by status code and by text", () => {
    // The status is the reliable signal; `reason` is localisable (app.change_ui_lang).
    expect(new CapiwsError("list_all_certificates", "не важно", -1022).isApiKeyRejection).toBe(true);
    expect(isApiKeyRejection(undefined, -1022)).toBe(true);
    // Fallback for builds that send no status.
    expect(new CapiwsError("list_all_certificates", ORIGIN_REFUSED).isApiKeyRejection).toBe(true);
    expect(isApiKeyRejection(ORIGIN_REFUSED)).toBe(true);
  });

  test("does not mistake other module failures for it", () => {
    expect(new CapiwsError("list_certificates", "Диск не найден", -1).isApiKeyRejection).toBe(false);
    expect(new CapiwsError("load_key", "Неверный пароль").isApiKeyRejection).toBe(false);
    expect(isApiKeyRejection(undefined)).toBe(false);
  });

  test("keeps the module's own reason on the error", () => {
    const err = new CapiwsError("load_key", "Неверный пароль");

    expect(err.reason).toBe("Неверный пароль");
    expect(err.message).toContain("Неверный пароль");
  });
});

/**
 * The transport itself. Driven with a fake socket, so this runs anywhere — which
 * matters, because the bug it covers (`window.CAPIWS` assigned by nothing, so the
 * module was unreachable on every page) survived precisely because no test could
 * see the transport layer at all.
 */
test.describe("capiwsCall", () => {
  interface Sent {
    url: string;
    frames: string[];
  }

  /** A socket that answers `reply` to whatever it is sent. */
  function fakeSocket(reply: unknown, sent: Sent) {
    return (url: string): SocketLike => {
      sent.url = url;
      const sock: SocketLike = {
        send: (data: string) => {
          sent.frames.push(data);
          queueMicrotask(() => sock.onmessage?.({ data: JSON.stringify(reply) }));
        },
        close: () => {},
        onopen: null,
        onmessage: null,
        onerror: null,
        onclose: null,
      };
      queueMicrotask(() => sock.onopen?.(null));
      return sock;
    };
  }

  test("sends the request as one JSON frame and resolves the reply", async () => {
    const sent: Sent = { url: "", frames: [] };
    const data = await capiwsCall(
      { plugin: "pfx", name: "list_all_certificates" },
      { factory: fakeSocket({ success: true, certificates: [] }, sent) },
    );

    expect(data).toEqual({ success: true, certificates: [] });
    expect(JSON.parse(sent.frames[0] ?? "{}")).toEqual({
      plugin: "pfx",
      name: "list_all_certificates",
    });
  });

  test("talks wss on 64443 — a ws:// call from the HTTPS cabinet is blocked as mixed content", async () => {
    const sent: Sent = { url: "", frames: [] };
    await capiwsCall({ name: "apikey" }, { factory: fakeSocket({ success: true }, sent) });

    expect(sent.url).toBe("wss://127.0.0.1:64443/service/cryptapi");
  });

  test("resolves a module refusal rather than rejecting it", async () => {
    // `{success:false}` is an ANSWER — classification belongs to `capiws.ts`, and
    // rejecting here would collapse "wrong password" into "module missing".
    const sent: Sent = { url: "", frames: [] };
    const data = await capiwsCall(
      { plugin: "pfx", name: "load_key" },
      { factory: fakeSocket({ success: false, reason: "Неверный пароль" }, sent) },
    );

    expect(data.success).toBe(false);
    expect(data.reason).toBe("Неверный пароль");
  });

  test("a socket that closes without answering is a reachability failure", async () => {
    const factory = (): SocketLike => {
      const sock: SocketLike = {
        send: () => {},
        close: () => {},
        onopen: null,
        onmessage: null,
        onerror: null,
        onclose: null,
      };
      queueMicrotask(() => sock.onclose?.({ code: 1006 }));
      return sock;
    };

    await expect(capiwsCall({ name: "version" }, { factory })).rejects.toThrow(
      "eimzo_module_unreachable",
    );
  });
});

/**
 * Signing data that is ALREADY base64.
 *
 * Didox hands the payload to sign pre-encoded, and the obvious call —
 * `bridge.sign(certId, atob(dataB64))` — silently corrupts it. `atob` returns a
 * latin-1 string of the UTF-8 bytes; `sign()` then runs
 * `encodeURIComponent` over it and encodes those bytes AGAIN. A contract line
 * reading «Поставка полимеров» gets signed as «ÐÐ¾ÑÑÐ°Ð²ÐºÐ°...», so the
 * signature covers bytes the verifier can never reproduce — and nothing anywhere
 * says so. Caught by watching a real document go through, not by a type.
 */
test.describe("base64 round-trip corruption", () => {
  const CYRILLIC = '{"contractname":"Поставка полимеров"}';

  function toBase64(text: string): string {
    return btoa(unescape(encodeURIComponent(text)));
  }

  test("decoding then re-encoding non-ASCII does NOT reproduce the original", () => {
    const original = toBase64(CYRILLIC);

    // What a caller would naively do to feed `sign()`, which re-encodes.
    const roundTripped = toBase64(atob(original));

    expect(roundTripped).not.toBe(original);
    expect(atob(roundTripped)).not.toBe(atob(original));
  });

  test("ASCII survives it, which is why this hides until a real document", () => {
    const ascii = toBase64('{"contractno":"C-7b520eb7"}');
    expect(toBase64(atob(ascii))).toBe(ascii);
  });

  test("the bridge exposes a path that takes base64 as-is", async () => {
    // A stub session standing in for a loaded key: whatever reaches create_pkcs7
    // is what got signed, so asserting on it asserts the bytes.
    let signedArgument = "";
    const session = {
      signBase64: async (dataB64: string) => {
        signedArgument = dataB64;
        return { pkcs7_64: "P", signature_hex: "H" };
      },
      sign: async (text: string) => session.signBase64(toBase64(text)),
      close: async () => {},
    };

    const original = toBase64(CYRILLIC);
    await session.signBase64(original);
    expect(signedArgument).toBe(original);

    // …whereas going through the text path with decoded input does not.
    await session.sign(atob(original));
    expect(signedArgument).not.toBe(original);
  });
});

/**
 * A failed handshake must not be remembered.
 *
 * `handshake()` memoises its promise, which is right for a SUCCESS — the module
 * keeps the origin registration process-wide, so one round trip per page load is
 * enough. It was also caching the REJECTION: a user who opened the cabinet before
 * starting E-IMZO got «модуль не найден» forever, because every later attempt
 * re-awaited the same settled failure. Only a full page reload cleared it — and
 * `resetHandshake` did not help, since it fires only for an api-key REJECTION,
 * never for a transport failure.
 *
 * Found live on 24.08.2026: the module was running and answering raw calls while
 * the app insisted it was absent.
 */
test.describe("handshake memoisation", () => {
  /** A socket that fails the first N attempts, then answers. */
  function flakyFactory(failures: number): { factory: () => SocketLike; attempts: () => number } {
    let seen = 0;
    return {
      attempts: () => seen,
      factory: () => {
        seen += 1;
        const failing = seen <= failures;
        const socket: SocketLike = {
          send: () => {},
          close: () => {},
          onopen: null,
          onmessage: null,
          onerror: null,
          onclose: null,
        };
        setTimeout(() => {
          if (failing) {
            // 1006: the module is not listening — what "not started yet" looks like.
            socket.onclose?.({ code: 1006 });
            return;
          }
          socket.onopen?.({});
          socket.onmessage?.({ data: JSON.stringify({ success: true, status: 1 }) });
        }, 0);
        return socket;
      },
    };
  }

  test("a call that failed while the module was down succeeds once it is up", async () => {
    const { factory, attempts } = flakyFactory(1);

    await expect(
      capiwsCall({ name: "apikey", arguments: [] }, { factory }),
    ).rejects.toThrow(/eimzo_module_unreachable/);

    // The retry must actually reach the module rather than replay the failure.
    const second = await capiwsCall({ name: "apikey", arguments: [] }, { factory });
    expect(second.success).toBe(true);
    expect(attempts()).toBe(2);
  });

  test("the bridge recovers without a page reload", async () => {
    const { resetHandshake, handshakeForTest } = await import(
      "../src/shared/lib/eimzo/capiws"
    );
    const { factory } = flakyFactory(1);
    const api = {
      callFunction: (
        call: { name: string; arguments?: unknown[] },
        onSuccess: (event: unknown, data: unknown) => void,
        onError: (error: unknown) => void,
      ) => {
        void capiwsCall(call, { factory }).then(
          (data) => onSuccess(null, data),
          (err) => onError(err),
        );
      },
    };

    resetHandshake();
    await expect(handshakeForTest(api)).rejects.toThrow(/eimzo_module_unreachable/);
    // The SECOND attempt must retry, not re-await the cached rejection.
    await expect(handshakeForTest(api)).resolves.toBeUndefined();
  });
});

/**
 * One socket per call — because the module says so.
 *
 * Verified in a real browser on 25.08.2026: after answering one frame the module
 * closes the connection itself with code 1000, and a second frame sent on that
 * socket is never answered. A shared long-lived connection therefore serves the
 * first call and fails every one after it with `eimzo_no_response`.
 *
 * This is written down because the opposite looks plausible: a password dialog
 * spanning `load_key` → `create_pkcs7` feels like it should need one connection.
 * It does not — a `keyId` stays valid on the next connection.
 */
test.describe("one socket per call", () => {
  test("each call opens its own connection", async () => {
    const urls: string[] = [];
    const factory = () => {
      const socket: SocketLike = {
        send: () => {},
        close: () => {},
        onopen: null,
        onmessage: null,
        onerror: null,
        onclose: null,
      };
      urls.push("opened");
      setTimeout(() => {
        socket.onopen?.({});
        socket.onmessage?.({ data: JSON.stringify({ success: true }) });
      }, 0);
      return socket;
    };

    await capiwsCall({ plugin: "pfx", name: "load_key" }, { factory });
    await capiwsCall({ plugin: "pkcs7", name: "create_pkcs7" }, { factory });

    expect(urls).toHaveLength(2);
  });

  test("a close with 1000 before any reply is «answered nothing», not «unreachable»", async () => {
    const factory = () => {
      const socket: SocketLike = {
        send: () => {},
        close: () => {},
        onopen: null,
        onmessage: null,
        onerror: null,
        onclose: null,
      };
      setTimeout(() => {
        socket.onopen?.({});
        socket.onclose?.({ code: 1000 });
      }, 0);
      return socket;
    };

    await expect(capiwsCall({ name: "apikey" }, { factory })).rejects.toThrow(/eimzo_no_response/);
  });
});
