import { expect, test } from "@playwright/test";

import { login, registerCompany } from "./_registration";
import { registerLaboratory, registerLogistics, registerManufacturer, uniquePhone, uniqueTaxId } from "./_registration-typed";

test.use({ locale: "ru-RU" });

test("smoke: buyer happy path", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  const id = await registerCompany(page, uniqueTaxId(), { type: "buyer" });
  expect(id).toBeGreaterThan(0);
});

test("smoke: distributor happy path (dual role: distributor + trader)", async ({
  page,
  request,
}) => {
  await login(page, request, uniquePhone());
  const id = await registerCompany(page, uniqueTaxId(), { type: "distributor" });
  expect(id).toBeGreaterThan(0);
});

test("smoke: manufacturer happy path", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  const id = await registerManufacturer(page, uniqueTaxId());
  expect(id).toBeGreaterThan(0);
});

test("smoke: logistics happy path", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  const id = await registerLogistics(page, uniqueTaxId());
  expect(id).toBeGreaterThan(0);
});

test("smoke: laboratory happy path", async ({ page, request }) => {
  await login(page, request, uniquePhone());
  const id = await registerLaboratory(page, uniqueTaxId());
  expect(id).toBeGreaterThan(0);
});
