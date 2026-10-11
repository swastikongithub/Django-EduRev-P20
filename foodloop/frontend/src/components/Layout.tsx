import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChefHat, LogOut, Menu, Search, ShieldCheck, Ticket, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, ScrollRestoration, useLocation, useNavigate } from "react-router";

import { api } from "../api/client";
import { useMe } from "../api/queries";
import type { Me } from "../api/types";
import { Logo } from "./Logo";

function navItems(me: Me | null | undefined) {
  const items = [{ to: "/meals", label: "Browse meals", icon: Search }];
  if (me?.user.role === "customer") items.push({ to: "/reservations", label: "My reservations", icon: Ticket });
  if (me?.user.role === "provider") items.push({ to: "/kitchen", label: "Kitchen dashboard", icon: ChefHat });
  if (me?.user.role === "admin") items.push({ to: "/admin", label: "Admin", icon: ShieldCheck });
  return items;
}

function Header() {
  const { data: me, isLoading } = useMe();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: () => api<void>("/auth/logout", { method: "POST" }),
    onSettled: () => {
      queryClient.clear();
      navigate("/");
    },
  });

  useEffect(() => setOpen(false), [location.pathname]);

  const items = navItems(me);
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `inline-flex min-h-10 items-center gap-2 rounded-full px-3.5 text-sm font-semibold transition ${
      isActive ? "bg-leaf-50 text-leaf-800" : "text-ink-600 hover:bg-cream-200 hover:text-ink-900"
    }`;

  return (
    <header className="sticky top-0 z-40 border-b border-line/70 bg-cream-100/85 backdrop-blur-lg">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Logo />
        <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClass}>
              <item.icon className="size-4" aria-hidden="true" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          {isLoading ? null : me ? (
            <>
              <span className="max-w-40 truncate text-sm text-ink-600" title={me.user.email}>
                Hi, {me.user.full_name.split(" ")[0]}
              </span>
              <button type="button" className="btn-ghost btn-sm" onClick={() => logout.mutate()}>
                <LogOut className="size-4" aria-hidden="true" /> Log out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn-ghost btn-sm">
                Log in
              </Link>
              <Link to="/register" className="btn-primary btn-sm">
                Sign up
              </Link>
            </>
          )}
        </div>
        <button
          type="button"
          className="btn-ghost -mr-2 px-3 md:hidden"
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X className="size-5" /> : <Menu className="size-5" />}
          <span className="sr-only">Menu</span>
        </button>
      </div>
      {open && (
        <div id="mobile-menu" className="animate-rise border-t border-line/70 bg-cream-50 px-4 pt-3 pb-5 md:hidden">
          <nav aria-label="Mobile" className="flex flex-col gap-1">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} className={linkClass}>
                <item.icon className="size-4" aria-hidden="true" />
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-4 flex gap-2 border-t border-line pt-4">
            {me ? (
              <button type="button" className="btn-secondary w-full" onClick={() => logout.mutate()}>
                <LogOut className="size-4" aria-hidden="true" /> Log out
              </button>
            ) : (
              <>
                <Link to="/login" className="btn-secondary flex-1">
                  Log in
                </Link>
                <Link to="/register" className="btn-primary flex-1">
                  Sign up
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}

function Footer() {
  return (
    <footer className="mt-20 border-t border-line bg-cream-50">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <Logo />
          <p className="font-display mt-4 text-lg text-ink-700 italic">Good food. Less waste.</p>
          <p className="mt-3 max-w-sm text-sm leading-relaxed text-ink-500">
            FoodLoop connects FSSAI-registered kitchens that have safe, unsold food with people who want an affordable
            meal. Pickup only, before the eat-by time.
          </p>
        </div>
        <div>
          <h2 className="text-sm font-bold text-ink-900">For you</h2>
          <ul className="mt-3 space-y-2 text-sm text-ink-600">
            <li><Link className="hover:text-leaf-700" to="/meals">Browse meals</Link></li>
            <li><Link className="hover:text-leaf-700" to="/register">Create an account</Link></li>
            <li><a className="hover:text-leaf-700" href="/#safety">How we keep food safe</a></li>
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-bold text-ink-900">For kitchens</h2>
          <ul className="mt-3 space-y-2 text-sm text-ink-600">
            <li><Link className="hover:text-leaf-700" to="/register/kitchen">Register your kitchen</Link></li>
            <li><Link className="hover:text-leaf-700" to="/kitchen">Kitchen dashboard</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-6xl px-4 py-5 text-xs leading-relaxed text-ink-500 sm:px-6">
          Kitchens are responsible for the food they list and must hold valid FSSAI registration. Anything marked
          “Sample data” is fictional and exists only for development.
        </p>
      </div>
    </footer>
  );
}

export function Layout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-full bg-ink-900 px-4 py-2 text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <Header />
      <main id="main" className="flex-1">
        <Outlet />
      </main>
      <Footer />
      <ScrollRestoration />
    </div>
  );
}
