"use client";

import { useEffect, useState } from "react";
import { IncidentWorkflowNav, type IncidentStage } from "@/components/incident-workflow-nav";
import { useAccount } from "@/components/m1/use-account";
import { apiGet, type Incident } from "@/lib/api-client";
import { formatRelativeAge } from "@/lib/dashboard-api";

export function IncidentWorkspaceHeader({
  incidentId,
  current,
  showTabs = true,
}: {
  incidentId: string;
  current?: IncidentStage;
  showTabs?: boolean;
}) {
  const account = useAccount();
  const [incident, setIncident] = useState<Incident | null>(null);

  useEffect(() => {
    if (account.state !== "signed-in") return;
    let active = true;
    apiGet<Incident>(`incidents/${encodeURIComponent(incidentId)}`)
      .then((record) => {
        if (active) setIncident(record);
      })
      .catch(() => {
        if (active) setIncident(null);
      });
    return () => {
      active = false;
    };
  }, [account.state, incidentId]);

  if (account.state !== "signed-in") return null;

  const shortId = `INC-${incidentId.slice(0, 6).toUpperCase()}`;

  return (
    <div className="inc-ctx-wrap">
      <div className={showTabs && current ? "inc-ctx-bar" : "inc-ctx-bar is-standalone"}>
        <div className="inc-ctx-left">
          <span className="inc-ctx-id">{shortId}</span>
          <span className="inc-ctx-title">{incident ? incident.title : "Incident workspace"}</span>
          {incident?.service_name && <span className="inc-ctx-chip">{incident.service_name}</span>}
          {incident?.environment && <span className="inc-ctx-chip">{incident.environment}</span>}
        </div>
        {incident && (
          <div className="inc-ctx-right">
            <span className={`if-badge if-badge-${incident.severity}`}>{incident.severity}</span>
            <span className={`if-badge if-badge-${incident.status}`}>{incident.status}</span>
            <span className="inc-ctx-age" title={incident.updated_at}>
              Updated {formatRelativeAge(incident.updated_at)}
            </span>
          </div>
        )}
      </div>
      {showTabs && current && <IncidentWorkflowNav incidentId={incidentId} current={current} />}
    </div>
  );
}
