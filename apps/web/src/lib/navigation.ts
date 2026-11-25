export type NavigationIcon =
  | "overview"
  | "incidents"
  | "workspaces"
  | "logs"
  | "investigations"
  | "analytics"
  | "reports"
  | "settings";

export type NavigationItem = Readonly<{
  label: string;
  icon: NavigationIcon;
  href?: string;
}>;

export const primaryNavigation: readonly NavigationItem[] = [
  { label: "Overview", icon: "overview", href: "/" },
  { label: "Incidents", icon: "incidents", href: "/incidents" },
  { label: "Workspaces", icon: "workspaces", href: "/workspaces" },
];

export const secondaryNavigation: readonly NavigationItem[] = [
  { label: "Profile", icon: "settings", href: "/profile" },
];
