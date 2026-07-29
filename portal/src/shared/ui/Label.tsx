import { type LabelHTMLAttributes } from "react";

import { cn } from "@/shared/lib";

interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  required?: boolean;
}

export function Label({ className, children, required, ...rest }: LabelProps) {
  return (
    <label className={cn("mb-1.5 block text-sm font-medium text-text", className)} {...rest}>
      {children}
      {required ? <span className="ml-0.5 text-danger">*</span> : null}
    </label>
  );
}
