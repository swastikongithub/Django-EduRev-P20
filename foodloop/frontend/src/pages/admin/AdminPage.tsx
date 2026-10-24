import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Ban, ExternalLink, History, ShieldCheck, Store, Ticket, Users, Utensils, X } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api, errorMessage } from "../../api/client";
import { useAdminKitchens, useAdminListings, useAdminOverview, useMeta } from "../../api/queries";
import type { AdminKitchen, AuditEntry, ProviderListing } from "../../api/types";
import { MealImage } from "../../components/MealImage";
import { useToast } from "../../components/Toast";
import { BusyLabel, EmptyState, ErrorState, Notice, PageHeader, SampleBadge, Skeleton, StatTile, StatusPill, Tabs } from "../../components/ui";
import { formatDateTime, formatRupees, formatWindow } from "../../lib/format";

type Tab = "kitchens" | "listings" | "activity";

function ReasonForm({ label, onSubmit, onCancel, pending }: { label: string; onSubmit: (reason: string) => void; onCancel: () => void; pending: boolean }) {
  const [reason, setReason] = useState("");
  return (
    <form
      className="mt-3 flex flex-col gap-2 rounded-2xl bg-cream-100 p-3 sm:flex-row"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(reason);
      }}
    >
      <label className="flex-1">
        <span className="sr-only">Reason</span>
        <input className="input" required minLength={3} maxLength={500} placeholder="Reason (shared with the kitchen)" value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <button type="button" className="btn-secondary btn-sm" onClick={onCancel}>
        Back
      </button>
      <button className="btn-danger btn-sm" disabled={pending}>
        <BusyLabel busy={pending} busyText="Saving…">
          {label}
        </BusyLabel>
      </button>
    </form>
  );
}

