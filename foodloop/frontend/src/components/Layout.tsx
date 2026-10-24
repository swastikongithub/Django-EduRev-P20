import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChefHat, LogOut, Mail, Menu, ShieldCheck, Ticket, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, ScrollRestoration, useLocation, useNavigate } from "react-router";

import { api } from "../api/client";
import { useMe } from "../api/queries";
import type { Me } from "../api/types";
import { Logo } from "./Logo";

const PUBLIC_LINKS = [
  { to: "/", label: "Home", end: true },
  { to: "/meals", label: "Explore Meals" },
  { to: "/#how-it-works", label: "How It Works", hash: "#how-it-works" },
  { to: "/#providers", label: "For Providers", hash: "#providers" },
];

function accountLink(me: Me | null | undefined) {
  if (me?.user.role === "customer") return { to: "/reservations", label: "My reservations", icon: Ticket };
  if (me?.user.role === "provider") return { to: "/kitchen", label: "Kitchen dashboard", icon: ChefHat };
  if (me?.user.role === "admin") return { to: "/admin", label: "Admin", icon: ShieldCheck };
  return null;
}

/** Scroll to /#section links (React Router doesn't do this by itself). */
function useHashScroll() {
  const { hash, pathname } = useLocation();
  useEffect(() => {
    if (!hash) return;
    const id = window.setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" }), 60);
    return () => window.clearTimeout(id);
  }, [hash, pathname]);
}

function Header() {
  const { data: me, isLoading } = useMe();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
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

  useEffect(() => setOpen(false), [location.pathname, location.hash]);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const account = accountLink(me);
  const isActive = (link: (typeof PUBLIC_LINKS)[number]) =>
    link.hash
      ? location.pathname === "/" && location.hash === link.hash
      : link.end
        ? location.pathname === "/" && !location.hash
        : location.pathname.startsWith(link.to);
  const linkClass = (active: boolean) =>
    `relative inline-flex min-h-10 items-center rounded-full px-3.5 text-[14.5px] font-semibold transition ${
      active ? "text-leaf-700" : "text-ink-600 hover:text-ink-900"
    }`;

  return (
    <header
      className={`sticky top-0 z-40 transition-[background-color,box-shadow,border-color] duration-300 ${
        scrolled || open
          ? "border-b border-line/70 bg-cream-50/90 shadow-[0_6px_24px_-18px_rgb(20_29_24/0.35)] backdrop-blur-xl"
          : "border-b border-transparent bg-cream-100/0"
      }`}
    >
      <div className="container-page flex h-[4.25rem] items-center justify-between gap-6">
        <Logo />
        <nav aria-label="Main" className="hidden items-center gap-0.5 lg:flex">
          {PUBLIC_LINKS.map((link) => (
            <Link key={link.label} to={link.to} className={linkClass(isActive(link))} aria-current={isActive(link) ? "page" : undefined}>
              {link.label}
              {isActive(link) && <span className="absolute inset-x-3.5 -bottom-0.5 h-0.5 rounded-full bg-leaf-600" />}
            </Link>
          ))}
        </nav>
        <div className="hidden items-center gap-2 lg:flex">
          {isLoading ? (
            <span className="h-9 w-40" />
          ) : me ? (
            <>
              {account && (
                <NavLink
                  to={account.to}
                  className={({ isActive: active }) =>
                    `btn-sm btn ${active ? "bg-leaf-50 text-leaf-800" : "text-ink-700 hover:bg-cream-200"}`
                  }
                >
                  <account.icon className="size-4" aria-hidden="true" /> {account.label}
                </NavLink>
              )}
              <span className="mx-1 h-6 w-px bg-line" aria-hidden="true" />
              <span className="max-w-32 truncate text-sm text-ink-600" title={me.user.email}>
                {me.user.full_name.split(" ")[0]}
              </span>
              <button type="button" className="btn-ghost btn-sm" onClick={() => logout.mutate()} aria-label="Log out">
                <LogOut className="size-4" aria-hidden="true" />
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn-ghost btn-sm px-4 text-[14px]">
                Log in
              </Link>
              <Link to="/register" className="btn-primary btn-sm px-5 text-[14px]">
                Sign up
              </Link>
            </>
          )}
        </div>
        <button
          type="button"
          className="btn-ghost -mr-2 px-3 lg:hidden"
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X className="size-5" aria-hidden="true" /> : <Menu className="size-5" aria-hidden="true" />}
          <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
        </button>
      </div>
      {open && (
        <div id="mobile-menu" className="animate-fade border-t border-line/70 bg-cream-50 lg:hidden">
          <nav aria-label="Mobile" className="container-page flex flex-col gap-1 py-4">
            {PUBLIC_LINKS.map((link) => (
              <Link
                key={link.label}
                to={link.to}
                aria-current={isActive(link) ? "page" : undefined}
                className={`flex min-h-12 items-center rounded-2xl px-4 text-[15px] font-semibold ${
                  isActive(link) ? "bg-leaf-50 text-leaf-800" : "text-ink-700 hover:bg-cream-200"
                }`}
              >
                {link.label}
              </Link>
            ))}
            {account && (
              <Link to={account.to} className="flex min-h-12 items-center gap-2 rounded-2xl px-4 text-[15px] font-semibold text-ink-700 hover:bg-cream-200">
                <account.icon className="size-4" aria-hidden="true" /> {account.label}
              </Link>
            )}
            <div className="mt-3 flex gap-2 border-t border-line pt-4">
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
          </nav>
        </div>
      )}
    </header>
  );
}

