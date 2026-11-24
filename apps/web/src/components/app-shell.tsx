"use client";
import { usePathname } from "next/navigation";

import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { primaryNavigation, secondaryNavigation, type NavigationItem } from "@/lib/navigation";
import { ProductIcon } from "@/components/product-icon";

function NavigationGroup({ items, label }: { items: readonly NavigationItem[]; label: string }) {
  const pathname = usePathname();
  return (
    <div className="nav-group" role="group" aria-label={label}>
      <p className="nav-heading">{label}</p>
      {items.map((item) =>
        item.href ? (
          <Link key={item.label} className={pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href + "/")) ? "nav-item is-active" : "nav-item"} href={item.href} aria-current={pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href + "/")) ? "page" : undefined}>
            <ProductIcon name={item.icon} />
            <span>{item.label}</span>
          </Link>
        ) : (
          <button key={item.label} type="button" className="nav-item" disabled>
            <ProductIcon name={item.icon} />
            <span>{item.label}</span>
          </button>
        ),
      )}
    </div>
  );
}

function breadcrumbLabel(pathname: string): string {
  if (pathname === "/") return "Overview";
  if (pathname === "/profile") return "Profile";
  if (pathname === "/incidents") return "Incidents";
  if (pathname === "/incidents/new") return "New incident";
  if (pathname.endsWith("/sources")) return "Evidence & sources";
  if (pathname.endsWith("/analysis")) return "Incident analysis";
  if (pathname.endsWith("/relationships")) return "Relationships";
  if (pathname.endsWith("/evidence-snapshots")) return "Evidence snapshots";
  if (pathname.includes("/investigations")) return "AI investigations";
  if (pathname.includes("/reports")) return "Postmortems";
  if (pathname.startsWith("/incidents/")) return "Incident details";
  return "Workspace";
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <Link href="/" className="brand" aria-label="IncidentForge home">
          <Image
            src="/incidentforge-mark.svg"
            alt=""
            width={36}
            height={36}
            className="brand-logo"
            priority
          />
          <span>IncidentForge</span>
        </Link>
        <nav className="side-nav" aria-label="Workspace sections">
          <NavigationGroup label="Workspace" items={primaryNavigation} />
          <NavigationGroup label="Account" items={secondaryNavigation} />
        </nav>
        <div className="sidebar-bottom">Incident operations</div>
      </aside>

      <div className="app-main">
        <header className="app-header">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span aria-hidden="true">/</span>
            <strong>{breadcrumbLabel(pathname)}</strong>
          </div>
          <div className="header-actions">
            <Link className="search-control" href="/incidents">
              <ProductIcon name="search" size={16} />
              <span>Browse incidents</span>
            </Link>
            <span className="workspace-label">Local workspace</span>
          </div>
        </header>
        <main
          className="workspace-content"
          id="main-content"
          tabIndex={-1}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
