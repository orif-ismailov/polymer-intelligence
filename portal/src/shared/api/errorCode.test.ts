/**
 * Run with: node --test src/shared/api/errorCode.test.ts
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { detailCode, detailError } from "./errorCode.ts";

// What `extractError` builds for FastAPI's `HTTPException(409, "didox_session_required")`:
// `detail` is the WHOLE body, so the string sits one level down.
const sessionRequired = {
  status: 409,
  message: "didox_session_required",
  detail: { detail: "didox_session_required" },
};

test("reads the string detail out of the body the error carries", () => {
  assert.equal(detailCode(sessionRequired), "didox_session_required");
});

test("an object detail is not a code", () => {
  const rejected = {
    status: 422,
    detail: { detail: { error: "didox_rejected", message: "x" } },
  };
  assert.equal(detailCode(rejected), null);
});

test("anything that is not an API error has no code", () => {
  assert.equal(detailCode(new Error("didox_session_required")), null);
  assert.equal(detailCode(null), null);
  assert.equal(detailCode({ detail: null }), null);
});

test("detailError reads the code of a structured refusal", () => {
  const pending = {
    status: 409,
    detail: { detail: { error: "facture_pending", document_id: 7 } },
  };
  assert.equal(detailError(pending), "facture_pending");
  assert.equal(detailError(sessionRequired), null);
  assert.equal(detailError(null), null);
});
