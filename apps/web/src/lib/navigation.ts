export type NavigationIcon =
  | "overview"
  | "incidents"
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
  { label: "Log explorer", icon: "logs" },
  { label: "Investigations", icon: "investigations" },
  { label: "Analytics", icon: "analytics" },
  { label: "Reports", icon: "reports" },
];

export const secondaryNavigation: readonly NavigationItem[] = [
  { label: "Settings", icon: "settings" },
];
