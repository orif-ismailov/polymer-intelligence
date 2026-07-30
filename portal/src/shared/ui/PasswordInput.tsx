import { forwardRef, useState } from "react";

import { Input, type InputProps } from "./Input";
import { EyeIcon, EyeOffIcon } from "./icons";

export interface PasswordInputProps extends Omit<InputProps, "type" | "trailing"> {
  /** Accessible name for the reveal toggle — the caller supplies the localized string. */
  revealLabel?: string;
}

/**
 * A masked field with the mockups' reveal eye (E-IMZO «PIN-код от токена»).
 *
 * The toggle is a real button inside the well rather than a sibling: `Input`'s
 * adornment slot is pointer-transparent except for nested buttons, so clicking
 * anywhere else in the field still focuses the input.
 */
export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  function PasswordInput({ revealLabel, ...rest }, ref) {
    const [revealed, setRevealed] = useState(false);

    return (
      <Input
        ref={ref}
        type={revealed ? "text" : "password"}
        trailing={
          <button
            type="button"
            aria-label={revealLabel}
            aria-pressed={revealed}
            onClick={() => setRevealed((prev) => !prev)}
            className="rounded-sm text-text-muted transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
          >
            {revealed ? <EyeOffIcon size={18} /> : <EyeIcon size={18} />}
          </button>
        }
        {...rest}
      />
    );
  },
);
