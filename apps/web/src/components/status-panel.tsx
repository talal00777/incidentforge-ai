import type { ServiceHealth } from "@/lib/health";

export function StatusPanel({ health }: { health: ServiceHealth }) {
  const healthy = health.state === "operational";
  const checkedAt = new Date(health.checkedAt).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });

  return (
    <section className="panel health-panel" aria-labelledby="health-heading">
      <div className="panel-header">
        <h2 id="health-heading">Platform health</h2>
        <span className={`health-pill ${healthy ? "is-healthy" : "is-degraded"}`}>
          <span className="health-dot" aria-hidden="true" />
          {healthy ? "Operational" : "Degraded"}
        </span>
      </div>
      <dl className="health-details">
        <div><dt>API and dependencies</dt><dd>{healthy ? "Ready" : "Unavailable"}</dd></div>
        <div><dt>Last checked</dt><dd><time dateTime={health.checkedAt}>{checkedAt} UTC</time></dd></div>
      </dl>
      {!healthy && <p className="health-error" role="alert">{health.reason}</p>}
    </section>
  );
}
