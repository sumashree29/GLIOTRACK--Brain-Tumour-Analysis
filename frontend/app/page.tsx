import { redirect } from "next/navigation";

// Root "/" always redirects to login.
// AuthGuard on /login will forward authenticated users to /dashboard.
export default function RootPage() {
  redirect("/login");
}
