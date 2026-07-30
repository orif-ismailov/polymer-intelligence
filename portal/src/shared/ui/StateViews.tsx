import { type ReactNode } from "react";

import { Alert } from "./Alert";
import { Button } from "./Button";
import { Spinner } from "./Spinner";

interface LoadingViewProps {
  label?: string;
  className?: string;
}

/** Centered loading placeholder for a page/section. */
export function LoadingView({ label, className }: LoadingViewProps) {
  return (
    <div className={className ?? "flex items-center justify-center py-16 text-text-muted"}>
      <Spinner label={label} />
    </div>
  );
}

interface ErrorViewProps {
  title: string;
  message?: string;
  retryLabel?: string;
  onRetry?: () => void;
  children?: ReactNode;
}

/** Centered error placeholder with an optional retry action. */
export function ErrorView({ title, message, retryLabel, onRetry, children }: ErrorViewProps) {
  return (
    <div className="py-8">
      <Alert
        tone="danger"
        title={title}
        action={
          onRetry ? (
            <Button size="sm" variant="outline" onClick={onRetry}>
              {retryLabel ?? "Retry"}
            </Button>
          ) : (
            children
          )
        }
      >
        {message}
      </Alert>
    </div>
  );
}
