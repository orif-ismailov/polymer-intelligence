/**
 * Dashboard Home — placeholder for Plan 04-03 KPI cards + panels.
 * This route renders now so the route group compiles and auth guard works.
 * Plan 04-03 fills this with KPI cards (Total Buyers, Total Sellers, Active Requests,
 * Hot Leads, Price Alerts), Live Market Feed panel, Price Trends panel, AI Market Signals
 * panel (D-01 layout-final), and Top Buyer/Seller panels.
 */
export default function DashboardHomePage() {
  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-foreground">Dashboard</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Market overview and activity summary
        </p>
      </div>
      {/* KPI cards + panels grid — filled by Plan 04-03 */}
      <div
        className="grid gap-6"
        aria-label="Dashboard panels placeholder"
        data-slot="dashboard-grid"
      >
        <p className="text-sm text-foreground-subtle">
          Dashboard panels loading… (Plan 04-03 fills this grid with KPI cards,
          Live Feed, Price Trends, and AI Market Signals panels.)
        </p>
      </div>
    </div>
  );
}
