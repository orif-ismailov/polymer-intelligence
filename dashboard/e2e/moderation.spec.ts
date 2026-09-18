/**
 * Moderation queue — each row must say which offer it is (IMEX-23).
 *
 * A moderator approves or rejects a listing, and before this the row carried the
 * grade, the volume, the city, the seller and the price — everything except WHAT
 * IS BEING SOLD. Two offers for different products rendered as the same sentence.
 *
 * **Why this one spec stubs its API while the rest of the suite runs against a real
 * one.** Putting two pending offers in the queue for real means driving the entire
 * seller pipeline — portal account, company, verification, publish — for a change
 * that is purely about how a row renders. The stub states the payload the backend
 * already sends (`product_text` is in `ModerationOfferOut` today) and asserts what
 * the page does with it, which is the whole of what changed. Anything about the
 * queue's data is still the backend suite's job.
 */
import { expect } from "@playwright/test";

import { test, M, p } from "./helpers";

/** Two offers that differ ONLY in the field the row was failing to show. */
const QUEUE = [
  {
    id: 4101,
    product_id: null,
    product_text: "Полипропилен гомополимер, литьевой",
    grade_text: "QA",
    polymer_type: "PP",
    availability: "in_stock",
    qty_available: 25000,
    qty_unit: "MT",
    price: 1200,
    currency: "USD",
    warehouse_city: "Tashkent",
    created_at: "2026-09-15T08:00:00Z",
    status: "pending_moderation",
    seller: null,
    origin: "company",
    display_name: "QA seller",
    company_verified: true,
    compliance: null,
    has_lab_passport: false,
    lab_verified: false,
    files: [
      { id: 1, kind: "image", file_name: "granulat.jpg" },
      { id: 2, kind: "lab_passport", file_name: "passport_kachestva.pdf" },
    ],
  },
  {
    id: 4102,
    product_id: null,
    product_text: "Полиэтилен низкого давления, плёночный",
    // Same grade as the first row on purpose: while the grade was the title, these
    // two rows were literally the same sentence.
    grade_text: "QA",
    polymer_type: "HDPE",
    availability: "in_stock",
    qty_available: 25000,
    qty_unit: "MT",
    price: 1200,
    currency: "USD",
    warehouse_city: "Tashkent",
    created_at: "2026-09-15T09:00:00Z",
    status: "pending_moderation",
    seller: null,
    origin: "company",
    display_name: "QA seller",
    company_verified: true,
    compliance: null,
    has_lab_passport: false,
    lab_verified: false,
    files: [],
  },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/admin/moderation/offers", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({ json: QUEUE });
  });
});

test("a queue row names the product a buyer will see, not its grade", async ({ page }) => {
  await page.goto(p("/moderation"));

  // `data-offer-id` sits ON the row, so it is part of the selector — not a
  // `filter({has})`, which looks for a descendant and quietly matches nothing.
  const row = page.locator('[data-testid="moderation-offer"][data-offer-id="4101"]');
  await expect(page.getByTestId("moderation-offer")).toHaveCount(2);

  // The catalogue title is the headline. Before IMEX-23 this read "QA" — the grade
  // shadowed `product_text`, so the moderator and the buyer saw different products.
  await expect(row.getByTestId("moderation-offer-title")).toHaveText(
    "Полипропилен гомополимер, литьевой",
  );
});

test("the grade survives as a subtitle rather than replacing the product", async ({ page }) => {
  await page.goto(p("/moderation"));

  const row = page.locator('[data-testid="moderation-offer"][data-offer-id="4101"]');
  await expect(row.getByTestId("moderation-offer-subtitle")).toContainText("QA");
  await expect(row.getByTestId("moderation-offer-subtitle")).toContainText("PP");
});

test("two different products no longer render as the same row", async ({ page }) => {
  await page.goto(p("/moderation"));

  const first = page.locator('[data-testid="moderation-offer"][data-offer-id="4101"]');
  const second = page.locator('[data-testid="moderation-offer"][data-offer-id="4102"]');

  const a = await first.getByTestId("moderation-offer-title").textContent();
  const b = await second.getByTestId("moderation-offer-title").textContent();
  expect(a).not.toEqual(b);
});

test("the row carries the offer id a moderator can quote", async ({ page }) => {
  await page.goto(p("/moderation"));

  const row = page.locator('[data-testid="moderation-offer"][data-offer-id="4101"]');
  await expect(row).toContainText("4101");
});

test("attachments are listed, so the moderator knows what was submitted", async ({ page }) => {
  await page.goto(p("/moderation"));

  const withFiles = page.locator('[data-testid="moderation-offer"][data-offer-id="4101"]');
  await expect(withFiles.getByTestId("moderation-offer-files")).toContainText(
    "passport_kachestva.pdf",
  );

  // No files is not an empty heading — the block is absent entirely.
  const withoutFiles = page.locator('[data-testid="moderation-offer"][data-offer-id="4102"]');
  await expect(withoutFiles.getByTestId("moderation-offer-files")).toHaveCount(0);
});

test("a decision can be aimed at one specific offer in the queue", async ({ page }) => {
  // The automation complaint on the ticket, as a test: without an addressable row a
  // spec has to approve whatever is first and then work out from the request which
  // offer that was. Here the SECOND row is targeted and the request must name it.
  await page.goto(p("/moderation"));

  const approve = page
    .locator('[data-testid="moderation-offer"][data-offer-id="4102"]')
    .getByTestId("moderation-approve");

  const [request] = await Promise.all([
    page.waitForRequest(
      (r) => r.url().includes("/admin/moderation/offers/") && r.method() === "POST",
    ),
    approve.click(),
  ]);

  expect(request.url()).toContain("/admin/moderation/offers/4102/approve");
});

test("the note box belongs to its own row", async ({ page }) => {
  await page.goto(p("/moderation"));

  const row = page.locator('[data-testid="moderation-offer"][data-offer-id="4102"]');
  await row.getByTestId("moderation-note").fill("не хватает паспорта качества");

  const other = page.locator('[data-testid="moderation-offer"][data-offer-id="4101"]');
  await expect(other.getByTestId("moderation-note")).toHaveValue("");
  expect(M.moderation.notePlaceholder).toBeTruthy();
});
