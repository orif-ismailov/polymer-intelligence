#!/usr/bin/env node
/**
 * capiws.mjs — a zero-dependency CLI driver for the LOCAL E-IMZO desktop module.
 *
 * E-IMZO exposes its whole crypto API over a WebSocket ("CAPIWS") served by the
 * installed desktop app. Browsers reach it through e-imzo.js; there is no HTTP
 * surface and no official CLI, so this file is the handle an agent gets on it.
 *
 * Protocol (from the shipped e-imzo.js, verified live against v6.4.7 Standard):
 *   - endpoint   ws://127.0.0.1:64646/service/cryptapi   (plaintext, preferred)
 *                wss://127.0.0.1:64443/service/cryptapi  (TLS, self-signed cert)
 *   - ONE request per socket: open -> send one JSON -> read one JSON -> close.
 *     There is no multiplexing and no request id. Reusing a socket hangs.
 *   - request  {plugin, name, arguments:[...]}  (all arguments are STRINGS)
 *     or a bare meta call {name:'version'|'apidoc'|'apikey'}.
 *   - response {success:bool, status:int, ...payload}  — on failure, {reason}.
 *
 * Requires Node >= 22 (global WebSocket). Verified on Node v24.11.1 / macOS.
 *
 * Usage:  node .claude/skills/eimzo/capiws.mjs <command> [options]
 *         node .claude/skills/eimzo/capiws.mjs help
 */

const WSS = 'wss://127.0.0.1:64443/service/cryptapi';
const WS = 'ws://127.0.0.1:64646/service/cryptapi';

// `apikey` registers the calling ORIGIN against this table for the lifetime of the
// MODULE PROCESS. A Node client sends no Origin, so it lands on the 'null' entry.
//
// It is genuinely REQUIRED: without it every plugin call fails with
// "API-key для домена null недействителен". It only *looks* optional because any
// client that already handshook (a browser tab on an E-IMZO page, an earlier run of
// this driver) has registered the domain process-wide — so the next caller gets a
// free ride until the module restarts. `handshake()` below does it once per process.
//
// The full table also lives in the module's own prefs (macOS:
// `defaults read uz.yt.eimzo`), which is where to look for a domain not listed here.
const API_KEYS = [
  'localhost',
  '96D0C1491615C82B9A54D9989779DF825B690748224C2B04F500F370D51827CE2644D8D4A82C18184D73AB8530BB8ED537269603F61DB0D03D2104ABF789970B',
  '127.0.0.1',
  'A7BCFA5D490B351BE0754130DF03A068F855DB4333D43921125B9CF2670EF6A40370C646B90401955E1F7BC9CDBF59CE0B2C5467D820BE189C845D0B79CFC96F',
  'null',
  'E0A205EC4E7B78BBB56AFF83A733A1BB9FD39D562E67978CC5E7D73B0951DB1954595A20672A63332535E13CC6EC1E1FC8857BB09E0855D7E76E411B6FA16E9D',
];

// Default per-call ceiling. Anything that pops a NATIVE dialog (load_key asks for
// the store password; generate_keypair/save_temporary_pfx confirm on-screen) can
// sit here indefinitely — those calls pass their own, much larger, timeout.
const DEFAULT_TIMEOUT_MS = 15_000;
const DIALOG_TIMEOUT_MS = 180_000;

let ENDPOINT = WS;
let VERBOSE = false;

/** One CAPIWS call = one socket. Resolves the parsed response object. */
function raw(payload, timeoutMs = DEFAULT_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    let ws;
    try {
      ws = new WebSocket(ENDPOINT);
    } catch (err) {
      reject(new Error(`cannot open ${ENDPOINT}: ${err.message}`));
      return;
    }
    let settled = false;
    const done = (fn, arg) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try { ws.close(); } catch { /* already closing */ }
      fn(arg);
    };
    const timer = setTimeout(
      () => done(reject, new Error(`timeout after ${timeoutMs}ms — is a native E-IMZO dialog waiting on screen?`)),
      timeoutMs,
    );
    if (VERBOSE) process.stderr.write(`→ ${JSON.stringify(payload)}\n`);
    ws.onopen = () => ws.send(JSON.stringify(payload));
    ws.onmessage = (ev) => {
      if (VERBOSE) process.stderr.write(`← ${String(ev.data).slice(0, 400)}\n`);
      try { done(resolve, JSON.parse(ev.data)); } catch (err) { done(reject, err); }
    };
    // `onerror` fires without a usable message; the close code carries the signal.
    ws.onerror = () => {};
    ws.onclose = (ev) => {
      if (ev.code === 1000) {
        done(reject, new Error('module closed the socket without answering'));
      } else {
        done(reject, new Error(`socket closed (code ${ev.code}) — is E-IMZO running? open -a E-IMZO`));
      }
    };
  });
}

