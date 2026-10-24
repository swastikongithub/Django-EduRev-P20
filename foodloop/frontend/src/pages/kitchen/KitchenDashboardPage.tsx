import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChefHat,
  CircleCheck,
  ClipboardCheck,
  Clock,
  IndianRupee,
  Pause,
  Pencil,
  Play,
  Plus,
  Store,
  Ticket,
  Trash2,
  TrendingUp,
  Utensils,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api, ApiError, errorMessage } from "../../api/client";
import { keys, useKitchen, useKitchenListings, useKitchenReservations, useKitchenStats, useMe } from "../../api/queries";
import type { Funnel, Kitchen, KitchenInput, ProviderListing, ProviderReservation } from "../../api/types";
import { KitchenFields } from "../../components/KitchenFields";
import { MealImage } from "../../components/MealImage";
import { useToast } from "../../components/Toast";
import { BusyLabel, EmptyState, ErrorState, Notice, PageHeader, Skeleton, StatTile, StatusPill, Tabs } from "../../components/ui";
import { formatDateTime, formatRupees, formatTime, formatWindow, plural, relativeTime } from "../../lib/format";
import { useNow } from "../../lib/useNow";

type Tab = "pickups" | "listings" | "profile";

function StatusBanner({ kitchen }: { kitchen: Kitchen }) {
  if (kitchen.status === "approved") return null;
  const content = {
    pending: {
      tone: "warning" as const,
      title: "Waiting for approval",
      body: "FoodLoop is checking your FSSAI details. You'll be able to publish listings as soon as your kitchen is approved.",
    },
    rejected: { tone: "danger" as const, title: "Application not approved", body: "Update your details in the Kitchen profile tab and they'll be reviewed again." },
    suspended: { tone: "danger" as const, title: "Kitchen suspended", body: "Your listings are hidden and can't be reserved. Contact FoodLoop to resolve this." },
  }[kitchen.status];
  return (
    <Notice tone={content.tone} title={content.title} className="mb-6">
      {content.body}
      {kitchen.status_reason && <span className="mt-1 block font-medium">Reason: {kitchen.status_reason}</span>}
    </Notice>
  );
}

function Stats() {
  const { data } = useKitchenStats();
  if (!data) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((key) => (
          <Skeleton key={key} className="h-24 rounded-[1.25rem]" />
        ))}
      </div>
    );
  }
  const { today, last_7_days: week } = data;
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatTile label="Waiting for pickup" value={data.open_pickups} sub={`${plural(data.live_listings, "live listing")}`} icon={<Ticket className="size-5" />} tone="saffron" />
      <StatTile
        label="Today: reserved / listed"
        value={`${today.portions_reserved} / ${today.portions_listed}`}
        sub={today.sell_through_percent !== null ? `${today.sell_through_percent}% sell-through` : "No listings today yet"}
        icon={<TrendingUp className="size-5" />}
      />
      <StatTile
        label="Today: collected"
        value={today.portions_collected}
        sub={today.portions_missed ? `${plural(today.portions_missed, "portion")} not collected` : "portions handed over"}
        icon={<CircleCheck className="size-5" />}
      />
      <StatTile
        label="Recovered, last 7 days"
        value={formatRupees(week.revenue_recovered_paise)}
        sub={week.collection_rate_percent !== null ? `${week.collection_rate_percent}% of reservations collected` : "From collected meals"}
        icon={<IndianRupee className="size-5" />}
        tone="ink"
      />
    </div>
  );
}

