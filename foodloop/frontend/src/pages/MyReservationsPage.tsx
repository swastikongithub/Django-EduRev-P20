import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Clock, Copy, Hourglass, MapPin, Phone, Ticket, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { api, errorMessage } from "../api/client";
import { keys, useMyReservations } from "../api/queries";
import type { CustomerReservation } from "../api/types";
import { MealImage } from "../components/MealImage";
import { useToast } from "../components/Toast";
import { BusyLabel, EmptyState, ErrorState, Notice, PageHeader, SampleBadge, Skeleton, StatusPill, Tabs } from "../components/ui";
import { formatDateTime, formatRupees, formatWindow, minutesUntil, plural, relativeTime } from "../lib/format";
import { useNow } from "../lib/useNow";

function CopyCode({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="btn-ghost btn-sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(code);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function CancelControl({ reservation }: { reservation: CustomerReservation }) {
  const [confirming, setConfirming] = useState(false);
  const queryClient = useQueryClient();
  const toast = useToast();
  const cancel = useMutation({
    mutationFn: () => api(`/reservations/${reservation.id}/cancel`, { method: "POST", body: { reason: "" } }),
    onSuccess: () => {
      toast.success("Reservation cancelled", "Thanks for releasing it. Someone else can now have it.");
      queryClient.invalidateQueries({ queryKey: keys.myReservations });
      queryClient.invalidateQueries({ queryKey: ["listings"] });
    },
  });
  if (!confirming) {
    return (
      <button type="button" className="btn-ghost btn-sm text-fg-soft" onClick={() => setConfirming(true)}>
        <X className="size-4" aria-hidden="true" /> Cancel reservation
      </button>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-raised p-3">
      <p className="mr-auto text-sm text-fg-soft">Cancel and release {plural(reservation.quantity, "portion")} for someone else?</p>
      <button type="button" className="btn-secondary btn-sm" onClick={() => setConfirming(false)}>
        Keep it
      </button>
      <button type="button" className="btn-danger btn-sm" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
        <BusyLabel busy={cancel.isPending} busyText="Cancelling…">
          Yes, cancel
        </BusyLabel>
      </button>
      {cancel.isError && <p className="w-full text-sm text-danger-400">{errorMessage(cancel.error)}</p>}
    </div>
  );
}

function ActiveReservation({ reservation, now }: { reservation: CustomerReservation; now: Date }) {
  const soon = minutesUntil(reservation.pickup_deadline, now) <= 20;
  return (
    <article className="card animate-rise overflow-hidden">
      <div className="grid grid-cols-1 sm:grid-cols-[220px_1fr]">
        <div className="relative aspect-[16/9] bg-raised sm:aspect-auto">
          <MealImage imageUrl={reservation.listing.image_url} mealType={reservation.listing.meal_type} title={reservation.listing.title} seed={reservation.listing.id} alt={reservation.listing.title} sizes="220px" />
          {reservation.provider.is_sample && <SampleBadge className="absolute top-3 left-3" />}
        </div>
        <div className="p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">{reservation.listing.title}</h2>
              <p className="mt-0.5 text-sm text-fg-soft">
                {plural(reservation.quantity, "portion")} · pay {formatRupees(reservation.total_paise)} at the counter
              </p>
            </div>
            <StatusPill status={reservation.display_status} />
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3 rounded-2xl border-2 border-dashed border-brand-700 bg-brand-950 px-4 py-3">
            <Ticket className="size-5 text-brand-400" aria-hidden="true" />
            <div className="mr-auto">
              <p className="text-[12px] font-semibold tracking-wide text-brand-300 uppercase">Pickup code</p>
              <p className="font-mono text-2xl font-bold tracking-[0.25em] text-brand-200">{reservation.pickup_code}</p>
            </div>
            <CopyCode code={reservation.pickup_code} />
          </div>

          <ul className="mt-5 space-y-2.5 text-[14px]">
            <li className="flex gap-2.5">
              <Clock className="mt-0.5 size-4 shrink-0 text-brand-400" aria-hidden="true" />
              <span>
                Pickup {formatWindow(reservation.listing.pickup_start, reservation.listing.pickup_end, now)}{" "}
                <span className={soon ? "font-semibold text-brand-400" : "text-fg-muted"}>
                  (ends {relativeTime(reservation.pickup_deadline, now)})
                </span>
              </span>
            </li>
            <li className="flex gap-2.5">
              <Hourglass className="mt-0.5 size-4 shrink-0 text-brand-400" aria-hidden="true" />
              <span>Eat by {formatDateTime(reservation.listing.safe_until, now)}</span>
            </li>
            <li className="flex gap-2.5">
              <MapPin className="mt-0.5 size-4 shrink-0 text-brand-400" aria-hidden="true" />
              <span>
                <strong>{reservation.provider.name}</strong>, {reservation.provider.address_line}, {reservation.provider.area}
                {reservation.provider.pickup_instructions && (
                  <span className="mt-1 block text-fg-soft">{reservation.provider.pickup_instructions}</span>
                )}
              </span>
            </li>
            <li className="flex gap-2.5">
              <Phone className="mt-0.5 size-4 shrink-0 text-brand-400" aria-hidden="true" />
              <a className="font-medium text-brand-400 underline-offset-4 hover:underline" href={`tel:+91${reservation.provider.contact_phone}`}>
                Call the kitchen
              </a>
            </li>
          </ul>
          {reservation.can_cancel && (
            <div className="mt-5 border-t border-line pt-4">
              <CancelControl reservation={reservation} />
            </div>
          )}
        </div>
      </div>
    </article>
  );
}

function PastReservation({ reservation, now }: { reservation: CustomerReservation; now: Date }) {
  const explanation =
    reservation.display_status === "cancelled"
      ? reservation.cancelled_by === "customer"
        ? "You cancelled this reservation."
        : `Cancelled by ${reservation.cancelled_by === "provider" ? "the kitchen" : "FoodLoop"}${reservation.cancel_reason ? `: ${reservation.cancel_reason}` : "."}`
      : reservation.display_status === "collected"
        ? `Collected ${reservation.collected_at ? formatDateTime(reservation.collected_at, now) : ""}. Enjoy!`
        : "The pickup window ended before this was collected.";
  return (
    <article className="card flex gap-4 p-4 transition hover:shadow-lift">
      <div className="size-16 shrink-0 overflow-hidden rounded-2xl bg-raised">
        <MealImage imageUrl={reservation.listing.image_url} mealType={reservation.listing.meal_type} title={reservation.listing.title} seed={reservation.listing.id} alt="" sizes="64px" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="truncate font-sans text-[15px] font-semibold tracking-normal">{reservation.listing.title}</h3>
          <StatusPill status={reservation.display_status} />
        </div>
        <p className="mt-0.5 text-[13px] text-fg-muted">
          {reservation.provider.name} · {plural(reservation.quantity, "portion")} · {formatRupees(reservation.total_paise)}
        </p>
        <p className="mt-1.5 text-[13.5px] text-fg-soft">{explanation}</p>
      </div>
    </article>
  );
}

export function MyReservationsPage() {
  const { data, isLoading, isError, error, refetch } = useMyReservations();
  const now = useNow();
  const [tab, setTab] = useState<"active" | "past">("active");
  const active = (data ?? []).filter((r) => r.display_status === "reserved");
  const past = (data ?? []).filter((r) => r.display_status !== "reserved");
  const shown = tab === "active" ? active : past;

  return (
    <div>
      <PageHeader
        narrow
        eyebrow="Your meals"
        title="My reservations"
        description="Your pickup codes, times and kitchen addresses, all in one place."
        actions={
          <Link to="/meals" className="btn-secondary">
            Find more meals
          </Link>
        }
      >
        <Tabs
          label="Reservations"
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "active", label: "Upcoming", count: active.length },
            { value: "past", label: "Past" },
          ]}
        />
      </PageHeader>
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <div className="space-y-4">
          {isLoading ? (
            [0, 1].map((key) => <Skeleton key={key} className="h-56 w-full rounded-[1.25rem]" />)
          ) : isError ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : shown.length === 0 ? (
            <div className="card">
              <EmptyState
                icon={<Ticket className="size-7" />}
                title={tab === "active" ? "No upcoming pickups" : "Nothing here yet"}
                action={
                  <Link to="/meals" className="btn-primary">
                    Browse meals
                  </Link>
                }
              >
                {tab === "active" ? "Reserve a meal and your pickup code will appear here." : "Collected and cancelled reservations will show up here."}
              </EmptyState>
            </div>
          ) : tab === "active" ? (
            <>
              <Notice tone="info">Show the pickup code at the counter and pay the kitchen directly (UPI or cash).</Notice>
              {shown.map((reservation) => (
                <ActiveReservation key={reservation.id} reservation={reservation} now={now} />
              ))}
            </>
          ) : (
            shown.map((reservation) => <PastReservation key={reservation.id} reservation={reservation} now={now} />)
          )}
        </div>
      </div>
    </div>
  );
}