const FOOTER_COLUMNS = [
  {
    title: "Explore",
    links: [
      { to: "/meals", label: "Explore meals" },
      { to: "/#how-it-works", label: "How it works" },
      { to: "/#safety", label: "Food safety" },
      { to: "/register", label: "Create an account" },
    ],
  },
  {
    title: "For providers",
    links: [
      { to: "/register/kitchen", label: "Become a partner" },
      { to: "/#providers", label: "Why list with FoodLoop" },
      { to: "/login", label: "Kitchen login" },
    ],
  },
  {
    title: "Company",
    links: [
      { to: "/#impact", label: "Our mission" },
      { to: "/privacy", label: "Privacy policy" },
      { to: "/terms", label: "Terms of use" },
    ],
  },
];

function Footer() {
  return (
    <footer className="mt-24 bg-leaf-900 text-leaf-100">
      <div className="container-page grid gap-12 py-16 lg:grid-cols-[1.3fr_2fr]">
        <div>
          <Logo tone="light" />
          <p className="font-display mt-5 text-2xl font-semibold text-white">Good food. Less waste.</p>
          <p className="mt-3 max-w-sm text-[15px] leading-relaxed text-leaf-100/85">
            FoodLoop helps approved canteens, cafeterias, hostel messes and PG kitchens sell safe surplus meals to
            people nearby, so good food gets eaten instead of thrown away.
          </p>
          {/* Contact details are placeholders until FoodLoop has an official address. */}
          <a
            href="mailto:hello@foodloop.example"
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-white/8 px-4 py-2 text-sm font-medium text-white ring-1 ring-white/15 transition hover:bg-white/15"
          >
            <Mail className="size-4" aria-hidden="true" /> hello@foodloop.example
          </a>
        </div>
        <div className="grid gap-10 sm:grid-cols-3">
          {FOOTER_COLUMNS.map((column) => (
            <div key={column.title}>
              <h2 className="font-sans text-sm font-bold tracking-wide text-white">{column.title}</h2>
              <ul className="mt-4 space-y-2.5 text-[14.5px]">
                {column.links.map((link) => (
                  <li key={link.label}>
                    <Link className="text-leaf-100/85 transition hover:text-white" to={link.to}>
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <div className="border-t border-white/10">
        <div className="container-page flex flex-col gap-2 py-6 text-[13px] text-leaf-100/70 sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} FoodLoop. Kitchens are responsible for the food they list and must hold valid FSSAI registration.</p>
          <p>Listings marked “Sample data” are fictional demo content.</p>
        </div>
      </div>
    </footer>
  );
}

export function Layout() {
  useHashScroll();
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
