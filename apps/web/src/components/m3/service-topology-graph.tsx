"use client";

import { useMemo, useState } from "react";

export type TopologyTransition = Readonly<{
  from_service: string;
  to_service: string;
  count: number;
  event_ids: string[];
}>;

export type TopologyTimelineEvent = Readonly<{
  id: string;
  severity: string;
  service: string;
}>;

type NodeLayout = {
  id: string;
  x: number;
  y: number;
  totalEvents: number;
  errorEvents: number;
  health: "critical" | "degraded" | "healthy";
};

const ERROR_LEVELS = new Set(["ERROR", "FATAL", "CRITICAL"]);

export function computeTopologyLayout(
  transitions: readonly TopologyTransition[],
  timeline: readonly TopologyTimelineEvent[],
): { nodes: NodeLayout[]; width: number; height: number } {
  const serviceSet = new Set<string>();
  const outgoing = new Map<string, Set<string>>();
  const inDegree = new Map<string, number>();

  for (const edge of transitions) {
    serviceSet.add(edge.from_service);
    serviceSet.add(edge.to_service);
    if (!outgoing.has(edge.from_service)) outgoing.set(edge.from_service, new Set());
    outgoing.get(edge.from_service)!.add(edge.to_service);
    inDegree.set(edge.to_service, (inDegree.get(edge.to_service) ?? 0) + 1);
    if (!inDegree.has(edge.from_service)) inDegree.set(edge.from_service, 0);
  }
  for (const ev of timeline) {
    if (ev.service) serviceSet.add(ev.service);
  }

  const allServices = Array.from(serviceSet).sort();
  if (allServices.length === 0) {
    return { nodes: [], width: 860, height: 260 };
  }

  // Compute topological depth (BFS from roots; gracefully handles cycles)
  const depth = new Map<string, number>();
  const roots = allServices.filter((svc) => (inDegree.get(svc) ?? 0) === 0);
  const queue = roots.length > 0 ? [...roots] : [allServices[0]];
  for (const r of queue) depth.set(r, 0);

  let head = 0;
  while (head < queue.length) {
    const current = queue[head++];
    const currentDepth = depth.get(current) ?? 0;
    for (const next of outgoing.get(current) ?? []) {
      const candidate = Math.min(currentDepth + 1, 5);
      if (!depth.has(next)) {
        depth.set(next, candidate);
        queue.push(next);
      }
    }
  }
  for (const svc of allServices) {
    if (!depth.has(svc)) depth.set(svc, 0);
  }

  const columns = new Map<number, string[]>();
  for (const svc of allServices) {
    const col = depth.get(svc) ?? 0;
    if (!columns.has(col)) columns.set(col, []);
    columns.get(col)!.push(svc);
  }

  const sortedCols = Array.from(columns.keys()).sort((a, b) => a - b);
  const maxRows = Math.max(1, ...sortedCols.map((c) => columns.get(c)!.length));
  const width = Math.max(940, sortedCols.length * 290 + 140);
  const height = Math.max(320, maxRows * 130 + 90);

  const eventStats = new Map<string, { total: number; errors: number }>();
  for (const ev of timeline) {
    if (!ev.service) continue;
    const entry = eventStats.get(ev.service) ?? { total: 0, errors: 0 };
    entry.total += 1;
    if (ERROR_LEVELS.has((ev.severity || "").toUpperCase())) entry.errors += 1;
    eventStats.set(ev.service, entry);
  }

  const nodes: NodeLayout[] = [];
  const xMargin = 148;
  const usableW = Math.max(1, width - xMargin * 2);

  sortedCols.forEach((colKey, colIdx) => {
    const colServices = columns.get(colKey)!;
    const x =
      sortedCols.length === 1
        ? width / 2
        : xMargin + (colIdx / (sortedCols.length - 1)) * usableW;
    const stepY = height / (colServices.length + 1);
    colServices.forEach((svc, rowIdx) => {
      const stats = eventStats.get(svc) ?? { total: 0, errors: 0 };
      const ratio = stats.total > 0 ? stats.errors / stats.total : 0;
      const health: NodeLayout["health"] =
        stats.errors > 0 && ratio >= 0.3
          ? "critical"
          : stats.errors > 0
            ? "degraded"
            : "healthy";
      nodes.push({
        id: svc,
        x: Math.round(x),
        y: Math.round(stepY * (rowIdx + 1)),
        totalEvents: stats.total,
        errorEvents: stats.errors,
        health,
      });
    });
  });

  return { nodes, width, height };
}

