import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IncidentForge | Incident Overview",
  description: "Incident investigation and operational analysis workspace.",
  icons: {
  icon: "/incidentforge-mark.svg",
},
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
