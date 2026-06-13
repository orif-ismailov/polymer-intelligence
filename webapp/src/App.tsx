// Polymer Intelligence — Telegram Web App
// Honors Telegram theme CSS variables (var(--tg-theme-*)) per C-frontend constraint.
// NO hardcoded dark colors — the Telegram client injects its own theme vars.

const styles = {
  app: {
    minHeight: "100vh",
    backgroundColor: "var(--tg-theme-bg-color, #1e293b)",
    color: "var(--tg-theme-text-color, #f8fafc)",
    fontFamily: "system-ui, sans-serif",
  },
  header: {
    padding: "16px",
    borderBottom: "1px solid var(--tg-theme-secondary-bg-color, #334155)",
    backgroundColor: "var(--tg-theme-secondary-bg-color, #0f172a)",
  },
  headerTitle: {
    margin: 0,
    fontSize: "18px",
    fontWeight: 600,
    color: "var(--tg-theme-text-color, #f8fafc)",
  },
  headerSubtitle: {
    margin: "4px 0 0",
    fontSize: "13px",
    color: "var(--tg-theme-hint-color, #94a3b8)",
  },
  main: {
    padding: "16px",
  },
  card: {
    borderRadius: "12px",
    padding: "16px",
    backgroundColor: "var(--tg-theme-secondary-bg-color, #1e293b)",
    marginBottom: "12px",
  },
  cardTitle: {
    margin: "0 0 8px",
    fontSize: "15px",
    fontWeight: 600,
    color: "var(--tg-theme-text-color, #f8fafc)",
  },
  cardText: {
    margin: 0,
    fontSize: "13px",
    color: "var(--tg-theme-hint-color, #94a3b8)",
  },
  accentButton: {
    display: "inline-block",
    marginTop: "12px",
    padding: "10px 20px",
    borderRadius: "8px",
    backgroundColor: "var(--tg-theme-button-color, #10b981)",
    color: "var(--tg-theme-button-text-color, #ffffff)",
    border: "none",
    fontSize: "14px",
    fontWeight: 600,
    cursor: "pointer",
    width: "100%",
  },
} as const;

export default function App() {
  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <h1 style={styles.headerTitle}>Polymer Intelligence</h1>
        <p style={styles.headerSubtitle}>Telegram Web App — Phase 1 scaffold</p>
      </header>
      <main style={styles.main}>
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>My Requests</h2>
          <p style={styles.cardText}>
            Request submission and tracking will be available in a later phase.
          </p>
          <button style={styles.accentButton} type="button">
            New Request
          </button>
        </div>
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>Market Signals</h2>
          <p style={styles.cardText}>
            Live feed of polymer market signals — coming soon.
          </p>
        </div>
      </main>
    </div>
  );
}
