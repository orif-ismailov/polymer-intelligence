export default function DashboardPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-4xl">
        <h1 className="mb-2 text-3xl font-bold text-foreground">
          Polymer Intelligence
        </h1>
        <p className="mb-8 text-foreground-muted">
          Market intelligence platform — Phase 1 scaffold
        </p>
        <div className="rounded-lg border border-border bg-background-secondary p-6">
          <p className="text-foreground-muted">
            Dashboard screens will be implemented in later phases.
          </p>
          <div className="mt-4 flex gap-3">
            <span className="inline-flex items-center rounded-full bg-accent-subtle px-3 py-1 text-sm text-accent">
              Live Feed
            </span>
            <span className="inline-flex items-center rounded-full bg-background-tertiary px-3 py-1 text-sm text-foreground-muted">
              Purchase Requests
            </span>
            <span className="inline-flex items-center rounded-full bg-background-tertiary px-3 py-1 text-sm text-foreground-muted">
              Price Trends
            </span>
          </div>
        </div>
      </div>
    </main>
  );
}
