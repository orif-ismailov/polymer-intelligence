import { type ReactNode } from "react";

import { tabItemClasses, tabListClasses, type TabsVariant } from "./tabStyles";

export interface TabItem {
  id: string;
  label: ReactNode;
  /** Rendered beside the label in tabular figures, so counts line up. */
  count?: number;
  testId?: string;
}

interface TabsProps {
  items: readonly TabItem[];
  value: string;
  onChange: (id: string) => void;
  variant?: TabsVariant;
  /** Accessible name for the group — the caller supplies the localized string. */
  label?: string;
  className?: string;
  "data-testid"?: string;
}

/**
 * The mockups' two switcher shapes in one primitive: `underline` (product detail,
 * company profile, trade room) and `pill` (market filters, deal scopes). It was
 * copy-pasted with identical classes in six places before this.
 *
 * Deliberately NOT `role="tablist"`. These switchers filter a list that lives
 * outside them; a tablist without a matching `role="tabpanel"` is an axe violation
 * where a plain toggle button is not, and every call site would have to grow a
 * panel wrapper to complete the pattern. `aria-pressed` toggle buttons are both
 * correct and what the existing pill rows already use.
 */
export function Tabs({
  items,
  value,
  onChange,
  variant = "underline",
  label,
  className,
  "data-testid": testId,
}: TabsProps) {
  return (
    <div
      role="group"
      aria-label={label}
      className={tabListClasses(variant, className)}
      data-testid={testId}
    >
      {items.map((item) => {
        const active = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onChange(item.id)}
            aria-pressed={active}
            className={tabItemClasses(variant, active)}
            data-testid={item.testId}
          >
            {item.label}
            {item.count != null ? <span className="num ms-1.5 text-xs">{item.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
