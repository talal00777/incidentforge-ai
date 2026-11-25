import { AppShell } from "@/components/app-shell";
import { WorkspacesPanel } from "@/components/workspaces/workspaces-panel";

export default function WorkspacesPage() {
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <header className="page-heading is-compact">
          <div>
            <h1>Workspaces</h1>
            <p className="page-subtitle">Team access control and signed alert webhooks.</p>
          </div>
        </header>
        <WorkspacesPanel />
      </AppShell>
    </>
  );
}
