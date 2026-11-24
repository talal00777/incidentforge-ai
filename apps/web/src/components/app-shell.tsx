"use client";

import { useEffect, useState, type ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { primaryNavigation, secondaryNavigation, type NavigationItem } from "@/lib/navigation";
import { ProductIcon } from "@/components/product-icon";
import { CommandPalette } from "@/components/command-palette";
import { useTheme } from "@/components/theme-provider";
import { useAccount } from "@/components/m1/use-account";
import { apiWrite } from "@/lib/api-client";

function NavigationGroup({
  items,
  label,
  collapsed,
}: {
  items: readonly NavigationItem[];
  label: string;
  collapsed: boolean;
}) {
  const pathname = usePathname();
  return (
    <div className="nav-group" role="group" aria-label={label}>
      {!collapsed && <p className="nav-heading">{label}</p>}
      {items.map((item) => {
        const active =
          item.href !== undefined &&
          (pathname === item.href || (item.href !== "/" && pathname.startsWith(`${item.href}/`)));
        return item.href ? (
          <Link
            key={item.label}
            className={active ? "nav-item is-active" : "nav-item"}
            href={item.href}
            aria-current={active ? "page" : undefined}
            title={collapsed ? item.label : undefined}
          >
            <ProductIcon name={item.icon} />
            {!collapsed && <span>{item.label}</span>}
          </Link>
        ) : (
          <button key={item.label} type="button" className="nav-item" disabled>
            <ProductIcon name={item.icon} />
            {!collapsed && <span>{item.label}</span>}
          </button>
        );
      })}
    </div>
  );
}

function breadcrumbTrail(pathname: string): Array<{ label: string; href?: string }> {
  if (pathname === "/") return [{ label: "Overview" }];
  if (pathname === "/profile") return [{ label: "Profile" }];
  if (pathname === "/incidents") return [{ label: "Incidents" }];
  if (pathname === "/incidents/new") {
    return [{ label: "Incidents", href: "/incidents" }, { label: "New incident" }];
  }
  const match = /^\/incidents\/([^/]+)(?:\/(.*))?$/.exec(pathname);
  if (match) {
    const incidentId = match[1];
    const rest = match[2] || "";
    const base = `/incidents/${incidentId}`;
    const trail: Array<{ label: string; href?: string }> = [
      { label: "Incidents", href: "/incidents" },
      { label: `INC-${incidentId.slice(0, 6).toUpperCase()}`, href: rest ? base : undefined },
    ];
    if (rest === "sources") trail.push({ label: "Logs & sources" });
    else if (rest === "analysis") trail.push({ label: "Analysis" });
    else if (rest === "relationships") trail.push({ label: "Relationships" });
    else if (rest === "evidence-snapshots") trail.push({ label: "Snapshots" });
    else if (rest.endsWith("/review")) trail.push({ label: "Human review" });
    else if (rest.startsWith("investigations/")) trail.push({ label: "AI findings" });
    else if (rest === "investigations") trail.push({ label: "AI investigations" });
    else if (rest.startsWith("reports/")) trail.push({ label: "Postmortem version" });
    else if (rest === "reports") trail.push({ label: "Postmortems" });
    return trail;
  }
  return [{ label: "Workspace" }];
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();
  const account = useAccount();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((current) => !current);
        return;
      }
      const target = event.target as HTMLElement | null;
      const editing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      if (!editing && !event.metaKey && !event.ctrlKey && !event.altKey && event.key === "[") {
        setCollapsed((current) => !current);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await apiWrite<void>("auth/logout", "POST");
      router.replace("/login");
      router.refresh();
    } finally {
      setSigningOut(false);
    }
  }

  const trail = breadcrumbTrail(pathname);
  const initials =
    account.state === "signed-in"
      ? (account.user.first_name?.[0] || account.user.email[0] || "U").toUpperCase()
      : "";

  return (
    <div className={collapsed ? "app-shell is-collapsed" : "app-shell"}>
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="sidebar-brand-row">
          <Link href="/" className="brand" aria-label="IncidentForge home">
            <Image
              src="/incidentforge-mark.svg"
              alt=""
              width={30}
              height={30}
              className="brand-logo"
              priority
            />
            {!collapsed && <span>IncidentForge</span>}
          </Link>
          <button
            type="button"
            className="sidebar-collapse-btn"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar ([)" : "Collapse sidebar ([)"}
            onClick={() => setCollapsed((c) => !c)}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              {collapsed ? <path d="m9 18 6-6-6-6" /> : <path d="m15 18-6-6 6-6" />}
            </svg>
          </button>
        </div>

        <nav className="side-nav" aria-label="Workspace sections">
          <NavigationGroup label="Workspace" items={primaryNavigation} collapsed={collapsed} />
          <NavigationGroup label="Account" items={secondaryNavigation} collapsed={collapsed} />
        </nav>

        <div className="sidebar-bottom">
          {collapsed ? (
            <button
              type="button"
              className="sidebar-cmd-icon"
              aria-label="Open command palette"
              title="Command palette (Ctrl+K)"
              onClick={() => setPaletteOpen(true)}
            >
              ⌘K
            </button>
          ) : (
            <div className="sidebar-meta-row">
              <span>Local workbench</span>
              <kbd className="sidebar-kbd">Ctrl K</kbd>
            </div>
          )}
        </div>
      </aside>

      <div className="app-main">
        <header className="app-header">
          <nav className="breadcrumb" aria-label="Breadcrumb">
            <Link href="/" className="breadcrumb-root">Workspace</Link>
            {trail.map((crumb) => (
              <span key={crumb.label} className="breadcrumb-segment">
                <span aria-hidden="true" className="breadcrumb-sep">/</span>
                {crumb.href ? (
                  <Link href={crumb.href} className="breadcrumb-link">{crumb.label}</Link>
                ) : (
                  <strong>{crumb.label}</strong>
                )}
              </span>
            ))}
          </nav>

          <div className="header-actions">
            <button
              type="button"
              className="search-control"
              onClick={() => setPaletteOpen(true)}
              aria-label="Open command palette"
            >
              <ProductIcon name="search" size={15} />
              <span className="search-control-label">Search or jump…</span>
              <kbd className="header-kbd">Ctrl K</kbd>
            </button>

            <button
              type="button"
              className="theme-toggle-btn"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              title={theme === "dark" ? "Switch to light mode" : "Switch to SRE dark mode"}
            >
              {theme === "dark" ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              )}
            </button>

            {account.state === "signed-in" ? (
              <div className="header-user">
                <Link href="/profile" className="header-user-pill" title={account.user.email}>
                  <span className="header-avatar" aria-hidden="true">{initials}</span>
                  <span className="header-user-email">{account.user.email}</span>
                </Link>
                <button
                  type="button"
                  className="header-signout-btn"
                  disabled={signingOut}
                  onClick={() => void handleSignOut()}
                >
                  Sign out
                </button>
              </div>
            ) : account.state === "signed-out" ? (
              <Link href="/login" className="header-signin-link">
                Sign in
              </Link>
            ) : null}
          </div>
        </header>

        <main className="workspace-content" id="main-content" tabIndex={-1}>
          {children}
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