export function ServiceTopologyGraph({
  transitions,
  timeline,
  selectedTransition,
  selectedService,
  onSelectTransition,
  onSelectService,
}: {
  transitions: readonly TopologyTransition[];
  timeline: readonly TopologyTimelineEvent[];
  selectedTransition: number | null;
  selectedService: string | null;
  onSelectTransition: (index: number | null) => void;
  onSelectService: (service: string | null) => void;
}) {
  const [zoom, setZoom] = useState(1);

  const layout = useMemo(
    () => computeTopologyLayout(transitions, timeline),
    [transitions, timeline],
  );
  const nodeMap = useMemo(
    () => new Map(layout.nodes.map((node) => [node.id, node])),
    [layout.nodes],
  );

  if (layout.nodes.length === 0) {
    return null;
  }

  const NODE_W = 204;
  const NODE_H = 78;

  return (
    <section className="topo-card" aria-labelledby="topology-graph-heading">
      <div className="topo-header">
        <div>
          <h2 id="topology-graph-heading">Service dependency topology</h2>
          <p>
            Click any service node or directed transition edge to isolate correlated evidence below.
          </p>
        </div>
        <div className="topo-controls">
          <div className="topo-legend" aria-hidden="true">
            <span><i className="topo-dot is-critical" /> High error</span>
            <span><i className="topo-dot is-degraded" /> Errors observed</span>
            <span><i className="topo-dot is-healthy" /> Healthy</span>
          </div>
          <div className="topo-zoom-group" role="group" aria-label="Topology zoom">
            <button type="button" onClick={() => setZoom((z) => Math.max(0.75, +(z - 0.15).toFixed(2)))} aria-label="Zoom out">−</button>
            <button type="button" onClick={() => setZoom(1)} aria-label="Reset zoom">{Math.round(zoom * 100)}%</button>
            <button type="button" onClick={() => setZoom((z) => Math.min(1.45, +(z + 0.15).toFixed(2)))} aria-label="Zoom in">+</button>
          </div>
          {(selectedService || selectedTransition !== null) && (
            <button
              type="button"
              className="topo-clear-btn"
              onClick={() => {
                onSelectService(null);
                onSelectTransition(null);
              }}
            >
              Clear focus
            </button>
          )}
        </div>
      </div>

      <div className="topo-canvas-scroll">
        <svg
          className="topo-svg"
          role="group"
          aria-label="Interactive service dependency topology map"
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          style={{ width: `${Math.round(zoom * 100)}%`, minWidth: `${Math.round(layout.width * 0.72)}px` }}
        >
          <defs>
            <marker
              id="topo-arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 10 5 L 0 8.5 z" className="topo-arrow-fill" />
            </marker>
            <marker
              id="topo-arrow-active"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 10 5 L 0 8.5 z" className="topo-arrow-active-fill" />
            </marker>
          </defs>

          {/* Subtle technical dot grid */}
          <pattern id="topo-dots" width="24" height="24" patternUnits="userSpaceOnUse">
            <circle cx="2" cy="2" r="1" className="topo-grid-dot" />
          </pattern>
          <rect x="0" y="0" width={layout.width} height={layout.height} fill="url(#topo-dots)" />

          {/* Directed Edges */}
          {transitions.map((edge, index) => {
            const src = nodeMap.get(edge.from_service);
            const dst = nodeMap.get(edge.to_service);
            if (!src || !dst) return null;

            const forward = dst.x >= src.x;
            const x1 = forward ? src.x + NODE_W / 2 : src.x - NODE_W / 2;
            const y1 = src.y;
            const x2 = forward ? dst.x - NODE_W / 2 - 4 : dst.x + NODE_W / 2 + 4;
            const y2 = dst.y;
            const dx = Math.max(48, Math.abs(x2 - x1) * 0.45);
            const c1x = forward ? x1 + dx : x1 - dx;
            const c2x = forward ? x2 - dx : x2 + dx;
            const d = `M ${x1} ${y1} C ${c1x} ${y1}, ${c2x} ${y2}, ${x2} ${y2}`;
            const midX = (x1 + x2) / 2;
            const midY = (y1 + y2) / 2 - (src.y === dst.y ? 0 : 4);

            const isSelected = selectedTransition === index;
            const isTouchingService =
              selectedService !== null &&
              (edge.from_service === selectedService || edge.to_service === selectedService);
            const isDimmed =
              (selectedTransition !== null && !isSelected) ||
              (selectedService !== null && !isTouchingService);

            return (
              <g
                key={`${edge.from_service}->${edge.to_service}`}
                className={`topo-edge ${isSelected || isTouchingService ? "is-active" : ""} ${isDimmed ? "is-dimmed" : ""}`}
                onClick={() => {
                  onSelectService(null);
                  onSelectTransition(isSelected ? null : index);
                }}
              >
                <path d={d} className="topo-edge-hit" />
                <path
                  d={d}
                  className="topo-edge-path"
                  markerEnd={isSelected || isTouchingService ? "url(#topo-arrow-active)" : "url(#topo-arrow)"}
                />
                <g transform={`translate(${midX}, ${midY})`}>
                  <rect x="-24" y="-13" width="48" height="26" rx="13" className="topo-edge-pill" />
                  <text x="0" y="5" textAnchor="middle" className="topo-edge-label">
                    {edge.count}×
                  </text>
                </g>
              </g>
            );
          })}

          {/* Service Nodes */}
          {layout.nodes.map((node) => {
            const isSelected = selectedService === node.id;
            const isDimmed =
              (selectedService !== null && !isSelected) ||
              (selectedTransition !== null &&
                transitions[selectedTransition]?.from_service !== node.id &&
                transitions[selectedTransition]?.to_service !== node.id);

            return (
              <g
                key={node.id}
                transform={`translate(${node.x - NODE_W / 2}, ${node.y - NODE_H / 2})`}
                className={`topo-node is-${node.health} ${isSelected ? "is-selected" : ""} ${isDimmed ? "is-dimmed" : ""}`}
                role="button"
                tabIndex={0}
                aria-pressed={isSelected}
                aria-label={`Service ${node.id}: ${node.errorEvents} errors out of ${node.totalEvents} events`}
                onClick={() => {
                  onSelectTransition(null);
                  onSelectService(isSelected ? null : node.id);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelectTransition(null);
                    onSelectService(isSelected ? null : node.id);
                  }
                }}
              >
                <rect width={NODE_W} height={NODE_H} rx="12" className="topo-node-box" />
                <rect x="0" y="12" width="5" height={NODE_H - 24} rx="2.5" className="topo-node-accent" />
                <circle cx="24" cy="27" r="5.5" className="topo-node-dot" />
                <text x="38" y="32" className="topo-node-name">
                  {node.id.length > 18 ? `${node.id.slice(0, 17)}…` : node.id}
                </text>
                <text x="20" y="58" className="topo-node-stats">
                  {node.totalEvents} ev · {node.errorEvents} err
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </section>
  );
}
