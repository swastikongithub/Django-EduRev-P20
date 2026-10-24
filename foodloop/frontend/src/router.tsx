import { createBrowserRouter } from "react-router";

import { Layout } from "./components/Layout";
import { RequireRole } from "./components/RequireRole";
import { AdminPage } from "./pages/admin/AdminPage";
import { LoginPage, RegisterKitchenPage, RegisterPage } from "./pages/AuthPages";
import { BrowsePage } from "./pages/BrowsePage";
import { KitchenDashboardPage } from "./pages/kitchen/KitchenDashboardPage";
import { ListingFormPage } from "./pages/kitchen/ListingFormPage";
import { LandingPage } from "./pages/LandingPage";
import { PrivacyPage, TermsPage } from "./pages/LegalPages";
import { ListingDetailPage } from "./pages/ListingDetailPage";
import { MyReservationsPage } from "./pages/MyReservationsPage";
import { NotFoundPage, RouteError } from "./pages/NotFoundPage";

export const router = createBrowserRouter([
  {
    element: <Layout />,
    errorElement: <RouteError />,
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
      { path: "kitchen", element: <RequireRole role="provider"><KitchenDashboardPage /></RequireRole> },
      { path: "kitchen/listings/new", element: <RequireRole role="provider"><ListingFormPage /></RequireRole> },
      { path: "kitchen/listings/:id/edit", element: <RequireRole role="provider"><ListingFormPage /></RequireRole> },
      { path: "admin", element: <RequireRole role="admin"><AdminPage /></RequireRole> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
