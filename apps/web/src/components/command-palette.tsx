"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiGet, type Incident, type IncidentPage } from "@/lib/api-client";
import { seedDemoScenario } from "@/lib/dashboard-api";
import { useTheme } from "@/components/theme-provider";

type CommandItem = Readonly<{
  id: string;
  group: "Current incident" | "Actions" | "Incidents";
  label: string;
  hint: string;
  keywords: string;
  run: () => void | Promise<void>;
}>;

const INCIDENT_PATH_RE = /^\/incidents\/([0-9a-f-]{8,})(?:\/|$)/i;

function CommandPaletteDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [busyMessage, setBusyMessage] = useState("");

  const activeIncidentId = useMemo(() => {
    const match = INCIDENT_PATH_RE.exec(pathname);
    return match ? match[1] : null;
  }, [pathname]);

  useEffect(() => {
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 10);

    let active = true;
    apiGet<IncidentPage>("incidents?page_size=25")
      .then((page) => {
        if (active) setIncidents(page.results);
      })
      .catch(() => {
        if (active) setIncidents([]);
      });
    return () => {
      active = false;
      window.clearTimeout(focusTimer);
    };
  }, []);

  const commands = useMemo<CommandItem[]>(() => {
    const list: CommandItem[] = [];

    if (activeIncidentId) {
      const encoded = encodeURIComponent(activeIncidentId);
      const stages: [string, string, string][] = [
        ["Overview & metadata", `/incidents/${encoded}`, "details record edit status"],
        ["Logs & sources", `/incidents/${encoded}/sources`, "upload evidence events search"],
        ["Analytics & anomaly timeline", `/incidents/${encoded}/analysis`, "charts buckets errors mad"],
        ["Service relationships", `/incidents/${encoded}/relationships`, "traces transitions correlation"],
        ["Evidence snapshots", `/incidents/${encoded}/evidence-snapshots`, "redacted consent preview"],
        ["AI investigations", `/incidents/${encoded}/investigations`, "llm hypotheses generate review"],
        ["Postmortems & exports", `/incidents/${encoded}/reports`, "pdf json immutable version"],
      ];
      for (const [label, href, keywords] of stages) {
        list.push({
          id: `stage:${href}`,
          group: "Current incident",
          label,
          hint: "Jump to stage",
          keywords,
          run: () => {
            onClose();
            router.push(href);
          },
        });
      }
    }

    list.push(
      {
        id: "action:new-incident",
        group: "Actions",
        label: "Create new incident",
        hint: "/incidents/new",
        keywords: "new create open outage",
        run: () => {
          onClose();
          router.push("/incidents/new");
        },
      },
      {
        id: "action:incidents",
        group: "Actions",
        label: "Browse all incidents",
        hint: "/incidents",
        keywords: "list search filter",
        run: () => {
          onClose();
          router.push("/incidents");
        },
      },
      {
        id: "action:overview",
        group: "Actions",
        label: "Operational overview",
        hint: "/",
        keywords: "home dashboard metrics",
        run: () => {
          onClose();
          router.push("/");
        },
      },
      {
        id: "action:theme",
        group: "Actions",
        label: theme === "dark" ? "Switch to Light mode" : "Switch to SRE Dark mode",
        hint: "Appearance",
        keywords: "theme dark light contrast appearance",
        run: () => {
          toggleTheme();
          onClose();
        },
      },
      {
        id: "action:demo-checkout",
        group: "Actions",
        label: "Seed demo outage: Checkout DB pool exhaustion",
        hint: "3 services · critical",
        keywords: "demo seed sample fixture checkout pool 503",
        run: async () => {
          setBusyMessage("Seeding Checkout DB pool outage…");
          try {
            const seeded = await seedDemoScenario("checkout-db-pool");
            onClose();
            router.push(`/incidents/${encodeURIComponent(seeded.incident.id)}/analysis`);
          } catch {
            setBusyMessage("Sign in required to seed a demo incident.");
          }
        },
      },
      {
        id: "action:profile",
        group: "Actions",
        label: "Account profile",
        hint: "/profile",
        keywords: "settings account session",
        run: () => {
          onClose();
          router.push("/profile");
        },
      },
    );

    for (const item of incidents) {
      list.push({
        id: `incident:${item.id}`,
        group: "Incidents",
        label: item.title,
        hint: `${item.service_name || "unassigned"} · ${item.severity} · ${item.status}`,
        keywords: `${item.title} ${item.service_name} ${item.severity} ${item.status} ${item.environment}`,
        run: () => {
          onClose();
          router.push(`/incidents/${encodeURIComponent(item.id)}`);
        },
      });
    }

    return list;
  }, [activeIncidentId, incidents, onClose, router, theme, toggleTheme]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.hint.toLowerCase().includes(q) ||
        item.keywords.toLowerCase().includes(q),
    );
  }, [commands, query]);

  const clampedIndex = filtered.length === 0 ? 0 : Math.min(activeIndex, filtered.length - 1);
  const groups: CommandItem["group"][] = ["Current incident", "Actions", "Incidents"];

  return (
    <div
      className="cmdk-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="cmdk-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onClose();
          } else if (event.key === "ArrowDown") {
            event.preventDefault();
            setActiveIndex((idx) => (filtered.length ? (idx + 1) % filtered.length : 0));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActiveIndex((idx) =>
              filtered.length ? (idx - 1 + filtered.length) % filtered.length : 0,
            );
          } else if (event.key === "Enter" && filtered[clampedIndex]) {
            event.preventDefault();
            void filtered[clampedIndex].run();
          }
        }}
      >
        <div className="cmdk-input-row">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            ref={inputRef}
            className="cmdk-input"
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            placeholder="Jump to incident, switch stage, toggle theme, or seed demo…"
            aria-label="Filter commands and incidents"
          />
          <kbd className="cmdk-kbd">Esc</kbd>
        </div>

        {busyMessage && (
          <div className="cmdk-status" role="status">
            {busyMessage}
          </div>
        )}

        <div className="cmdk-list" role="listbox" aria-label="Matching commands">
          {filtered.length === 0 ? (
            <p className="cmdk-empty">No matching incidents or commands for &ldquo;{query}&rdquo;.</p>
          ) : (
            groups.map((group) => {
              const items = filtered.filter((item) => item.group === group);
              if (items.length === 0) return null;
              return (
                <div className="cmdk-group" key={group}>
                  <p className="cmdk-group-label">{group}</p>
                  {items.map((item) => {
                    const flatIndex = filtered.indexOf(item);
                    const isSelected = flatIndex === clampedIndex;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        role="option"
                        aria-selected={isSelected}
                        className={isSelected ? "cmdk-item is-selected" : "cmdk-item"}
                        onMouseEnter={() => setActiveIndex(flatIndex)}
                        onClick={() => void item.run()}
                      >
                        <span className="cmdk-item-label">{item.label}</span>
                        <span className="cmdk-item-hint">{item.hint}</span>
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        <footer className="cmdk-footer">
          <span><kbd className="cmdk-kbd">↑↓</kbd> Navigate</span>
          <span><kbd className="cmdk-kbd">↵</kbd> Open</span>
          <span><kbd className="cmdk-kbd">Ctrl K</kbd> Toggle</span>
        </footer>
      </div>
    </div>
  );
}

export function CommandPalette({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  if (!open) return null;
  return <CommandPaletteDialog onClose={onClose} />;
}
