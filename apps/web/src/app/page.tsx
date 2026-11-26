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
  const healthy = health.state === "operational";

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppShell>
        <span className="sr-only" id="unavailable-action-description">This action is not available yet.</span>
        <section className="page-heading is-compact">
          <div className="page-heading-inline">
            <h1>Incident overview</h1>
            <span className={`health-inline ${healthy ? "is-healthy" : "is-degraded"}`}>
              <span className="health-dot" aria-hidden="true" />
              {healthy ? "API operational" : "API degraded"}
            </span>
          </div>
          <Link className="button button-primary" href="/incidents/new">
            <ProductIcon name="plus" size={16} /> New incident
          </Link>
        </section>

        {!healthy && (
          <p className="health-error" role="alert" style={{ marginBottom: "16px" }}>
            {health.reason}
          </p>
        )}

        <OperationalDashboard health={health} />
      </AppShell>
    </>
  );
}
