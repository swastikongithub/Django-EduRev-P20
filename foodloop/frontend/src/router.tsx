import { createBrowserRouter } from "react-router";

import { Layout } from "./components/Layout";
import { RequireRole } from "./components/RequireRole";
import { PageLoader } from "./components/ui";
import { LoginPage, RegisterKitchenPage, RegisterPage } from "./pages/AuthPages";
import { BrowsePage } from "./pages/BrowsePage";
import { LandingPage } from "./pages/LandingPage";
import { PrivacyPage, TermsPage } from "./pages/LegalPages";
import { ListingDetailPage } from "./pages/ListingDetailPage";
import { MyReservationsPage } from "./pages/MyReservationsPage";
import { NotFoundPage, RouteError } from "./pages/NotFoundPage";

// Kitchen and admin screens load on first visit, so customers never download them.
const kitchenDashboard = async () => {
  const { KitchenDashboardPage } = await import("./pages/kitchen/KitchenDashboardPage");
  return { element: <RequireRole role="provider"><KitchenDashboardPage /></RequireRole> };
};
const listingForm = async () => {
  const { ListingFormPage } = await import("./pages/kitchen/ListingFormPage");
  return { element: <RequireRole role="provider"><ListingFormPage /></RequireRole> };
};
const adminPage = async () => {
  const { AdminPage } = await import("./pages/admin/AdminPage");
  return { element: <RequireRole role="admin"><AdminPage /></RequireRole> };
};

export const router = createBrowserRouter([
  {
    element: <Layout />,
    errorElement: <RouteError />,
    // Shown for a moment when someone opens a kitchen or admin page directly, while its code downloads.
    hydrateFallbackElement: <PageLoader />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: "meals", element: <BrowsePage /> },
      { path: "meals/:id", element: <ListingDetailPage /> },
      { path: "login", element: <LoginPage /> },
      { path: "register", element: <RegisterPage /> },
      { path: "register/kitchen", element: <RegisterKitchenPage /> },
      { path: "privacy", element: <PrivacyPage /> },
      { path: "terms", element: <TermsPage /> },
      { path: "reservations", element: <RequireRole role="customer"><MyReservationsPage /></RequireRole> },
      { path: "kitchen", lazy: kitchenDashboard },
      { path: "kitchen/listings/new", lazy: listingForm },
      { path: "kitchen/listings/:id/edit", lazy: listingForm },
      { path: "admin", lazy: adminPage },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
