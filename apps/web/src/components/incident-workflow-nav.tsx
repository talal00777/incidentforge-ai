import Link from "next/link";

export type IncidentStage =
  | "overview"
  | "war-room"
  | "sources"
  | "analysis"
  | "relationships"
  | "snapshots"
  | "investigations"
  | "reports";

type StageDefinition = Readonly<{
  key: IncidentStage;
  label: string;
  suffix: string;
}>;

const STAGES: readonly StageDefinition[] = [
  { key: "overview", label: "Overview", suffix: "" },
  { key: "war-room", label: "War room", suffix: "/war-room" },
  { key: "sources", label: "Logs", suffix: "/sources" },
  { key: "analysis", label: "Analysis", suffix: "/analysis" },
  { key: "relationships", label: "Topology", suffix: "/relationships" },
  { key: "snapshots", label: "Snapshots", suffix: "/evidence-snapshots" },
  { key: "investigations", label: "AI", suffix: "/investigations" },
  { key: "reports", label: "Postmortems", suffix: "/reports" },
];

export function IncidentWorkflowNav({
  incidentId,
  current,
  className = "workflow-tabs",
}: {
  incidentId: string;
  current: IncidentStage;
  className?: string;
}) {
  const base = `/incidents/${encodeURIComponent(incidentId)}`;
  return (
    <nav className={className} aria-label="Incident workflow">
      {STAGES.map((stage) => (
        <Link
          key={stage.key}
          href={`${base}${stage.suffix}`}
          className={stage.key === current ? "workflow-tab is-active" : "workflow-tab"}
          aria-current={stage.key === current ? "page" : undefined}
        >
          {stage.label}
        </Link>
      ))}
    </nav>
  );
}
