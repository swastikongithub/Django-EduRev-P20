import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Camera, CircleAlert, Flame, Package, ShieldCheck, Snowflake, Thermometer } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { api, ApiError, errorMessage } from "../../api/client";
import { useKitchenListing, useMeta } from "../../api/queries";
import type { Diet, ListingInput, MealType, ProviderListing, Storage } from "../../api/types";
import { MealImage } from "../../components/MealImage";
import { useToast } from "../../components/Toast";
import { BusyLabel, DietMark, describedBy, ErrorState, Field, Notice, PageHeader, PageLoader } from "../../components/ui";
import { addMinutes, formatRupees, fromIstInput, paiseToRupeesInput, rupeesToPaise, toIstInput } from "../../lib/format";
import { ALLERGEN_KEYS } from "../../lib/meals";

const MEAL_TYPES: MealType[] = ["lunch", "dinner", "breakfast", "snacks", "bakery", "beverages"];
const DIETS: Diet[] = ["veg", "vegan", "egg", "non_veg"];
const STORAGE: { value: Storage; icon: typeof Flame }[] = [
  { value: "hot_held", icon: Flame },
  { value: "refrigerated", icon: Snowflake },
  { value: "room_temp", icon: Thermometer },
  { value: "shelf_stable", icon: Package },
];
const CHECKLIST = [
  "This food was prepared today and has been stored the way I've described.",
  "None of it has been served to a customer, returned, or left uncovered.",
  "The veg / non-veg mark and the allergen information are accurate.",
  "It will only be handed over before the eat-by time.",
];

interface FormState {
  title: string;
  description: string;
  meal_type: MealType;
  diet: Diet;
  allergens: string[];
  noAllergens: boolean;
  allergen_note: string;
  original: string;
  price: string;
  quantity_total: string;
  max_per_order: string;
  storage: Storage;
  prepared_at: string;
  pickup_start: string;
  pickup_end: string;
  safe_until: string;
  pickup_instructions: string;
  image_is_representative: boolean;
  checklist: boolean[];
  publish: boolean;
}

function roundedNow(): Date {
  const now = new Date();
  now.setSeconds(0, 0);
  now.setMinutes(Math.floor(now.getMinutes() / 5) * 5);
  return now;
}

function blankForm(): FormState {
  const now = roundedNow();
  return {
    title: "",
    description: "",
    meal_type: "lunch",
    diet: "veg",
    allergens: [],
    noAllergens: false,
    allergen_note: "",
    original: "",
    price: "",
    quantity_total: "10",
    max_per_order: "2",
    storage: "hot_held",
    prepared_at: toIstInput(addMinutes(now, -30)),
    pickup_start: toIstInput(now),
    pickup_end: toIstInput(addMinutes(now, 60)),
    safe_until: toIstInput(addMinutes(now, 90)),
    pickup_instructions: "",
    image_is_representative: false,
    checklist: CHECKLIST.map(() => false),
    publish: true,
  };
}

function fromListing(listing: ProviderListing): FormState {
  return {
    title: listing.title,
    description: listing.description,
    meal_type: listing.meal_type,
    diet: listing.diet,
    allergens: listing.allergens,
    noAllergens: listing.allergens.length === 0,
    allergen_note: listing.allergen_note,
    original: paiseToRupeesInput(listing.original_price_paise),
    price: paiseToRupeesInput(listing.price_paise),
    quantity_total: String(listing.quantity_total),
    max_per_order: String(listing.max_per_order),
    storage: listing.storage,
    prepared_at: toIstInput(listing.prepared_at),
    pickup_start: toIstInput(listing.pickup_start),
    pickup_end: toIstInput(listing.pickup_end),
    safe_until: toIstInput(listing.safe_until),
    pickup_instructions: listing.pickup_instructions,
    image_is_representative: listing.image_is_representative,
    checklist: CHECKLIST.map(() => false), // re-confirm safety on every save
    publish: listing.status === "active",
  };
}

