import { Sidebar } from "@/components/layout/Sidebar";

interface AppShellProps {
  children: React.ReactNode;
}

/**
 * AppShell — fixed 240px sidebar + scrollable main content area.
 * Pattern: fixed Sidebar + flex-1 main (RESEARCH.md Recommended Project Structure).
 */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <main
        className="flex-1 overflow-y-auto"
        id="main-content"
        tabIndex={-1}
      >
        {children}
      </main>
    </div>
  );
}