/** Register our origin with the module. Idempotent, once per process. */
let _handshook = null;
function handshake() {
  if (_handshook === null) _handshook = raw({ name: 'apikey', arguments: API_KEYS }, 8000).catch(() => null);
  return _handshook;
}

/** raw() + the success check. Throws the module's own `reason` on failure. */
async function call(plugin, name, args = [], timeoutMs = DEFAULT_TIMEOUT_MS) {
  if (plugin) await handshake();
  const payload = plugin ? { plugin, name, arguments: args.map(String) } : { name };
  const data = await raw(payload, timeoutMs);
  if (data && data.success === false) {
    throw new Error(`${plugin ? plugin + '.' : ''}${name} failed: ${data.reason || 'unknown reason'}`);
  }
  return data;
}

/**
 * Parse the certificate `alias`, which is the whole subject DN plus validity,
 * lowercased and comma-joined:
 *
 *   cn=min gunner oletta,1.2.860.3.16.1.2=37357422485008,uid=710975453,
 *   1.2.860.3.16.1.1=562353400,o=ooo treadway inc,t=direktor,
 *   serialnumber=2187131f2,validfrom=2026.08.18 14:55:14,validto=…
 *
 * v6.4.7 does NOT return the discrete `TIN`/`CN`/`O` fields older integrations
 * (including this repo's portal bridge) expect — everything is in here.
 * The two national OIDs are the ones that matter:
 *   1.2.860.3.16.1.1 = organisation INN/STIR   ← matched against company.tax_id
 *   1.2.860.3.16.1.2 = PINFL (personal id)
 */
function parseAlias(alias) {
  const out = {};
  if (!alias) return out;
  for (const part of alias.split(',')) {
    const eq = part.indexOf('=');
    if (eq < 0) continue;
    out[part.slice(0, eq).trim()] = part.slice(eq + 1).trim();
  }
  return {
    cn: out.cn,
    org: out.o,
    position: out.t,
    orgInn: out['1.2.860.3.16.1.1'],
    pinfl: out['1.2.860.3.16.1.2'],
    personalInn: out.uid,
    serialNumber: out.serialnumber,
    validFrom: out.validfrom,
    validTo: out.validto,
  };
}

// ── certificates ─────────────────────────────────────────────────────────────

/**
 * Every certificate the module can see, from both file stores.
 *
 * `id` is the opaque handle the portal bridge uses (portal/src/shared/lib/eimzo/
 * capiws.ts) — a JSON blob of disk/path/name/alias, because `load_key` needs all
 * four and there is no single identifier.
 */
async function listCertificates() {
  const out = [];
  // On macOS the key volume IS /Volumes/DSKEYS, so it is reachable both as
  // (disk='/Volumes/', path='DSKEYS') and as (disk='/Volumes/DSKEYS/', path='').
  // `list_all_certificates` merges the two roots and its dedup leaks — it really
  // does return the same file twice. Dedup on the certificate itself.
  const seen = new Set();
  for (const store of ['pfx', 'ytks']) {
    let data;
    try {
      data = await call(store, 'list_all_certificates');
    } catch (err) {
      if (VERBOSE) process.stderr.write(`${store}: ${err.message}\n`);
      continue;
    }
    for (const c of data.certificates || []) {
      const key = `${store}|${c.name}|${c.alias}`;
      if (seen.has(key)) continue;
      seen.add(key);
      // Discrete fields when the module offers them; otherwise the parsed alias DN.
      const a = parseAlias(c.alias);
      out.push({
        store,
        id: JSON.stringify({ disk: c.disk, path: c.path, name: c.name, alias: c.alias }),
        subjectName: [c.O ?? a.org, c.CN ?? a.cn].filter(Boolean).join(' — ') || c.name,
        tin: c.TIN ?? a.orgInn,
        personalInn: a.personalInn,
        pinfl: c.PINFL ?? a.pinfl,
        name: c.CN ?? a.cn,
        org: c.O ?? a.org,
        position: a.position,
        serialNumber: c.serialNumber ?? a.serialNumber,
        validFrom: c.validFrom ?? a.validFrom,
        validTo: c.validTo ?? a.validTo,
        type: c.type,
        raw: c,
      });
    }
  }
  return out;
}

