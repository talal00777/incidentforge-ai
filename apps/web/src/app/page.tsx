import Link from "next/link";
import "./accessibility.css";
import { AppShell } from "@/components/app-shell";
import { OperationalDashboard } from "@/components/dashboard/operational-dashboard";
import { ProductIcon } from "@/components/product-icon";
import { fetchServiceHealth } from "@/lib/health";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const origin = process.env.INTERNAL_API_ORIGIN ?? "http://127.0.0.1:8000";
  const health = await fetchServiceHealth(origin);

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <span className="sr-only" id="unavailable-action-description">This action is not available yet.</span>
        <section className="page-heading">
          <div>
            <p className="page-overline">Operations</p>
            <h1>Incident overview</h1>
            <p className="page-subtitle">
              Real-time incident telemetry, service error impact, and one-click outage investigation.
            </p>
          </div>
          <Link className="button button-primary" href="/incidents/new">
            <ProductIcon name="plus" size={18} /> New incident
          </Link>
        </section>

        <OperationalDashboard health={health} />
      </AppShell>
    </>
  );
}
