// Kitchen details form section, shared by "Register your kitchen" and the kitchen profile page.

import { useMeta } from "../api/queries";
import type { FssaiKind, KitchenInput, ProviderKind } from "../api/types";
import { describedBy, Field } from "./ui";

export const EMPTY_KITCHEN: KitchenInput = {
  name: "",
  kind: "college_canteen",
  description: "",
  address_line: "",
  area: "",
  city: "",
  pincode: "",
  contact_phone: "",
  fssai_number: "",
  fssai_kind: "registration",
  fssai_valid_until: "",
  pickup_instructions: "",
};

const KINDS: ProviderKind[] = ["college_canteen", "cafeteria", "hostel_mess", "pg_kitchen", "other"];
const FSSAI_KINDS: FssaiKind[] = ["registration", "state_licence", "central_licence"];

export function KitchenFields({
  value,
  onChange,
  errors,
  prefix = "",
}: {
  value: KitchenInput;
  onChange: (value: KitchenInput) => void;
  errors: Record<string, string>;
  /** Server field names may be nested, e.g. "kitchen.fssai_number". */
  prefix?: string;
}) {
  const { data: meta } = useMeta();
  const set = <K extends keyof KitchenInput>(key: K, next: KitchenInput[K]) => onChange({ ...value, [key]: next });
  const err = (key: keyof KitchenInput) => errors[`${prefix}${key}`];

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Field id="k-name" label="Kitchen name" error={err("name")} hint="As customers know it, e.g. “Block 32 Canteen”.">
          <input className="input" required maxLength={120} value={value.name} onChange={(e) => set("name", e.target.value)} {...describedBy("k-name", err("name"))} />
        </Field>
      </div>
      <Field id="k-kind" label="Type of kitchen" error={err("kind")}>
        <select className="input" value={value.kind} onChange={(e) => set("kind", e.target.value as ProviderKind)} {...describedBy("k-kind", err("kind"))}>
          {KINDS.map((kind) => (
            <option key={kind} value={kind}>
              {meta?.labels.provider_kind[kind] ?? kind}
            </option>
          ))}
        </select>
      </Field>
      <Field id="k-phone" label="Kitchen phone" error={err("contact_phone")} hint="10-digit mobile number. Shown to customers with a reservation.">
        <input className="input" type="tel" inputMode="numeric" required value={value.contact_phone} onChange={(e) => set("contact_phone", e.target.value)} {...describedBy("k-phone", err("contact_phone"))} />
      </Field>
      <div className="sm:col-span-2">
        <Field id="k-address" label="Address" error={err("address_line")}>
          <input className="input" required maxLength={200} placeholder="Building, floor, landmark" value={value.address_line} onChange={(e) => set("address_line", e.target.value)} {...describedBy("k-address", err("address_line"))} />
        </Field>
      </div>
      <Field id="k-area" label="Area or campus" error={err("area")}>
        <input className="input" required maxLength={100} value={value.area} onChange={(e) => set("area", e.target.value)} {...describedBy("k-area", err("area"))} />
      </Field>
      <div className="grid grid-cols-[1fr_8rem] gap-3">
        <Field id="k-city" label="City" error={err("city")}>
          <input className="input" required maxLength={100} value={value.city} onChange={(e) => set("city", e.target.value)} {...describedBy("k-city", err("city"))} />
        </Field>
        <Field id="k-pincode" label="PIN code" error={err("pincode")}>
          <input className="input" required inputMode="numeric" maxLength={6} pattern="[1-9][0-9]{5}" value={value.pincode} onChange={(e) => set("pincode", e.target.value)} {...describedBy("k-pincode", err("pincode"))} />
        </Field>
      </div>

      <div className="rounded-2xl border border-leaf-200 bg-leaf-50/60 p-4 sm:col-span-2 sm:p-5">
        <p className="text-sm font-semibold text-leaf-900">FSSAI registration</p>
        <p className="mt-1 text-[13px] text-leaf-900/80">
          FoodLoop checks this on the FSSAI FoSCoS portal before approving your kitchen. It's shown on your listings.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Field id="k-fssai" label="Licence / registration no." error={err("fssai_number")} hint="14 digits">
            <input className="input font-mono" required inputMode="numeric" maxLength={17} value={value.fssai_number} onChange={(e) => set("fssai_number", e.target.value)} {...describedBy("k-fssai", err("fssai_number"))} />
          </Field>
          <Field id="k-fssai-kind" label="Type" error={err("fssai_kind")}>
            <select className="input" value={value.fssai_kind} onChange={(e) => set("fssai_kind", e.target.value as FssaiKind)} {...describedBy("k-fssai-kind", err("fssai_kind"))}>
              {FSSAI_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {meta?.labels.fssai_kind[kind] ?? kind}
                </option>
              ))}
            </select>
          </Field>
          <Field id="k-fssai-valid" label="Valid until" error={err("fssai_valid_until")}>
            <input className="input" type="date" required value={value.fssai_valid_until} onChange={(e) => set("fssai_valid_until", e.target.value)} {...describedBy("k-fssai-valid", err("fssai_valid_until"))} />
          </Field>
        </div>
      </div>

      <div className="sm:col-span-2">
        <Field id="k-pickup" label="Default pickup instructions" optional error={err("pickup_instructions")} hint="Where customers collect food and what to say, e.g. “Side counter by the billing desk. Show your code.”">
          <textarea className="input min-h-24 py-3" maxLength={500} value={value.pickup_instructions} onChange={(e) => set("pickup_instructions", e.target.value)} {...describedBy("k-pickup", err("pickup_instructions"))} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field id="k-desc" label="About your kitchen" optional error={err("description")}>
          <textarea className="input min-h-20 py-3" maxLength={500} value={value.description} onChange={(e) => set("description", e.target.value)} {...describedBy("k-desc", err("description"))} />
        </Field>
      </div>
    </div>
  );
}