/** Resolve --cert: a 1-based index into `certs`, or a literal {disk,path,...} JSON. */
async function resolveCert(spec) {
  if (spec && spec.trim().startsWith('{')) return JSON.parse(spec);
  const certs = await listCertificates();
  if (certs.length === 0) {
    throw new Error(
      'no certificates found. On macOS E-IMZO scans /Volumes/DSKEYS/ ONLY — ~/DSKEYS is ' +
        'ignored. See `doctor`, and SKILL.md "Get a real test key" to mint one.',
    );
  }
  const idx = spec === undefined ? 1 : Number(spec);
  if (!Number.isInteger(idx) || idx < 1 || idx > certs.length) {
    throw new Error(`--cert must be 1..${certs.length} or a {disk,path,name,alias} JSON`);
  }
  return JSON.parse(certs[idx - 1].id);
}

// ── signing ──────────────────────────────────────────────────────────────────

/**
 * Produce a real PKCS#7/CMS signature over `challenge`.
 *
 * `load_key` opens a NATIVE password dialog on the desktop — this blocks until a
 * human types the store password, which is why it gets DIALOG_TIMEOUT_MS. The key
 * stays loaded for a while afterwards, so we unload it explicitly.
 *
 * `detached: 'yes'` omits the signed content from the envelope; 'no' embeds it.
 * The portal signs with 'no' and the backend verifies the embedded content
 * against the challenge, so keep 'no' unless you know the verifier wants detached.
 */
async function sign({ cert, challenge, detached = false }) {
  const { disk, path, name, alias } = cert;
  const loaded = await call('pfx', 'load_key', [disk, path, name, alias], DIALOG_TIMEOUT_MS);
  const keyId = loaded.keyId;
  if (!keyId) throw new Error(`load_key returned no keyId: ${JSON.stringify(loaded)}`);
  try {
    const data64 = Buffer.from(challenge, 'utf8').toString('base64');
    const signed = await call('pkcs7', 'create_pkcs7', [data64, keyId, detached ? 'yes' : 'no'], DIALOG_TIMEOUT_MS);
    if (!signed.pkcs7_64) throw new Error(`create_pkcs7 returned no pkcs7_64: ${JSON.stringify(signed)}`);
    return { pkcs7_64: signed.pkcs7_64, keyId };
  } finally {
    try { await call('pfx', 'unload_key', [keyId]); } catch { /* best effort */ }
  }
}

/**
 * The EIMZO_STUB envelope — NOT a signature.
 *
 * With `EIMZO_STUB=true` the backend skips the sidecar entirely and
 * `app/integrations/eimzo/client.py::_stub_verify` just base64-decodes a JSON
 * blob with these exact keys. This is how the whole challenge→verify→case flow is
 * driven in dev/e2e without a certificate. Field names are the STUB's, not the
 * sidecar's (`tin` here becomes `signer.org_inn`).
 */
function stubEnvelope({ challenge, tin, orgName, name, pinfl, position, serial, revoked }) {
  const blob = {
    challenge,
    tin: tin ?? '305123456',
    org_name: orgName ?? 'OOO POLYMER TEST',
    name: name ?? 'IVANOV IVAN',
    pinfl: pinfl ?? '31234567890123',
    position: position ?? 'Director',
    serial: serial ?? 'ABCDEF0123456789',
    ...(revoked ? { revoked: true } : {}),
  };
  return Buffer.from(JSON.stringify(blob), 'utf8').toString('base64');
}

// ── commands ─────────────────────────────────────────────────────────────────