function toPayload(form: FormState): ListingInput {
  return {
    title: form.title,
    description: form.description,
    meal_type: form.meal_type,
    diet: form.diet,
    allergens: form.noAllergens ? [] : form.allergens,
    allergen_note: form.allergen_note,
    original_price_paise: rupeesToPaise(form.original),
    price_paise: rupeesToPaise(form.price),
    quantity_total: Number(form.quantity_total),
    max_per_order: Number(form.max_per_order),
    storage: form.storage,
    prepared_at: fromIstInput(form.prepared_at),
    pickup_start: fromIstInput(form.pickup_start),
    pickup_end: fromIstInput(form.pickup_end),
    safe_until: fromIstInput(form.safe_until),
    pickup_instructions: form.pickup_instructions,
    image_is_representative: form.image_is_representative,
    safety_confirmed: form.checklist.every(Boolean),
  };
}

export function ListingFormPage() {
  const { id } = useParams();
  const editing = Boolean(id);
  const { data: listing, isLoading, isError, error, refetch } = useKitchenListing(id);
  const { data: meta } = useMeta();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState<FormState>(blankForm);
  const [photo, setPhoto] = useState<File | null>(null);
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  const loaded = useRef(false);

  useEffect(() => {
    if (listing && !loaded.current) {
      loaded.current = true;
      setForm(fromListing(listing));
    }
  }, [listing]);

  const preview = useMemo(() => (photo ? URL.createObjectURL(photo) : null), [photo]);
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const save = useMutation({
    mutationFn: async () => {
      const body = toPayload(form);
      const saved = editing
        ? await api<ProviderListing>(`/provider/listings/${id}`, { method: "PUT", body })
        : await api<ProviderListing>("/provider/listings", { method: "POST", body: { ...body, publish: form.publish } });
      if (photo) {
        const data = new FormData();
        data.append("image", photo);
        data.append("is_representative", String(form.image_is_representative));
        try {
          await api(`/provider/listings/${saved.id}/image`, { method: "POST", formData: data });
        } catch (uploadError) {
          return { saved, photoError: uploadError instanceof ApiError ? uploadError.message : "The photo couldn't be uploaded." };
        }
      }
      return { saved, photoError: null as string | null };
    },
    onSuccess: ({ saved, photoError }) => {
      queryClient.invalidateQueries({ queryKey: ["kitchen"] });
      queryClient.invalidateQueries({ queryKey: ["listings"] });
      if (photoError) {
        navigate(`/kitchen/listings/${saved.id}/edit`, { replace: true, state: { photoError } });
        return;
      }
      if (editing) toast.success("Changes saved");
      else if (saved.status === "active") toast.success("Listing published", "Customers nearby can reserve it now.");
      else toast.success("Draft saved", "Publish it from your listings when you're ready.");
      navigate("/kitchen?tab=listings");
    },
    onError: (error) => toast.error("Couldn't save the listing", errorMessage(error)),
  });

  if (editing && isLoading) return <PageLoader />;
  if (editing && (isError || !listing)) return <ErrorState error={error} onRetry={() => refetch()} />;

  const serverErrors = save.error instanceof ApiError ? save.error.fieldErrors : {};
  const errors = { ...serverErrors, ...clientErrors };
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));
  const maxHours = meta?.safety_policy.max_safe_hours[form.storage];
  const original = rupeesToPaise(form.original);
  const price = rupeesToPaise(form.price);
  const discount = original > 0 && price > 0 && price <= original ? Math.round((100 * (original - price)) / original) : null;
  const photoError = (location.state as { photoError?: string } | null)?.photoError;

  function quickWindow(minutes: number) {
    const start = roundedNow();
    const end = addMinutes(start, minutes);
    const prepared = new Date(fromIstInput(form.prepared_at));
    const limit = maxHours ? addMinutes(prepared, maxHours * 60) : addMinutes(end, 30);
    const safe = new Date(Math.min(addMinutes(end, 30).getTime(), limit.getTime()));
    setForm((f) => ({ ...f, pickup_start: toIstInput(start), pickup_end: toIstInput(end), safe_until: toIstInput(safe < end ? end : safe) }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const problems: Record<string, string> = {};
    if (!form.noAllergens && form.allergens.length === 0) problems.allergens = "Choose the allergens in this food, or tick “None of these”.";
    if (!form.checklist.every(Boolean)) problems.safety_confirmed = "Please confirm every item in the safety checklist.";
    setClientErrors(problems);
    if (Object.keys(problems).length === 0) save.mutate();
  }

  return (
    <div>
      <PageHeader
        narrow
        eyebrow={
          <Link to="/kitchen?tab=listings" className="inline-flex items-center gap-1.5 underline-offset-4 hover:underline">
            <ArrowLeft className="size-3.5" aria-hidden="true" /> Back to dashboard
          </Link>
        }
        title={editing ? "Edit listing" : "List surplus food"}
        description="Customers see exactly what you enter here. Be accurate about timing and allergens."
      />
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        {photoError && (
          <Notice tone="warning" className="mb-6" title="Listing saved, but the photo wasn't">
            {photoError}
          </Notice>
        )}

        <form className="space-y-6" onSubmit={submit} noValidate>
          {save.isError && <Notice tone="danger">{save.error.message}</Notice>}

          <section className="card space-y-5 p-6 sm:p-8">
            <h2 className="text-xl font-semibold">The food</h2>
            <Field id="title" label="Meal name" error={errors.title} hint="Specific helps: “Veg thali: dal, aloo gobi, rice, 2 rotis”.">
              <input className="input" required maxLength={80} value={form.title} onChange={(e) => set("title", e.target.value)} {...describedBy("title", errors.title)} />
            </Field>
            <Field id="description" label="Description" optional error={errors.description}>
              <textarea className="input min-h-20 py-3" maxLength={500} value={form.description} onChange={(e) => set("description", e.target.value)} {...describedBy("description", errors.description)} />
            </Field>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field id="meal_type" label="Meal type" error={errors.meal_type}>
                <select className="input" value={form.meal_type} onChange={(e) => set("meal_type", e.target.value as MealType)} {...describedBy("meal_type", errors.meal_type)}>
                  {MEAL_TYPES.map((meal) => (
                    <option key={meal} value={meal}>
                      {meta?.labels.meal_type[meal] ?? meal}
                    </option>
                  ))}
                </select>
              </Field>
              <fieldset>
                <legend className="label">Veg or non-veg</legend>
                <div className="grid grid-cols-2 gap-2">
                  {DIETS.map((diet) => (
                    <label key={diet} className="flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border border-line bg-white px-3 has-[:checked]:border-leaf-600 has-[:checked]:bg-leaf-50">
                      <input type="radio" name="diet" className="sr-only" checked={form.diet === diet} onChange={() => set("diet", diet)} />
                      <DietMark diet={diet} label={meta?.labels.diet[diet] ?? diet} />
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>
          </section>

          <section className="card space-y-5 p-6 sm:p-8">
            <h2 className="text-xl font-semibold">Price &amp; quantity</h2>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field id="original" label="Usual price (₹)" error={errors.original_price_paise}>
                <input className="input" type="number" inputMode="decimal" min={1} step="0.5" required value={form.original} onChange={(e) => set("original", e.target.value)} {...describedBy("original", errors.original_price_paise)} />
              </Field>
              <Field
                id="price"
                label="FoodLoop price (₹)"
                error={errors.price_paise}
                hint={discount !== null ? `${discount}% off: customers save ${formatRupees(original - price)}` : "Lower than the usual price"}
              >
                <input className="input" type="number" inputMode="decimal" min={1} step="0.5" required value={form.price} onChange={(e) => set("price", e.target.value)} {...describedBy("price", errors.price_paise)} />
              </Field>
              <Field id="quantity" label="Portions available" error={errors.quantity_total}>
                <input className="input" type="number" inputMode="numeric" min={1} max={500} required value={form.quantity_total} onChange={(e) => set("quantity_total", e.target.value)} {...describedBy("quantity", errors.quantity_total)} />
              </Field>
              <Field id="max" label="Limit per order" error={errors.max_per_order} hint="Stops one person reserving everything.">
                <input className="input" type="number" inputMode="numeric" min={1} max={10} required value={form.max_per_order} onChange={(e) => set("max_per_order", e.target.value)} {...describedBy("max", errors.max_per_order)} />
              </Field>
            </div>
          </section>

          <section className="card space-y-5 p-6 sm:p-8">
            <div>
              <h2 className="text-xl font-semibold">Timing &amp; storage</h2>
              <p className="mt-1 text-sm text-ink-600">All times are India Standard Time (IST).</p>
            </div>
            <fieldset>
              <legend className="label">How has the food been kept since cooking?</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {STORAGE.map(({ value, icon: Icon }) => (
                  <label key={value} className="flex min-h-12 cursor-pointer items-center gap-3 rounded-xl border border-line bg-white px-3.5 has-[:checked]:border-leaf-600 has-[:checked]:bg-leaf-50">
                    <input type="radio" name="storage" className="sr-only" checked={form.storage === value} onChange={() => set("storage", value)} />
                    <Icon className="size-5 text-leaf-700" aria-hidden="true" />
                    <span className="text-sm font-semibold">{meta?.labels.storage[value] ?? value}</span>
                  </label>
                ))}
              </div>
              {maxHours !== undefined && (
                <p className="hint">FoodLoop safety policy: food {meta?.labels.storage[form.storage].toLowerCase()} must be eaten within {maxHours} hours of preparation.</p>
              )}
            </fieldset>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field id="prepared" label="Prepared at" error={errors.prepared_at}>
                <input className="input" type="datetime-local" required value={form.prepared_at} onChange={(e) => set("prepared_at", e.target.value)} {...describedBy("prepared", errors.prepared_at)} />
              </Field>
              <Field id="safe" label="Eat by" error={errors.safe_until} hint="The latest time this food should be eaten.">
                <input className="input" type="datetime-local" required value={form.safe_until} onChange={(e) => set("safe_until", e.target.value)} {...describedBy("safe", errors.safe_until)} />
              </Field>
              <Field id="start" label="Pickup starts" error={errors.pickup_start}>
                <input className="input" type="datetime-local" required value={form.pickup_start} onChange={(e) => set("pickup_start", e.target.value)} {...describedBy("start", errors.pickup_start)} />
              </Field>
              <Field id="end" label="Pickup ends" error={errors.pickup_end} hint={`Reservations close ${meta?.safety_policy.reservation_cutoff_minutes ?? 10} min before this.`}>
                <input className="input" type="datetime-local" required value={form.pickup_end} onChange={(e) => set("pickup_end", e.target.value)} {...describedBy("end", errors.pickup_end)} />
              </Field>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-ink-600">Quick pickup window from now:</span>
              {[30, 60, 90].map((minutes) => (
                <button key={minutes} type="button" className="chip" onClick={() => quickWindow(minutes)}>
                  {minutes} min
                </button>
              ))}
            </div>
            <Field id="instructions" label="Pickup instructions" optional error={errors.pickup_instructions} hint="Leave empty to use your kitchen's default instructions.">
              <input className="input" maxLength={500} value={form.pickup_instructions} onChange={(e) => set("pickup_instructions", e.target.value)} {...describedBy("instructions", errors.pickup_instructions)} />
            </Field>
          </section>

          <section className="card space-y-5 p-6 sm:p-8">
            <div>
              <h2 className="text-xl font-semibold">Allergens</h2>
              <p className="mt-1 text-sm text-ink-600">Tick everything this food contains. Customers filter and decide based on this.</p>
            </div>
            <fieldset aria-describedby={errors.allergens ? "allergens-error" : undefined}>
              <legend className="sr-only">Allergens present</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {ALLERGEN_KEYS.map((allergen) => (
                  <label key={allergen} className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-line bg-white px-3.5 text-sm has-[:checked]:border-saffron-400 has-[:checked]:bg-saffron-50 ${form.noAllergens ? "opacity-50" : ""}`}>
                    <input
                      type="checkbox"
                      className="size-4 accent-[var(--color-saffron-600)]"
                      disabled={form.noAllergens}
                      checked={form.allergens.includes(allergen)}
                      onChange={(e) =>
                        set("allergens", e.target.checked ? [...form.allergens, allergen] : form.allergens.filter((a) => a !== allergen))
                      }
                    />
                    {meta?.labels.allergen[allergen] ?? allergen}
                  </label>
                ))}
              </div>
              <label className="mt-3 flex min-h-11 cursor-pointer items-center gap-3 rounded-xl border border-dashed border-line px-3.5 text-sm font-semibold has-[:checked]:border-leaf-600 has-[:checked]:bg-leaf-50">
                <input type="checkbox" className="size-4 accent-[var(--color-leaf-600)]" checked={form.noAllergens} onChange={(e) => setForm((f) => ({ ...f, noAllergens: e.target.checked, allergens: e.target.checked ? [] : f.allergens }))} />
                None of these allergens
              </label>
              {errors.allergens && (
                <p id="allergens-error" className="field-error">
                  <CircleAlert className="mt-px size-4 shrink-0" aria-hidden="true" /> {errors.allergens}
                </p>
              )}
            </fieldset>
            <Field id="allergen-note" label="Cross-contamination note" optional error={errors.allergen_note} hint="e.g. “Made in a kitchen that also uses peanuts.”">
              <input className="input" maxLength={200} value={form.allergen_note} onChange={(e) => set("allergen_note", e.target.value)} {...describedBy("allergen-note", errors.allergen_note)} />
            </Field>
          </section>

          <section className="card p-6 sm:p-8">
            <h2 className="text-xl font-semibold">Photo</h2>
            <div className="mt-4 grid gap-5 sm:grid-cols-[200px_1fr] sm:items-center">
              <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-cream-200">
                <MealImage
                  key={preview ?? listing?.image_url ?? "representative"}
                  imageUrl={preview ?? listing?.image_url ?? null}
                  mealType={form.meal_type}
                  title={form.title}
                  alt=""
                  sizes="200px"
                />
                {!preview && !listing?.image_url && (
                  <span className="badge absolute bottom-2 left-2 bg-black/55 text-[11px] text-white backdrop-blur">Representative image</span>
                )}
              </div>
              <div className="space-y-3">
                <label className="btn-secondary cursor-pointer">
                  <Camera className="size-4" aria-hidden="true" /> {photo || listing?.image_url ? "Change photo" : "Add a photo"}
                  <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
                </label>
                <p className="hint !mt-0">JPG, PNG or WebP up to 5 MB. Without one, customers see a stock food photo labelled “Representative image”.</p>
                {errors.image && <p className="field-error">{errors.image}</p>}
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" className="size-4 accent-[var(--color-leaf-600)]" checked={form.image_is_representative} onChange={(e) => set("image_is_representative", e.target.checked)} />
                  This is a representative photo, not today's actual batch
                </label>
              </div>
            </div>
          </section>

          <section className="card overflow-hidden">
            <div className="flex items-center gap-2 bg-leaf-900 px-6 py-4 text-white sm:px-8">
              <ShieldCheck className="size-5 text-turmeric-300" aria-hidden="true" />
              <h2 className="font-sans text-base font-semibold tracking-normal">Food-safety checklist</h2>
            </div>
            <div className="space-y-2 p-6 sm:p-8">
              {CHECKLIST.map((item, index) => (
                <label key={item} className="flex cursor-pointer items-start gap-3 rounded-xl p-2 hover:bg-cream-100">
                  <input
                    type="checkbox"
                    className="mt-0.5 size-5 shrink-0 accent-[var(--color-leaf-600)]"
                    checked={form.checklist[index]}
                    onChange={(e) => set("checklist", form.checklist.map((value, i) => (i === index ? e.target.checked : value)))}
                  />
                  <span className="text-[15px] text-ink-700">{item}</span>
                </label>
              ))}
              {errors.safety_confirmed && (
                <p className="field-error">
                  <CircleAlert className="mt-px size-4 shrink-0" aria-hidden="true" /> {errors.safety_confirmed}
                </p>
              )}
              <p className="pt-2 text-[13px] text-ink-500">Your confirmation is recorded with your name and the time, for every save.</p>
            </div>
          </section>

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
            {!editing ? (
              <label className="flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" className="size-4 accent-[var(--color-leaf-600)]" checked={form.publish} onChange={(e) => set("publish", e.target.checked)} />
                Publish now (untick to save as a draft)
              </label>
            ) : (
              <span />
            )}
            <button className="btn-primary min-h-12 px-8" disabled={save.isPending}>
              <BusyLabel busy={save.isPending} busyText="Saving…">
                {editing ? "Save changes" : form.publish ? "Publish listing" : "Save draft"}
              </BusyLabel>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
