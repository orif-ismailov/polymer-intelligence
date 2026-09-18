/**
 * Step-up bridge — the same indirection as `authBridge`, for the same FSD reason.
 *
 * A sensitive action (today: company payout details) answers 403 `step_up_required`
 * when the password has not been re-entered recently. The fetch client cannot open a
 * dialog itself — `shared` may not import from `features` — so the step-up feature
 * *registers* a prompt here at app boot and the client calls through it.
 *
 * Nothing registered (unit tests, SSR) means no prompt: the 403 propagates to the
 * caller unchanged, which is the honest degradation. A silent retry would loop.
 */

export interface StepUpBridge {
  /**
   * Ask the user to re-enter their password and confirm it with the server.
   * Resolves true when the window is open and the request may be retried,
   * false when the user cancelled or the password was refused.
   */
  prompt: () => Promise<boolean>;
}

let bridge: StepUpBridge | null = null;

export function registerStepUpBridge(next: StepUpBridge): void {
  bridge = next;
}

export function promptStepUp(): Promise<boolean> {
  return bridge ? bridge.prompt() : Promise.resolve(false);
}
