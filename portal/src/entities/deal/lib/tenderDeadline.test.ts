/**
 * Run with: node --test src/entities/deal/lib/tenderDeadline.test.ts
 *
 * The portal has no unit runner (Playwright only), and this is the one piece of
 * the tender list that is arithmetic rather than layout — the thresholds decide
 * which tenders a supplier sees as urgent. Node strips the types itself, and the
 * module under test imports nothing, so no tooling is needed.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { tenderDeadline } from "./tenderDeadline.ts";

const CREATED = "2026-09-20T09:00:00Z";
const at = (iso: string): Date => new Date(iso);

test("a fresh tender has most of its window left and reads neutral", () => {
  const d = tenderDeadline(CREATED, 30, at("2026-09-21T09:00:00Z"));
  assert.equal(d.daysLeft, 29);
  assert.equal(d.tone, "neutral");
});

test("three days or fewer is a warning", () => {
  assert.equal(tenderDeadline(CREATED, 10, at("2026-09-27T09:00:00Z")).tone, "warning"); // 3 left
  assert.equal(tenderDeadline(CREATED, 10, at("2026-09-26T09:00:00Z")).tone, "neutral"); // 4 left
});

test("a part-day counts as a whole day left, never as zero", () => {
  // 2 days and 1 hour left reads «ещё 3 дн.», not «ещё 2 дн.» — rounding down would
  // tell a supplier they have less time than they do.
  const d = tenderDeadline(CREATED, 10, at("2026-09-28T08:00:00Z"));
  assert.equal(d.daysLeft, 3);
});

test("under a day left is the last day", () => {
  const d = tenderDeadline(CREATED, 10, at("2026-09-30T02:00:00Z"));
  assert.equal(d.tone, "lastDay");
  assert.equal(d.daysLeft, 1);
});

test("past the window the tender reads closed", () => {
  const d = tenderDeadline(CREATED, 10, at("2026-09-30T09:00:01Z"));
  assert.equal(d.tone, "closed");
  assert.equal(d.daysLeft, 0);
});

test("an unparseable date is not presented as urgent", () => {
  const d = tenderDeadline("not a date", 10, at("2026-09-21T09:00:00Z"));
  assert.equal(d.tone, "unknown");
});
