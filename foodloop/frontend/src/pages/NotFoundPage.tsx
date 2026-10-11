import { CircleAlert, Compass } from "lucide-react";
import { isRouteErrorResponse, Link, useRouteError } from "react-router";

import { EmptyState } from "../components/ui";

export function NotFoundPage() {
  return (
    <EmptyState
      icon={<Compass className="size-7" />}
      title="We couldn't find that page"
      action={
        <Link to="/meals" className="btn-primary">
          Browse meals
        </Link>
      }
    >
      The link may be old, or the meal may have been collected already.
    </EmptyState>
  );
}

/** Shown if a page crashes, instead of a blank screen. */
export function RouteError() {
  const error = useRouteError();
  const status = isRouteErrorResponse(error) ? error.status : null;
  if (status === 404) return <NotFoundPage />;
  return (
    <div className="grid min-h-dvh place-items-center bg-cream-100 px-4">
      <EmptyState
        icon={<CircleAlert className="size-7" />}
        title="Something went wrong"
        action={
          <a href="/" className="btn-primary">
            Back to FoodLoop
          </a>
        }
      >
        Please reload the page. If it keeps happening, tell the FoodLoop team what you were doing.
      </EmptyState>
    </div>
  );
}
