// Data-fetching hooks. TanStack Query gives every screen loading, error and refresh states for free.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, toQuery } from "./client";
import type {
  AdminKitchen,
  AdminOverview,
  CustomerReservation,
  Kitchen,
  Listing,
  Me,
  Meta,
  Page,
  ProviderListing,
  ProviderReservation,
  ProviderStats,
} from "./types";

export const keys = {
  me: ["me"] as const,
  meta: ["meta"] as const,
  listings: (params: object) => ["listings", params] as const,
  listing: (id: string) => ["listing", id] as const,
  myReservations: ["my-reservations"] as const,
  kitchen: ["kitchen"] as const,
  kitchenListings: ["kitchen", "listings"] as const,
  kitchenListing: (id: string) => ["kitchen", "listings", id] as const,
  kitchenReservations: (scope: string) => ["kitchen", "reservations", scope] as const,
  kitchenStats: ["kitchen", "stats"] as const,
  admin: ["admin"] as const,
};

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => api<Me | null>("/auth/me"), staleTime: 60_000 });
}

export function useMeta() {
  return useQuery({ queryKey: keys.meta, queryFn: () => api<Meta>("/meta"), staleTime: Infinity });
}

export interface BrowseParams {
  q?: string;
  meal_type?: string[];
  diet?: string[];
  exclude_allergen?: string[];
  max_price_paise?: number;
  availability?: string;
  sort?: string;
  limit?: number;
}

export function useListings(params: BrowseParams) {
  return useQuery({
    queryKey: keys.listings(params),
    queryFn: ({ signal }) => api<Page<Listing>>(`/listings${toQuery({ ...params })}`, { signal }),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000, // quantities and countdowns stay fresh
  });
}

export function useListing(id: string) {
  return useQuery({
    queryKey: keys.listing(id),
    queryFn: () => api<Listing>(`/listings/${id}`),
    refetchInterval: 30_000,
  });
}

export function useMyReservations(enabled = true) {
  return useQuery({
    queryKey: keys.myReservations,
    queryFn: () => api<CustomerReservation[]>("/reservations/mine"),
    enabled,
    refetchInterval: 60_000,
  });
}

export function useKitchen() {
  return useQuery({ queryKey: keys.kitchen, queryFn: () => api<Kitchen>("/provider/me") });
}

export function useKitchenListings() {
  return useQuery({
    queryKey: keys.kitchenListings,
    queryFn: () => api<ProviderListing[]>("/provider/listings"),
    refetchInterval: 60_000,
  });
}

export function useKitchenListing(id: string | undefined) {
  return useQuery({
    queryKey: keys.kitchenListing(id ?? "new"),
    queryFn: () => api<ProviderListing>(`/provider/listings/${id}`),
    enabled: Boolean(id),
  });
}

export function useKitchenReservations(scope: "open" | "all") {
  return useQuery({
    queryKey: keys.kitchenReservations(scope),
    queryFn: () => api<ProviderReservation[]>(`/provider/reservations?scope=${scope}`),
    refetchInterval: 30_000, // new reservations appear without reloading
  });
}

export function useKitchenStats() {
  return useQuery({
    queryKey: keys.kitchenStats,
    queryFn: () => api<ProviderStats>("/provider/stats"),
    refetchInterval: 60_000,
  });
}

export function useAdminOverview() {
  return useQuery({ queryKey: [...keys.admin, "overview"], queryFn: () => api<AdminOverview>("/admin/overview") });
}

export function useAdminKitchens(status: string) {
  return useQuery({
    queryKey: [...keys.admin, "kitchens", status],
    queryFn: () => api<AdminKitchen[]>(`/admin/providers${toQuery({ status })}`),
  });
}

export function useAdminListings(status: string, q: string) {
  return useQuery({
    queryKey: [...keys.admin, "listings", status, q],
    queryFn: () => api<Page<ProviderListing>>(`/admin/listings${toQuery({ status, q, limit: 100 })}`),
    placeholderData: keepPreviousData,
  });
}
