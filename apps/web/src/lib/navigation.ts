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
];

export const secondaryNavigation: readonly NavigationItem[] = [
  { label: "Profile", icon: "settings", href: "/profile" },
];
