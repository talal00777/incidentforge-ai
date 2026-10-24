import type { ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { primaryNavigation, secondaryNavigation, type NavigationItem } from "@/lib/navigation";
import { ProductIcon } from "@/components/product-icon";

function NavigationGroup({ items, label }: { items: readonly NavigationItem[]; label: string }) {
  return (
    <div className="nav-group" role="group" aria-label={label}>
      <p className="nav-heading">{label}</p>
      {items.map((item) =>
        item.href ? (
          <a key={item.label} className="nav-item is-active" href={item.href} aria-current="page">
            <ProductIcon name={item.icon} />
            <span>{item.label}</span>
          </a>
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

export function AppShell({ children }: { children: ReactNode }) {
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
          <NavigationGroup label="Preferences" items={secondaryNavigation} />
        </nav>
        <div className="sidebar-bottom">Incident operations</div>
      </aside>

      <div className="app-main">
        <header className="app-header">
          <div className="breadcrumb"><span>Workspace</span><span aria-hidden="true">/</span><strong>Overview</strong></div>
          <div className="header-actions">
            <button className="search-control" type="button" disabled>
              <ProductIcon name="search" size={16} />
              <span>Search incidents</span>
            </button>
            <button className="icon-button" type="button" aria-label="Notifications" disabled>
              <ProductIcon name="bell" size={18} />
            </button>
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
