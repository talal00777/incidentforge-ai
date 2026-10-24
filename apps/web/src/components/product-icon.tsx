import type { ReactNode } from "react";

export type ProductIconName =
  | "overview"
  | "incidents"
  | "logs"
  | "investigations"
  | "analytics"
  | "reports"
  | "settings"
  | "search"
  | "plus"
  | "bell"
  | "inbox"
  | "activity"
  | "upload";

const paths: Record<ProductIconName, ReactNode> = {
  overview: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  incidents: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
  logs: <><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5" /></>,
  investigations: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5M8 10h5" /></>,
  analytics: <><path d="M4 20V4M4 20h16M8 16v-4M13 16V7M18 16v-8" /></>,
  reports: <><path d="M6 3h9l4 4v14H6zM15 3v5h4M9 13h7M9 17h7" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
  inbox: <><path d="M4 4h16l2 11v5H2v-5z" /><path d="M2 15h6l2 3h4l2-3h6" /></>,
  activity: <path d="M3 12h4l3-7 4 14 3-7h4" />,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5" /></>,
};

export function ProductIcon({ name, size = 18 }: { name: ProductIconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}
