import { AppShell } from "@/components/app-shell";
import { ProfileForm } from "@/components/m1/profile-form";

export default function ProfilePage() {
  return <><a className="skip-link" href="#main-content">Skip to main content</a><AppShell><header className="page-heading"><div><p className="page-overline">Account</p><h1>Profile</h1><p className="page-subtitle">Update your profile information.</p></div></header><ProfileForm /></AppShell></>;
}