const commands = {
  async version() {
    const d = await raw({ name: 'version' });
    console.log(`E-IMZO ${d.major}.${d.minor}.${d.patch} (${d.edition} edition) via ${ENDPOINT}`);
    return d;
  },

  async apidoc(opts) {
    const doc = await raw({ name: 'apidoc' });
    if (opts.json) {
      console.log(JSON.stringify(doc, null, 2));
      return doc;
    }
    const shown = opts.plugin ? doc.filter((p) => p.name === opts.plugin) : doc;
    if (opts.plugin && shown.length === 0) {
      throw new Error(`no such plugin: ${opts.plugin} (have: ${doc.map((p) => p.name).join(', ')})`);
    }
    let n = 0;
    for (const p of shown) {
      console.log(`\n${p.name} — ${p.description}`);
      for (const f of p.functions) {
        n++;
        console.log(`  ${p.name}.${f.name}(${(f.arguments || []).map((a) => a.name).join(', ')})`);
        console.log(`      ${f.description}`);
        for (const a of f.arguments || []) console.log(`      · ${a.name}: ${a.description}`);
      }
    }
    console.log(`\n${shown.length} plugin(s), ${n} functions`);
    return doc;
  },

  /** Health sweep — every read-only call, nothing that mutates or pops a dialog. */
  async doctor() {
    const report = {};
    const line = (label, value) => console.log(`  ${label.padEnd(26)} ${value}`);
    console.log(`\nE-IMZO doctor — ${ENDPOINT}\n`);

    try {
      const v = await raw({ name: 'version' }, 5000);
      report.version = `${v.major}.${v.minor}.${v.patch} ${v.edition}`;
      line('module', `OK  ${report.version}`);
    } catch (err) {
      line('module', `UNREACHABLE  ${err.message}`);
      console.log('\n  → Start it:  open -a E-IMZO      (macOS)');
      console.log('  → Both transports must be listening: :64646 (ws) and :64443 (wss)');
      process.exitCode = 1;
      return report;
    }

    try {
      const k = await raw({ name: 'apikey', arguments: API_KEYS }, 5000);
      line('apikey handshake', k.success ? 'OK' : `REJECTED  ${k.reason}`);
    } catch (err) {
      line('apikey handshake', `ERR  ${err.message}`);
    }

    for (const [label, plugin, fn, pick] of [
      ['pfx disks', 'pfx', 'list_disks', (d) => (d.disks || []).join(', ') || '(none)'],
      ['idcard readers', 'idcard', 'list_readers', (d) => (d.readers || []).join(', ') || '(none)'],
      ['ckc supported', 'ckc', 'supported_ckc', (d) => (d.list || []).join(', ')],
      ['ckc devices', 'ckc', 'list_ckc', (d) => (d.devices || []).length + ' attached'],
    ]) {
      try { line(label, pick(await call(plugin, fn, [], 8000))); }
      catch (err) { line(label, `ERR  ${err.message}`); }
    }

    const certs = await listCertificates();
    report.certificates = certs.length;
    line('certificates', certs.length ? `${certs.length} found` : 'NONE — signing is impossible');
    for (const [i, c] of certs.entries()) {
      console.log(`      [${i + 1}] ${c.subjectName}  TIN=${c.tin || '-'}  до ${c.validTo || '-'}  (${c.store})`);
    }
    if (certs.length === 0) {
      console.log('\n  → macOS scans /Volumes/DSKEYS/ ONLY (~/DSKEYS is ignored). Mint a test key:');
      console.log('       curl -k -X POST https://test.e-imzo.uz/registrator/public/pfx -d type=1 -OJ');
      console.log('       hdiutil create -size 16m -fs HFS+ -volname DSKEYS -ov /tmp/dskeys.dmg');
      console.log('       hdiutil attach /tmp/dskeys.dmg && cp DS*-test.pfx /Volumes/DSKEYS/');
      console.log('  → No key? Drive the backend with `stub-sign` + EIMZO_STUB=true instead.');
    }
    console.log('');
    return report;
  },

  async certs(opts) {
    const certs = await listCertificates();
    if (opts.json) {
      console.log(JSON.stringify(certs, null, 2));
      return certs;
    }
    if (certs.length === 0) {
      console.log('No certificates. See `doctor` for where E-IMZO looks.');
      return certs;
    }
    for (const [i, c] of certs.entries()) {
      console.log(`[${i + 1}] ${c.subjectName}`);
      console.log(`    store=${c.store} TIN=${c.tin || '-'} PINFL=${c.pinfl || '-'} serial=${c.serialNumber || '-'}`);
      console.log(`    valid ${c.validFrom || '?'} → ${c.validTo || '?'}`);
      console.log(`    id=${c.id}`);
    }
    return certs;
  },

  async sign(opts) {
    if (!opts.challenge) throw new Error('sign needs --challenge <text>');
    const cert = await resolveCert(opts.cert);
    process.stderr.write('load_key may open a native password dialog — answer it on the desktop.\n');
    const { pkcs7_64 } = await sign({ cert, challenge: opts.challenge, detached: !!opts.detached });
    console.log(pkcs7_64);
    return pkcs7_64;
  },

  async 'stub-sign'(opts) {
    if (!opts.challenge) throw new Error('stub-sign needs --challenge <text>');
    console.log(
      stubEnvelope({
        challenge: opts.challenge,
        tin: opts.tin,
        orgName: opts['org-name'],
        name: opts.name,
        pinfl: opts.pinfl,
        position: opts.position,
        serial: opts.serial,
        revoked: !!opts.revoked,
      }),
    );
  },

  /** Escape hatch: any of the 43 documented functions. `call pfx.list_disks` */
  async call(opts, positional) {
    const target = positional[0];
    if (!target || !target.includes('.')) throw new Error('usage: call <plugin>.<function> [arg ...]');
    const [plugin, name] = target.split('.');
    const timeout = opts.timeout ? Number(opts.timeout) : DEFAULT_TIMEOUT_MS;
    const data = await call(plugin, name, positional.slice(1), timeout);
    console.log(JSON.stringify(data, null, 2));
    return data;
  },

  /**
   * The product flow: POST challenge → sign → POST verify, against a running API.
   * This is the thing the portal's EimzoSignDialog does, minus the browser.
   */
  async flow(opts) {
    const api = (opts.api || 'http://localhost:8000').replace(/\/$/, '');
    const companyId = opts.company;
    const token = opts.token;
    if (!companyId || !token) throw new Error('flow needs --company <id> --token <portal JWT>');
    const base = `${api}/api/v1/portal/companies/${companyId}/eimzo`;
    const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };

    process.stderr.write(`POST ${base}/challenge\n`);
    const chRes = await fetch(`${base}/challenge`, { method: 'POST', headers });
    const chBody = await chRes.text();
    if (!chRes.ok) throw new Error(`challenge failed ${chRes.status}: ${chBody}`);
    const challenge = JSON.parse(chBody).challenge;
    console.log(`challenge: ${challenge}`);

    let pkcs7;
    if (opts.stub) {
      pkcs7 = stubEnvelope({ challenge, tin: opts.tin, orgName: opts['org-name'] });
      process.stderr.write('signed with the STUB envelope (backend needs EIMZO_STUB=true)\n');
    } else {
      const cert = await resolveCert(opts.cert);
      process.stderr.write('load_key may open a native password dialog — answer it on the desktop.\n');
      pkcs7 = (await sign({ cert, challenge })).pkcs7_64;
      process.stderr.write(`signed: ${pkcs7.length} b64 chars\n`);
    }

    process.stderr.write(`POST ${base}/verify\n`);
    const vRes = await fetch(`${base}/verify`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ pkcs7: pkcs7 }),
    });
    const vBody = await vRes.text();
    console.log(`verify -> HTTP ${vRes.status}`);
    console.log(vBody);
    if (!vRes.ok) process.exitCode = 1;
  },

  help() {
    console.log(`
capiws.mjs — drive the local E-IMZO desktop module (CAPIWS WebSocket API)

  doctor                    health sweep: module, transports, stores, certificates
  version                   module version + edition
  apidoc [--json] [--plugin pfx]
                            the module's OWN function catalog (11 plugins / 43 fns)
  certs [--json]            every visible certificate, with the id sign() wants
  sign --challenge <text> [--cert N|<json>] [--detached]
                            REAL PKCS#7 over <text>; prints base64 to stdout
  stub-sign --challenge <text> [--tin ...] [--org-name ...] [--revoked]
                            the EIMZO_STUB envelope — no crypto, no certificate
  call <plugin>.<fn> [args...] [--timeout ms]
                            raw escape hatch for anything in apidoc
  flow --company <id> --token <jwt> [--api http://localhost:8000]
       [--stub | --cert N]
                            challenge → sign → verify against a running backend

Global:
  --tls                     use wss://127.0.0.1:64443 instead of ws://127.0.0.1:64646
  --verbose                 echo every frame to stderr

Examples:
  node .claude/skills/eimzo/capiws.mjs doctor
  node .claude/skills/eimzo/capiws.mjs apidoc --plugin pkcs7
  node .claude/skills/eimzo/capiws.mjs call x509.get_certificate_info "$(cat cert.b64)"
  node .claude/skills/eimzo/capiws.mjs stub-sign --challenge abc123 --tin 305123456
`);
  },
};

// ── arg parsing ──────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const opts = {};
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next === undefined || next.startsWith('--')) opts[key] = true;
      else { opts[key] = next; i++; }
    } else positional.push(a);
  }
  return { opts, positional };
}

const [, , cmdName = 'doctor', ...rest] = process.argv;
const { opts, positional } = parseArgs(rest);
if (opts.tls) {
  ENDPOINT = WSS;
  // The TLS endpoint presents a self-signed "CN=E-IMZO" certificate that no
  // trust store has. Set this BEFORE the first connect — undici reads it then.
  // Only on the --tls path, so the default transport never weakens TLS.
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';
}
if (opts.verbose) VERBOSE = true;

const cmd = commands[cmdName];
if (!cmd) {
  console.error(`unknown command: ${cmdName}`);
  commands.help();
  process.exit(2);
}
try {
  await cmd(opts, positional);
} catch (err) {
  console.error(`\n✗ ${err.message}`);
  process.exit(1);
}