function KitchenCard({ kitchen }: { kitchen: AdminKitchen }) {
  const { data: meta } = useMeta();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [action, setAction] = useState<"reject" | "suspend" | null>(null);
  const mutate = useMutation({
    mutationFn: ({ verb, reason }: { verb: string; reason?: string }) =>
      api(`/admin/providers/${kitchen.id}/${verb}`, { method: "POST", body: reason ? { reason } : undefined }),
    onSuccess: (_data, { verb }) => {
      setAction(null);
      const done: Record<string, string> = { approve: "Kitchen approved", reject: "Application rejected", suspend: "Kitchen suspended" };
      toast.success(done[verb] ?? "Saved", kitchen.name);
      queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (error) => toast.error("That didn't work", errorMessage(error)),
  });
  return (
    <article className="card animate-rise p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-sans text-base font-semibold tracking-normal">{kitchen.name}</h3>
            <StatusPill status={kitchen.status} />
            {kitchen.is_sample && <SampleBadge />}
          </div>
          <p className="mt-1 text-sm text-ink-600">
            {meta?.labels.provider_kind[kitchen.kind]} · {kitchen.address_line}, {kitchen.area}, {kitchen.city} {kitchen.pincode}
          </p>
          <p className="mt-1 text-sm text-ink-600">
            {kitchen.owner_name} · {kitchen.owner_email} · {kitchen.contact_phone}
          </p>
        </div>
        <p className="text-right text-[13px] text-ink-500">
          Applied {formatDateTime(kitchen.created_at)}
          <br />
          {kitchen.active_listings} live listing{kitchen.active_listings === 1 ? "" : "s"}
        </p>
      </div>
      <div className={`mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl px-3.5 py-2.5 text-sm ${kitchen.fssai_expired ? "bg-danger-50 text-danger-600" : "bg-cream-100 text-ink-700"}`}>
        <span>
          {meta?.labels.fssai_kind[kitchen.fssai_kind]}: <span className="font-mono font-semibold">{kitchen.fssai_number}</span>
        </span>
        <span>Valid until {kitchen.fssai_valid_until}{kitchen.fssai_expired && " (EXPIRED)"}</span>
        <a className="inline-flex items-center gap-1 font-semibold text-leaf-700 underline-offset-4 hover:underline" href="https://foscos.fssai.gov.in/" target="_blank" rel="noreferrer noopener">
          Verify on FoSCoS <ExternalLink className="size-3.5" aria-hidden="true" />
        </a>
      </div>
      {kitchen.status_reason && <p className="mt-2 text-sm text-ink-600">Note: {kitchen.status_reason}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        {kitchen.status !== "approved" && (
          <button type="button" className="btn-primary btn-sm" disabled={mutate.isPending || kitchen.fssai_expired} onClick={() => mutate.mutate({ verb: "approve" })}>
            <BusyLabel busy={mutate.isPending && mutate.variables?.verb === "approve"} busyText="Approving…">
              <BadgeCheck className="size-4" aria-hidden="true" /> {kitchen.status === "pending" ? "Approve" : "Re-approve"}
            </BusyLabel>
          </button>
        )}
        {kitchen.status === "pending" && (
          <button type="button" className="btn-secondary btn-sm" onClick={() => setAction("reject")}>
            <X className="size-4" aria-hidden="true" /> Reject
          </button>
        )}
        {kitchen.status === "approved" && (
          <button type="button" className="btn-danger btn-sm" onClick={() => setAction("suspend")}>
            <Ban className="size-4" aria-hidden="true" /> Suspend
          </button>
        )}
      </div>
      {action && (
        <ReasonForm
          label={action === "reject" ? "Reject kitchen" : "Suspend now"}
          pending={mutate.isPending}
          onCancel={() => setAction(null)}
          onSubmit={(reason) => mutate.mutate({ verb: action, reason })}
        />
      )}
      {action === "suspend" && <p className="mt-2 text-[13px] text-ink-500">Suspending hides all its listings and cancels open reservations immediately.</p>}
      {mutate.isError && <p className="mt-2 text-sm text-danger-600">{errorMessage(mutate.error)}</p>}
    </article>
  );
}

function Kitchens() {
  const [status, setStatus] = useState("pending");
  const { data, isLoading, isError, error, refetch } = useAdminKitchens(status);
  return (
    <section>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter kitchens">
        {[
          ["pending", "Awaiting approval"],
          ["approved", "Approved"],
          ["suspended", "Suspended"],
          ["rejected", "Rejected"],
          ["", "All"],
        ].map(([value, label]) => (
          <button key={value} type="button" className="chip" aria-pressed={status === value} onClick={() => setStatus(value)}>
            {label}
          </button>
        ))}
      </div>
      <div className="mt-4 space-y-3">
        {isLoading ? (
          <Skeleton className="h-40 w-full rounded-[1.25rem]" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !data?.length ? (
          <div className="card">
            <EmptyState icon={<Store className="size-7" />} title={status === "pending" ? "No kitchens waiting" : "No kitchens here"}>
              {status === "pending" ? "New kitchen applications will appear here for review." : "Try another filter."}
            </EmptyState>
          </div>
        ) : (
          data.map((kitchen) => <KitchenCard key={kitchen.id} kitchen={kitchen} />)
        )}
      </div>
    </section>
  );
}

function AdminListingRow({ listing }: { listing: ProviderListing }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [removing, setRemoving] = useState(false);
  const remove = useMutation({
    mutationFn: (reason: string) => api(`/admin/listings/${listing.id}/remove`, { method: "POST", body: { reason } }),
    onSuccess: () => {
      setRemoving(false);
      toast.success("Listing removed", "The kitchen and any customers with reservations can see your reason.");
      queryClient.invalidateQueries({ queryKey: ["admin"] });
      queryClient.invalidateQueries({ queryKey: ["listings"] });
    },
  });
  return (
    <article className="card p-4 transition hover:shadow-lift">
      <div className="flex gap-4">
        <div className="size-16 shrink-0 overflow-hidden rounded-2xl bg-cream-200">
          <MealImage imageUrl={listing.image_url} mealType={listing.meal_type} title={listing.title} seed={listing.id} alt="" sizes="64px" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={listing.availability === "expired" ? "expired" : listing.status} />
            {listing.provider.is_sample && <SampleBadge />}
          </div>
          <h3 className="mt-1 truncate font-sans text-[15px] font-semibold tracking-normal">{listing.title}</h3>
          <p className="text-[13px] text-ink-500">
            {listing.provider.name} · {formatRupees(listing.price_paise)} · {formatWindow(listing.pickup_start, listing.pickup_end)} ·{" "}
            {listing.quantity_available}/{listing.quantity_total} left
          </p>
          {listing.removed_reason && <p className="mt-1 text-[13px] text-danger-600">Removed: {listing.removed_reason}</p>}
        </div>
        {listing.status !== "removed" && !removing && (
          <button type="button" className="btn-danger btn-sm self-start" onClick={() => setRemoving(true)}>
            Remove
          </button>
        )}
      </div>
      {removing && <ReasonForm label="Remove listing" pending={remove.isPending} onCancel={() => setRemoving(false)} onSubmit={(reason) => remove.mutate(reason)} />}
      {remove.isError && <p className="mt-2 text-sm text-danger-600">{errorMessage(remove.error)}</p>}
    </article>
  );
}

function Listings() {
  const [status, setStatus] = useState("live");
  const [q, setQ] = useState("");
  const { data, isLoading, isError, error, refetch } = useAdminListings(status, q);
  return (
    <section>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter listings">
          {[
            ["live", "Live now"],
            ["paused", "Paused"],
            ["removed", "Removed"],
            ["", "All"],
          ].map(([value, label]) => (
            <button key={value} type="button" className="chip" aria-pressed={status === value} onClick={() => setStatus(value)}>
              {label}
            </button>
          ))}
        </div>
        <label className="sm:ml-auto sm:w-72">
          <span className="sr-only">Search listings</span>
          <input className="input" type="search" placeholder="Search meal or kitchen" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>
      <div className="mt-4 space-y-3">
        {isLoading ? (
          <Skeleton className="h-24 w-full rounded-[1.25rem]" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : !data?.items.length ? (
          <div className="card">
            <EmptyState icon={<Utensils className="size-7" />} title="No listings here" />
          </div>
        ) : (
          data.items.map((listing) => <AdminListingRow key={listing.id} listing={listing} />)
        )}
      </div>
    </section>
  );
}

const ACTION_LABELS: Record<string, string> = {
  "provider.registered": "Kitchen registered",
  "provider.approved": "Kitchen approved",
  "provider.rejected": "Kitchen rejected",
  "provider.suspended": "Kitchen suspended",
  "provider.resubmitted": "Kitchen details changed, back to review",
  "listing.created": "Listing created",
  "listing.updated": "Listing edited",
  "listing.active": "Listing published",
  "listing.paused": "Listing paused",
  "listing.draft": "Listing moved to draft",
  "listing.removed": "Listing removed",
  "reservation.cancelled_by_provider": "Kitchen cancelled a reservation",
};

function Activity({ entries }: { entries: AuditEntry[] }) {
  if (!entries.length) {
    return (
      <div className="card">
        <EmptyState icon={<History className="size-7" />} title="No activity yet" />
      </div>
    );
  }
  return (
    <ol className="card divide-y divide-line">
      {entries.map((entry) => (
        <li key={entry.id} className="flex flex-wrap items-baseline justify-between gap-2 px-5 py-3.5">
          <div className="relative pl-5">
            <span
              className={`absolute top-1.5 left-0 size-2.5 rounded-full ${/removed|suspended|rejected|cancelled/.test(entry.action) ? "bg-saffron-500" : "bg-leaf-500"}`}
              aria-hidden="true"
            />
            <p className="text-[14.5px] font-semibold">{ACTION_LABELS[entry.action] ?? entry.action}</p>
            <p className="text-[13px] text-ink-500">
              by {entry.actor_name ?? "system"}
              {typeof entry.details.reason === "string" && ` · “${entry.details.reason}”`}
              {typeof entry.details.title === "string" && ` · ${entry.details.title}`}
            </p>
          </div>
          <time className="text-[13px] text-ink-500" dateTime={entry.created_at}>
            {formatDateTime(entry.created_at)}
          </time>
        </li>
      ))}
    </ol>
  );
}

export function AdminPage() {
  const { data, isLoading, isError, error, refetch } = useAdminOverview();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "kitchens";

  return (
    <div>
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-2">
            <ShieldCheck className="size-4" aria-hidden="true" /> FoodLoop admin
          </span>
        }
        title="Platform overview"
        description="Approve kitchens, keep listings honest, and watch over safety."
        actions={
          <Link to="/meals" className="btn-secondary">
            View public site
          </Link>
        }
      >
        <div className="overflow-x-auto pb-1">
          <Tabs<Tab>
            label="Admin sections"
            value={tab}
            onChange={(value) => setParams({ tab: value }, { replace: true })}
            tabs={[
              { value: "kitchens", label: "Kitchens", count: data?.providers.pending },
              { value: "listings", label: "Listings" },
              { value: "activity", label: "Activity log" },
            ]}
          />
        </div>
      </PageHeader>
      <div className="container-page py-8">
        {isLoading ? (
          <Skeleton className="h-24 w-full rounded-[1.25rem]" />
        ) : isError || !data ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : (
          <>
            {data.providers.pending > 0 && (
              <Notice tone="warning" className="mb-6" title={`${data.providers.pending} kitchen${data.providers.pending === 1 ? "" : "s"} waiting for approval`}>
                Check each FSSAI number on FoSCoS before approving.
              </Notice>
            )}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatTile label="Approved kitchens" value={data.providers.approved} sub={`${data.providers.pending} pending · ${data.providers.suspended} suspended`} icon={<Store className="size-5" />} />
              <StatTile label="Live listings" value={data.live_listings} sub="Reservable right now" icon={<Utensils className="size-5" />} />
              <StatTile
                label="Portions reserved today"
                value={data.portions_reserved_today.reserved + data.portions_reserved_today.collected + data.portions_reserved_today.no_show}
                sub={`${data.portions_reserved_today.collected} collected · ${data.portions_reserved_today.cancelled} cancelled`}
                icon={<Ticket className="size-5" />}
                tone="saffron"
              />
              <StatTile label="Customers" value={data.customers} sub={`${data.portions_collected_all_time} portions collected all-time`} icon={<Users className="size-5" />} tone="ink" />
            </div>
          </>
        )}
        <div className="mt-8">
          {tab === "kitchens" && <Kitchens />}
          {tab === "listings" && <Listings />}
          {tab === "activity" && <Activity entries={data?.recent_activity ?? []} />}
        </div>
      </div>
    </div>
  );
}
