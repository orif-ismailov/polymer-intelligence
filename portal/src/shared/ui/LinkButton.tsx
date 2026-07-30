import { Link, type LinkProps } from "react-router-dom";

import { buttonClasses, type ButtonSize, type ButtonVariant } from "./buttonStyles";

export interface LinkButtonProps extends LinkProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
}

/** A react-router <Link> styled as a button — for navigational actions. */
export function LinkButton({ variant, size, fullWidth, className, ...rest }: LinkButtonProps) {
  return <Link className={buttonClasses({ variant, size, fullWidth, className })} {...rest} />;
}
