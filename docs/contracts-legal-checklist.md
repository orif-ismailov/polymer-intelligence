# Contracts — legal sign-off checklist (R3 Stage B, TB4.4)

**Status: LAUNCH BLOCKER.** The contracts feature (E-IMZO-signed e-contracts) must
not be enabled in production until every item below is signed off by the operator's
legal counsel. Engineering has shipped the rails; these are business/legal actions.

## 1. Production contract template text
- [ ] Replace the DEV placeholder template `SUPPLY_V1`
      (`backend/app/seed/data/contract_templates/supply_v1_ru.html`) with the
      legally reviewed supply-contract text (RU primary; UZ per availability).
- [ ] Bump the template `version` and re-seed
      (`python -m app.seed.seed_contract_templates`) so existing contracts keep their
      original `template_version` (contracts pin the version they were rendered with).
- [ ] Confirm the variable set (product, qty, unit, price, currency, incoterms,
      payment terms, delivery window, special conditions) matches the legal text.

## 2. Terms of Service / electronic contracting clause
- [ ] Add a ToS clause covering electronic contracting on the platform: that a
      contract signed by both parties via E-IMZO is legally binding, and how disputes
      are handled (out of platform in R3 — no in-platform dispute tooling).
- [ ] Surface acceptance of that clause during onboarding.

## 3. E-IMZO / e-document law conformance
- [ ] Legal confirmation that an E-IMZO **PKCS#7** signature over the contract
      document hash, plus the immutable stored evidence
      (`signature_evidence`: challenge, PKCS#7 blob in S3 + sha256, cert subject),
      satisfies the Uzbek requirements under the Law «Об электронном документообороте»
      and «Об электронной цифровой подписи».
- [ ] Confirm the challenge design (`contract:{public_id}:{document_sha256}`,
      single-use, bound to the rendered document hash) meets non-repudiation needs.
- [ ] Confirm the signature bundle export (`GET …/bundle` → PDF + both PKCS#7 +
      `verification.json` with sha256/signers/timestamps) is an acceptable evidentiary
      package for legal/audit use.

## 4. Data localization (PINFL / personal data)
- [ ] Confirm storage of director/signer personal data (`company_person_data`:
      encrypted PINFL + full name, §6.2) complies with UZ data-localization law
      (data resides on in-country infrastructure; app-layer encryption with
      `VERIFICATION_ENC_KEY`; PINFL never surfaced beyond a masked `****{last4}`).

## 5. Operational prerequisites (see deploy/CLAUDE.md)
- [ ] UNICON **e-imzo-server** sidecar image in the private registry
      (`EIMZO_SERVER_IMAGE`), `eimzo` compose profile enabled, `EIMZO_STUB=false`.
- [ ] Production UZ root/intermediate CA bundle mounted in
      `deploy/eimzo/truststore/`.

> Until sign-off: keep `EIMZO_STUB=false` in prod (the stub is dev/CI only), do not
> upload a production template, and treat the feature as staged. The state machine,
> evidence, integrity beat (`verify_contract_integrity`) and expiry beat
> (`expire_stale_contracts`) are all live and safe to run.
