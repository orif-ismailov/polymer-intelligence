/**
 * CAPIWS API-key table.
 *
 * The E-IMZO module authorises callers by **browser Origin**. Before any plugin
 * call it expects `CAPIWS.apikey([domain, key, domain, key, …])`; a domain with no
 * registered key gets `API-key для домена <d> недействителен` on every subsequent
 * call — which, before this file existed, the portal surfaced as "you have no
 * certificates".
 *
 * The registration lives in the MODULE PROCESS, not the page, so it is sticky: once
 * any tab has handshaken, others ride free until the module restarts. That is why
 * this was easy to miss in dev — an E-IMZO page open in another tab covers you.
 *
 * These keys are NOT secrets. Every E-IMZO-enabled site ships its own in plain
 * JavaScript; the module verifies the pair, so a key is useless on another domain.
 *
 * The three below are the public development pairs E-IMZO itself publishes (they
 * are in the module's own `apidoc.html`, and on macOS in `defaults read uz.yt.eimzo`).
 * They cover `localhost` and `127.0.0.1`, i.e. `npm run dev` and Playwright.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * PRODUCTION: `cabinet.ai-imex.com` is NOT registered with E-IMZO yet, so signing
 * cannot work there. The key has to be ISSUED by E-IMZO for that exact origin — it
 * cannot be generated locally. Once obtained, append the pair to `EIMZO_API_KEYS`
 * (domain first, key second). Until then the bridge fails with a distinct
 * `module_not_authorized` error instead of pretending the user has no certificates.
 * ─────────────────────────────────────────────────────────────────────────────
 */
export const EIMZO_API_KEYS: readonly string[] = [
  "localhost",
  "96D0C1491615C82B9A54D9989779DF825B690748224C2B04F500F370D51827CE2644D8D4A82C18184D73AB8530BB8ED537269603F61DB0D03D2104ABF789970B",
  "127.0.0.1",
  "A7BCFA5D490B351BE0754130DF03A068F855DB4333D43921125B9CF2670EF6A40370C646B90401955E1F7BC9CDBF59CE0B2C5467D820BE189C845D0B79CFC96F",
  "null",
  "E0A205EC4E7B78BBB56AFF83A733A1BB9FD39D562E67978CC5E7D73B0951DB1954595A20672A63332535E13CC6EC1E1FC8857BB09E0855D7E76E411B6FA16E9D",
];

/**
 * The module's status code for "this Origin has no valid API-key".
 * Observed verbatim on v6.4.7:
 *   {"success":false,"status":-1022,"reason":"API-key для домена null недействителен."}
 */
export const API_KEY_REJECTED_STATUS = -1022;

/**
 * True when the module refused our Origin rather than failing for a real reason.
 *
 * Prefer the status code: `reason` is a user-facing string and the module can be
 * switched to another language at runtime (`app.change_ui_lang`), so matching on
 * Russian text alone would quietly stop working. The text check stays as a fallback
 * for builds that do not send the code.
 */
export function isApiKeyRejection(reason: string | undefined, status?: number): boolean {
  if (status === API_KEY_REJECTED_STATUS) return true;
  return /api-?key/i.test(reason ?? "");
}