/** Last 7 days as a funnel: each bar is a share of the portions listed. Real numbers only, never padded. */
function WeekFunnel() {
  const { data } = useKitchenStats();
  if (!data) return <Skeleton className="h-64 w-full rounded-[1.25rem]" />;
  const week: Funnel = data.last_7_days;
  const listed = week.portions_listed;
  const rows = [
    { label: "Listed", value: listed, note: "portions offered" },
    { label: "Reserved", value: week.portions_reserved, note: week.sell_through_percent !== null ? `${week.sell_through_percent}% of listed` : "" },
    { label: "Collected", value: week.portions_collected, note: week.collection_rate_percent !== null ? `${week.collection_rate_percent}% of reserved` : "" },
  ];
  return (
    <section className="card p-5 sm:p-6" aria-labelledby="funnel-title">
      <h2 id="funnel-title" className="font-sans text-base font-semibold tracking-normal">
        Last 7 days
      </h2>
      <p className="mt-0.5 text-[13px] text-ink-500">From portions listed to meals handed over, grouped by pickup day.</p>
      {listed === 0 ? (
        <p className="mt-5 rounded-2xl bg-sage-50 px-4 py-6 text-center text-[14px] text-ink-600">
          No listings in the last 7 days yet. Your numbers will appear here after your first listing.
        </p>
      ) : (
        <>
          <ul className="mt-5 space-y-4">
            {rows.map((row) => {
              const share = Math.round((100 * row.value) / listed);
              return (
                <li key={row.label} className="group relative">
                  <div className="flex items-baseline justify-between gap-3 text-[14px]">
                    <span className="font-semibold text-ink-900">{row.label}</span>
                    <span className="text-ink-600">
                      <span className="font-semibold text-ink-900 tabular-nums">{row.value}</span>
                      {row.note && <span className="ml-1.5 text-[12.5px] text-ink-500">{row.note}</span>}
                    </span>
                  </div>
                  <div
                    className="mt-1.5 h-3 overflow-hidden rounded-full bg-leaf-50"
                    role="img"
                    aria-label={`${row.label}: ${row.value} of ${listed} portions listed (${share}%)`}
                    tabIndex={0}
                  >
                    <div className="h-full rounded-full bg-leaf-500 transition-[width] duration-700" style={{ width: `${Math.max(share, row.value ? 2 : 0)}%` }} />
                  </div>
                  <span
                    className="pointer-events-none absolute -top-9 right-0 z-10 rounded-lg bg-ink-900 px-2.5 py-1 text-[12px] font-medium whitespace-nowrap text-white opacity-0 shadow-lift transition group-focus-within:opacity-100 group-hover:opacity-100"
                    aria-hidden="true"
                  >
                    {row.value} of {listed} listed · {share}%
                  </span>
                </li>
              );
            })}
          </ul>
          <dl className="mt-5 grid grid-cols-3 gap-2 border-t border-line pt-4 text-center">
            <div>
              <dt className="text-[12px] text-ink-500">Cancelled</dt>
              <dd className="font-semibold tabular-nums">{week.portions_cancelled}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-ink-500">Not collected</dt>
              <dd className="font-semibold tabular-nums">{week.portions_missed}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-ink-500">Recovered</dt>
              <dd className="font-semibold tabular-nums">{formatRupees(week.revenue_recovered_paise)}</dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
}

function CollectBox() {
  const [code, setCode] = useState("");
  const queryClient = useQueryClient();
  const toast = useToast();
  const collect = useMutation({
    mutationFn: (pickup_code: string) =>
      api<ProviderReservation>("/provider/reservations/collect", { method: "POST", body: { pickup_code } }),
    onSuccess: (reservation) => {
      setCode("");
      toast.success("Pickup confirmed", `Collect ${formatRupees(reservation.total_paise)} from ${reservation.customer_name}.`);
      queryClient.invalidateQueries({ queryKey: ["kitchen"] });
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (code.trim()) collect.mutate(code.trim());
  }
  return (
    <div className="card overflow-hidden">
      <div className="bg-leaf-900 px-5 py-4 text-white sm:px-6">
        <h2 className="flex items-center gap-2 font-sans text-base font-semibold tracking-normal">
          <ClipboardCheck className="size-5 text-turmeric-300" aria-hidden="true" /> Hand over a meal
        </h2>
        <p className="mt-0.5 text-sm text-white/70">Ask for the customer's pickup code and type it here.</p>
      </div>
      <form className="flex flex-col gap-3 p-5 sm:flex-row sm:p-6" onSubmit={submit}>
        <label className="flex-1">
          <span className="sr-only">Pickup code</span>
          <input
            className="input h-12 text-center font-mono text-xl font-bold tracking-[0.3em] uppercase sm:text-left"
            placeholder="K7Q2MX"
            autoComplete="off"
            autoCapitalize="characters"
            maxLength={8}
            value={code}
            onChange={(event) => setCode(event.target.value.toUpperCase())}
            aria-invalid={collect.isError || undefined}
          />
        </label>
        <button className="btn-primary h-12 px-6" disabled={collect.isPending || !code.trim()}>
          <BusyLabel busy={collect.isPending} busyText="Checking…">
            Confirm pickup
          </BusyLabel>
        </button>
      </form>
      <div aria-live="polite" className="px-5 pb-5 sm:px-6">
        {collect.isSuccess && (
          <Notice tone="success" title={`Handed over to ${collect.data.customer_name}`}>
            {plural(collect.data.quantity, "portion")} of {collect.data.listing.title}. Collect{" "}
            {formatRupees(collect.data.total_paise)}.
          </Notice>
        )}
        {collect.isError && <Notice tone="danger">{errorMessage(collect.error)}</Notice>}
      </div>
    </div>
  );
}

function CancelReservation({ reservation }: { reservation: ProviderReservation }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const queryClient = useQueryClient();
  const toast = useToast();
  const cancel = useMutation({
    mutationFn: () => api(`/provider/reservations/${reservation.id}/cancel`, { method: "POST", body: { reason } }),
    onSuccess: () => {
      toast.success("Reservation cancelled", `${reservation.customer_name} will see your reason.`);
      queryClient.invalidateQueries({ queryKey: ["kitchen"] });
    },
  });
  if (!open) {
    return (
      <button type="button" className="btn-ghost btn-sm text-ink-600" onClick={() => setOpen(true)}>
        Can't hand over?
      </button>
    );
  }
  return (
    <form
      className="mt-3 flex w-full flex-col gap-2 rounded-2xl bg-cream-100 p-3 sm:flex-row"
      onSubmit={(event) => {
        event.preventDefault();
        cancel.mutate();
      }}
    >
      <label className="flex-1">
        <span className="sr-only">Reason for the customer</span>
        <input className="input" required minLength={3} placeholder="Reason, e.g. food spilled" value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <button type="button" className="btn-secondary btn-sm" onClick={() => setOpen(false)}>
        Back
      </button>
      <button className="btn-danger btn-sm" disabled={cancel.isPending}>
        <BusyLabel busy={cancel.isPending} busyText="Cancelling…">
          Cancel reservation
        </BusyLabel>
      </button>
      {cancel.isError && <p className="w-full text-sm text-danger-600">{errorMessage(cancel.error)}</p>}
    </form>
  );
}

function Pickups() {
  const [scope, setScope] = useState<"open" | "all">("open");
  const { data, isLoading, isError, error, refetch } = useKitchenReservations(scope);
  const now = useNow();
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_1.3fr]">
      <div className="space-y-6 lg:sticky lg:top-24 lg:self-start">
        <CollectBox />
        <WeekFunnel />
      </div>
      <section>
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-xl font-semibold">{scope === "open" ? "Waiting for pickup" : "All reservations"}</h2>
          <button type="button" className="btn-ghost btn-sm" onClick={() => setScope(scope === "open" ? "all" : "open")}>
            {scope === "open" ? "Show history" : "Show waiting only"}
          </button>
        </div>
        <div className="mt-4 space-y-3">
          {isLoading ? (
            <Skeleton className="h-28 w-full rounded-[1.25rem]" />
          ) : isError ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : !data?.length ? (
            <div className="card">
              <EmptyState icon={<Ticket className="size-7" />} title={scope === "open" ? "No one is waiting" : "No reservations yet"}>
                New reservations appear here automatically.
              </EmptyState>
            </div>
          ) : (
            data.map((reservation) => (
              <article key={reservation.id} className="card animate-rise p-4 sm:p-5">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold">{reservation.customer_name}</p>
                    <p className="text-sm text-ink-600">
                      {plural(reservation.quantity, "portion")} · {reservation.listing.title}
                    </p>
                  </div>
                  <div className="text-right">
                    <StatusPill status={reservation.display_status} />
                    <p className="mt-1 text-sm font-semibold">{formatRupees(reservation.total_paise)}</p>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[13px] text-ink-500">
                  <span className="flex items-center gap-1.5">
                    <Clock className="size-3.5" aria-hidden="true" />
                    {reservation.display_status === "reserved"
                      ? `Pickup by ${formatTime(reservation.pickup_deadline)} (${relativeTime(reservation.pickup_deadline, now)})`
                      : `Reserved ${formatDateTime(reservation.created_at, now)}`}
                  </span>
                  {reservation.display_status === "reserved" && <CancelReservation reservation={reservation} />}
                </div>
                {reservation.cancel_reason && <p className="mt-2 text-[13px] text-ink-600">Reason: {reservation.cancel_reason}</p>}
              </article>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function ListingRow({ listing, canEdit }: { listing: ProviderListing; canEdit: boolean }) {
  const now = useNow();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [removing, setRemoving] = useState(false);
  const [reason, setReason] = useState("");
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["kitchen"] });
    queryClient.invalidateQueries({ queryKey: ["listings"] });
  };
  const setStatus = useMutation({
    mutationFn: (status: string) => api(`/provider/listings/${listing.id}/status`, { method: "POST", body: { status } }),
    onSuccess: (_data, status) => {
      if (status === "paused") toast.success("Listing paused", "Customers can't reserve it until you publish it again.");
      else toast.success("Listing published", "Customers can reserve it now.");
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => api(`/provider/listings/${listing.id}/remove`, { method: "POST", body: { reason } }),
    onSuccess: () => {
      toast.success("Listing removed");
      refresh();
    },
  });
  const live = listing.status === "active";
  const ended = listing.availability === "expired";
  const error = setStatus.error ?? remove.error;

  return (
    <article className="card min-w-0 p-4 transition hover:shadow-lift sm:p-5">
      <div className="flex gap-4">
        <div className="size-20 shrink-0 overflow-hidden rounded-2xl bg-cream-200 sm:size-24">
          <MealImage imageUrl={listing.image_url} mealType={listing.meal_type} title={listing.title} seed={listing.id} alt="" sizes="96px" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={ended ? "expired" : listing.status} />
            {live && listing.availability !== "available" && !ended && <StatusPill status={listing.availability} />}
          </div>
          <h3 className="mt-1.5 truncate font-sans text-base font-semibold tracking-normal">{listing.title}</h3>
          <p className="mt-0.5 text-[13px] text-ink-500">
            {formatWindow(listing.pickup_start, listing.pickup_end, now)} · {formatRupees(listing.price_paise)}
          </p>
          <p className="mt-1 text-[13px] text-ink-700">
            <strong>{listing.quantity_available}</strong> of {listing.quantity_total} left · {listing.reserved_quantity} waiting ·{" "}
            {listing.collected_quantity} collected
          </p>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-leaf-50" aria-hidden="true">
            <div
              className="h-full rounded-full bg-leaf-500"
              style={{ width: `${listing.quantity_total ? Math.round((100 * (listing.quantity_total - listing.quantity_available)) / listing.quantity_total) : 0}%` }}
            />
          </div>
        </div>
      </div>
      {canEdit && !ended && (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-3">
          <Link to={`/kitchen/listings/${listing.id}/edit`} className="btn-secondary btn-sm">
            <Pencil className="size-3.5" aria-hidden="true" /> Edit
          </Link>
          {listing.status === "active" ? (
            <button type="button" className="btn-secondary btn-sm" disabled={setStatus.isPending} onClick={() => setStatus.mutate("paused")}>
              <Pause className="size-3.5" aria-hidden="true" /> Pause
            </button>
          ) : (
            <button type="button" className="btn-secondary btn-sm" disabled={setStatus.isPending} onClick={() => setStatus.mutate("active")}>
              <Play className="size-3.5" aria-hidden="true" /> Publish
            </button>
          )}
          <button type="button" className="btn-ghost btn-sm ml-auto text-danger-600" onClick={() => setRemoving(true)}>
            <Trash2 className="size-3.5" aria-hidden="true" /> Remove
          </button>
        </div>
      )}
      {removing && (
        <form
          className="mt-3 rounded-2xl bg-danger-50 p-3"
          onSubmit={(event) => {
            event.preventDefault();
            remove.mutate();
          }}
        >
          <p className="text-sm text-ink-700">
            Removing hides this listing for good.
            {listing.reserved_quantity > 0 && ` ${plural(listing.reserved_quantity, "portion")} waiting for pickup will be cancelled and the customers told why.`}
          </p>
          <div className="mt-2 flex flex-col gap-2 sm:flex-row">
            <input className="input" placeholder="Reason (shown to customers)" value={reason} onChange={(e) => setReason(e.target.value)} />
            <button type="button" className="btn-secondary btn-sm" onClick={() => setRemoving(false)}>
              Keep
            </button>
            <button className="btn-danger btn-sm" disabled={remove.isPending}>
              <BusyLabel busy={remove.isPending} busyText="Removing…">
                Remove listing
              </BusyLabel>
            </button>
          </div>
        </form>
      )}
      {error && <p className="mt-2 text-sm text-danger-600">{errorMessage(error)}</p>}
    </article>
  );
}

function Listings({ approved }: { approved: boolean }) {
  const { data, isLoading, isError, error, refetch } = useKitchenListings();
  const current = (data ?? []).filter((l) => l.availability !== "expired");
  const past = (data ?? []).filter((l) => l.availability === "expired");
  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Your listings</h2>
        {!approved && (
          <button type="button" className="btn-primary" disabled title="Available once your kitchen is approved">
            <Plus className="size-4" aria-hidden="true" /> List surplus food
          </button>
        )}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {isLoading ? (
          <Skeleton className="h-32 w-full rounded-[1.25rem]" />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : current.length === 0 ? (
          <div className="card lg:col-span-2">
            <EmptyState icon={<Utensils className="size-7" />} title="Nothing listed right now">
              {approved
                ? "Had food left after service? List it in under a minute, before it's no longer safe to sell."
                : "Once approved, you'll list surplus here."}
            </EmptyState>
          </div>
        ) : (
          current.map((listing) => <ListingRow key={listing.id} listing={listing} canEdit={approved} />)
        )}
      </div>
      {past.length > 0 && (
        <details className="mt-8">
          <summary className="cursor-pointer text-sm font-semibold text-ink-600">Ended listings ({past.length})</summary>
          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
            {past.map((listing) => (
              <ListingRow key={listing.id} listing={listing} canEdit={false} />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function Profile({ kitchen }: { kitchen: Kitchen }) {
  const queryClient = useQueryClient();
  const toInput = (k: Kitchen): KitchenInput => ({
    name: k.name,
    kind: k.kind,
    description: k.description,
    address_line: k.address_line,
    area: k.area,
    city: k.city,
    pincode: k.pincode,
    contact_phone: k.contact_phone,
    fssai_number: k.fssai_number,
    fssai_kind: k.fssai_kind,
    fssai_valid_until: k.fssai_valid_until,
    pickup_instructions: k.pickup_instructions,
  });
  const toast = useToast();
  const [form, setForm] = useState<KitchenInput>(toInput(kitchen));
  useEffect(() => setForm(toInput(kitchen)), [kitchen]);
  const save = useMutation({
    mutationFn: () => api<Kitchen>("/provider/me", { method: "PUT", body: form }),
    onSuccess: (updated) => {
      toast.success("Kitchen profile saved", updated.status === "pending" ? "Your kitchen will be re-checked before listings go live again." : undefined);
      queryClient.setQueryData(keys.kitchen, updated);
      queryClient.invalidateQueries({ queryKey: keys.me });
    },
  });
  const errors = save.error instanceof ApiError ? save.error.fieldErrors : {};
  return (
    <form
      className="card max-w-3xl p-6 sm:p-8"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <h2 className="text-xl font-semibold">Kitchen profile</h2>
      {kitchen.status === "approved" && (
        <Notice tone="warning" className="mt-4">
          Changing the name, address or FSSAI details sends your kitchen back for a quick re-check. Your listings are
          hidden until it's approved again.
        </Notice>
      )}
      <div className="mt-6">
        <KitchenFields value={form} onChange={setForm} errors={errors} />
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button className="btn-primary" disabled={save.isPending}>
          <BusyLabel busy={save.isPending} busyText="Saving…">
            Save changes
          </BusyLabel>
        </button>
        {save.isSuccess && <span className="text-sm font-medium text-leaf-700">Saved.</span>}
        {save.isError && !Object.keys(errors).length && <span className="text-sm text-danger-600">{errorMessage(save.error)}</span>}
      </div>
    </form>
  );
}

export function KitchenDashboardPage() {
  const { data: me } = useMe();
  const { data: kitchen, isLoading, isError, error, refetch } = useKitchen();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "pickups";
  const { data: stats } = useKitchenStats();

  if (isLoading) {
    return (
      <div className="container-page py-12">
        <Skeleton className="h-40 w-full rounded-[2rem]" />
      </div>
    );
  }
  if (isError || !kitchen) return <ErrorState error={error} onRetry={() => refetch()} />;
  const approved = kitchen.status === "approved";

  return (
    <div>
      <PageHeader
        eyebrow={
          <span className="flex items-center gap-2">
            <ChefHat className="size-4" aria-hidden="true" /> Kitchen dashboard
          </span>
        }
        title={
          <span className="flex flex-wrap items-center gap-3">
            {kitchen.name} <StatusPill status={kitchen.status} />
          </span>
        }
        description={
          <span className="flex items-center gap-1.5">
            <Store className="size-4 text-leaf-600" aria-hidden="true" /> {kitchen.area}, {kitchen.city} · signed in as {me?.user.full_name}
          </span>
        }
        actions={
          approved ? (
            <Link to="/kitchen/listings/new" className="btn-primary">
              <Plus className="size-4" aria-hidden="true" /> List surplus food
            </Link>
          ) : undefined
        }
      >
        <div className="overflow-x-auto pb-1">
          <Tabs<Tab>
            label="Kitchen sections"
            value={tab}
            onChange={(value) => setParams({ tab: value }, { replace: true })}
            tabs={[
              { value: "pickups", label: "Pickups", count: stats?.open_pickups },
              { value: "listings", label: "Listings" },
              { value: "profile", label: "Kitchen profile" },
            ]}
          />
        </div>
      </PageHeader>
      <div className="container-page py-8">
        <StatusBanner kitchen={kitchen} />
        <Stats />
        <div className="mt-8">
          {tab === "pickups" && <Pickups />}
          {tab === "listings" && <Listings approved={approved} />}
          {tab === "profile" && <Profile kitchen={kitchen} />}
        </div>
      </div>
    </div>
  );
}
