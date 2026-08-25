import { expect, test } from "@playwright/test";

/**
 * Didox's refusal has to reach the person, verbatim (P7.a, 25.08.2026).
 *
 * The rail's last step answers `422 {"detail": {"error": "didox_rejected",
 * "message": "ИНН/ПИНФЛ заказчика некорректный. ИНН/ПИНФЛ: 562353400"}}`. That
 * sentence names the field AND the company; the UI was rendering it as «Не
 * удалось подписать документ.», which sent an afternoon into guessing.
 *
 * The trap is one level deep and invisible to types: `ApiError.detail` holds the
 * WHOLE response body, so the payload sits at `detail.detail`, and reading
 * `detail.error` finds `undefined` and falls back to the generic string without
 * anything failing. Browser-free on purpose — this is about shape, not signing.
 */

test.describe("a Didox refusal is unwrapped, not swallowed", () => {
  test("the provider's own sentence survives FastAPI's envelope", async ({ page }) => {
    await page.goto("/cabinet/login");

    const verdict = await page.evaluate(async () => {
      const mod = await import("/src/features/didox-sign/model/useDidoxSign.ts");
      const api = await import("/src/shared/api/index.ts");

      const wrapped = new api.ApiError(422, "ИНН/ПИНФЛ заказчика некорректный", {
        code: null,
        // Exactly what `client.ts` stores: the whole body.
        detail: {
          detail: {
            error: "didox_rejected",
            message: "ИНН/ПИНФЛ заказчика некорректный. ИНН/ПИНФЛ: 562353400",
            description: "Проверьте ИНН контрагента",
            trace_id: null,
          },
        },
      });

      const bare = new api.ApiError(503, "down", { detail: { detail: "didox_unavailable" } });

      return {
        wrapped: mod.rejectionOf(wrapped)?.message ?? null,
        remedy: mod.rejectionOf(wrapped)?.description ?? null,
        unrelated: mod.rejectionOf(bare),
        notAnApiError: mod.rejectionOf(new Error("boom")),
      };
    });

    expect(verdict.wrapped).toContain("562353400");
    expect(verdict.remedy).toBe("Проверьте ИНН контрагента");
    // Anything that is not a provider refusal must stay unclaimed, so the hook's
    // own `expired` / `unavailable` / `offer_required` branches still fire.
    expect(verdict.unrelated).toBeNull();
    expect(verdict.notAnApiError).toBeNull();
  });
});
