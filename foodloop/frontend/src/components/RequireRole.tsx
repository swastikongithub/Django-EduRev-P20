import { Lock } from "lucide-react";
import type { ReactNode } from "react";
import { Link, Navigate, useLocation } from "react-router";

import { useMe } from "../api/queries";
import type { Role } from "../api/types";
import { EmptyState, ErrorState, PageLoader } from "./ui";

const HOME: Record<Role, string> = { customer: "/meals", provider: "/kitchen", admin: "/admin" };
const AREA: Record<Role, string> = { customer: "customers", provider: "registered kitchens", admin: "FoodLoop admins" };

/** Client-side guard for nicer navigation. The real protection is on the server: every API route checks the role. */
export function RequireRole({ role, children }: { role: Role | "any"; children: ReactNode }) {
  const { data: me, isLoading, error, refetch } = useMe();
  const location = useLocation();
  if (isLoading) return <PageLoader />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  if (role !== "any" && me.user.role !== role) {
    return (
      <EmptyState
        icon={<Lock className="size-7" />}
        title="This page isn't for your account"
        action={
          <Link to={HOME[me.user.role]} className="btn-primary">
            Go to your page
          </Link>
        }
      >
        This area is only for {AREA[role]}.
      </EmptyState>
    );
  }
  return <>{children}</>;
}
