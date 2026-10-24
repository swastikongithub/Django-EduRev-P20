import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ChefHat, Eye, EyeOff, ShieldCheck, Store } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";

import { api, ApiError } from "../api/client";
import { keys, useMe } from "../api/queries";
import type { KitchenInput, Me, Role } from "../api/types";
import { EMPTY_KITCHEN, KitchenFields } from "../components/KitchenFields";
import { Photo } from "../components/Photo";
import { BusyLabel, describedBy, Field, Notice } from "../components/ui";
import { type Photo as PhotoItem, PHOTOS } from "../lib/photos";

const HOME: Record<Role, string> = { customer: "/meals", provider: "/kitchen", admin: "/admin" };

/** Only follow ?next= to pages on this site, never to another website. */
function safeNext(next: string | null): string | null {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

function AuthShell({
  title,
  subtitle,
  children,
  photo = PHOTOS.idliVada,
  caption,
}: {
  title: string;
  subtitle: ReactNode;
  children: ReactNode;
  photo?: PhotoItem;
  caption: string;
}) {
  return (
    <div className="mx-auto grid max-w-6xl items-stretch gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[1fr_0.95fr] lg:py-14">
      <div className="card animate-rise self-start p-6 sm:p-10">
        <h1 className="text-[2rem] leading-tight sm:text-4xl">{title}</h1>
        <p className="mt-2 text-[15px] text-ink-600">{subtitle}</p>
        <div className="mt-8">{children}</div>
      </div>
      <div className="relative hidden min-h-[560px] overflow-hidden rounded-[2rem] shadow-lift lg:block" aria-hidden="true">
        <Photo photo={photo} alt="" sizes="(min-width: 1024px) 520px, 0px" priority />
        <div className="absolute inset-0 bg-gradient-to-t from-leaf-900/85 via-leaf-900/15 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 p-8 text-white">
          <p className="font-display text-[1.9rem] leading-tight font-semibold">{caption}</p>
          <p className="mt-3 flex items-center gap-2 text-[14px] text-white/85">
            <ShieldCheck className="size-4" /> Only FSSAI-checked kitchens. Nothing past its safe-until time.
          </p>
        </div>
      </div>
    </div>
  );
}

function PasswordInput({ id, value, onChange, error, autoComplete }: { id: string; value: string; onChange: (value: string) => void; error?: string; autoComplete: string }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input
        className="input pr-12"
        type={visible ? "text" : "password"}
        required
        minLength={autoComplete === "new-password" ? 8 : 1}
        maxLength={128}
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        {...describedBy(id, error)}
      />
      <button
        type="button"
        className="absolute top-1/2 right-1.5 grid size-9 -translate-y-1/2 place-items-center rounded-full text-ink-500 hover:bg-cream-200"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Hide password" : "Show password"}
      >
        {visible ? <EyeOff className="size-4.5" /> : <Eye className="size-4.5" />}
      </button>
    </div>
  );
}

function useAuthMutation(path: string) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  return useMutation({
    mutationFn: (body: unknown) => api<Me>(path, { method: "POST", body }),
    onSuccess: (me) => {
      queryClient.setQueryData(keys.me, me);
      navigate(safeNext(params.get("next")) ?? HOME[me.user.role], { replace: true });
    },
  });
}

function fieldErrors(error: unknown): Record<string, string> {
  return error instanceof ApiError ? error.fieldErrors : {};
}

export function LoginPage() {
  const { data: me } = useMe();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useAuthMutation("/auth/login");
  if (me) return <Navigate to={HOME[me.user.role]} replace />;

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate({ email, password });
  }
  const errors = fieldErrors(login.error);
  return (
    <AuthShell title="Welcome back" caption="Good food deserves another chance." subtitle={<>New here? <Link className="font-semibold text-leaf-700 underline-offset-4 hover:underline" to="/register">Create an account</Link></>}>
      <form className="space-y-5" onSubmit={submit} noValidate={false}>
        {login.isError && Object.keys(errors).length === 0 && <Notice tone="danger">{login.error.message}</Notice>}
        <Field id="email" label="Email" error={errors.email}>
          <input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} {...describedBy("email", errors.email)} />
        </Field>
        <Field id="password" label="Password" error={errors.password}>
          <PasswordInput id="password" value={password} onChange={setPassword} error={errors.password} autoComplete="current-password" />
        </Field>
        <button className="btn-primary w-full" disabled={login.isPending}>
          <BusyLabel busy={login.isPending} busyText="Logging in…">
            Log in
          </BusyLabel>
        </button>
      </form>
    </AuthShell>
  );
}

export function RegisterPage() {
  const { data: me } = useMe();
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", password: "" });
  const register = useAuthMutation("/auth/register");
  if (me) return <Navigate to={HOME[me.user.role]} replace />;
  const errors = fieldErrors(register.error);
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) => setForm({ ...form, [key]: event.target.value });

  function submit(event: FormEvent) {
    event.preventDefault();
    register.mutate({ ...form, phone: form.phone.trim() || null });
  }
  return (
    <AuthShell
      title="Create your account"
      subtitle={<>Already have one? <Link className="font-semibold text-leaf-700 underline-offset-4 hover:underline" to="/login">Log in</Link></>}
      photo={PHOTOS.steelThali}
      caption="Fresh surplus from kitchens near you, at a lower price."
    >
      <form className="space-y-5" onSubmit={submit}>
        {register.isError && Object.keys(errors).length === 0 && <Notice tone="danger">{register.error.message}</Notice>}
        <Field id="name" label="Your name" error={errors.full_name}>
          <input className="input" required minLength={2} maxLength={100} autoComplete="name" value={form.full_name} onChange={set("full_name")} {...describedBy("name", errors.full_name)} />
        </Field>
        <Field id="email" label="Email" error={errors.email}>
          <input className="input" type="email" required autoComplete="email" value={form.email} onChange={set("email")} {...describedBy("email", errors.email)} />
        </Field>
        <Field id="phone" label="Mobile number" optional error={errors.phone} hint="Only shared with a kitchen if there's a problem with your order.">
          <input className="input" type="tel" inputMode="numeric" autoComplete="tel" value={form.phone} onChange={set("phone")} {...describedBy("phone", errors.phone)} />
        </Field>
        <Field id="password" label="Password" error={errors.password} hint="At least 8 characters. A short phrase is easy to remember and hard to guess.">
          <PasswordInput id="password" value={form.password} onChange={(password) => setForm({ ...form, password })} error={errors.password} autoComplete="new-password" />
        </Field>
        <button className="btn-primary w-full" disabled={register.isPending}>
          <BusyLabel busy={register.isPending} busyText="Creating account…">
            Create account
          </BusyLabel>
        </button>
        <p className="text-center text-sm text-ink-600">
          Run a canteen, mess or PG kitchen?{" "}
          <Link to="/register/kitchen" className="font-semibold text-leaf-700 underline-offset-4 hover:underline">
            Register your kitchen
          </Link>
        </p>
      </form>
    </AuthShell>
  );
}

export function RegisterKitchenPage() {
  const { data: me } = useMe();
  const [account, setAccount] = useState({ full_name: "", email: "", phone: "", password: "" });
  const [kitchen, setKitchen] = useState<KitchenInput>(EMPTY_KITCHEN);
  const register = useAuthMutation("/auth/register-provider");
  if (me) return <Navigate to={HOME[me.user.role]} replace />;
  const errors = fieldErrors(register.error);
  const set = (key: keyof typeof account) => (event: { target: { value: string } }) => setAccount({ ...account, [key]: event.target.value });

  function submit(event: FormEvent) {
    event.preventDefault();
    register.mutate({ ...account, phone: account.phone.trim() || null, kitchen });
  }
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 lg:py-14">
      <div className="relative animate-rise overflow-hidden rounded-[2rem] bg-leaf-900 text-white shadow-lift">
        <div className="absolute inset-0 opacity-45">
          <Photo photo={PHOTOS.chefKitchen} alt="" sizes="(min-width: 768px) 768px, 100vw" priority />
        </div>
        <div className="absolute inset-0 bg-gradient-to-r from-leaf-900 via-leaf-900/85 to-leaf-900/30" />
        <div className="relative p-7 sm:p-10">
          <p className="flex items-center gap-2 text-[13px] font-semibold tracking-[0.14em] text-turmeric-300 uppercase">
            <ChefHat className="size-4" aria-hidden="true" /> For kitchens
          </p>
          <h1 className="mt-3 text-[2.2rem] leading-tight text-white sm:text-5xl">Register your kitchen</h1>
          <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-white/85">
            Tell us about your kitchen. FoodLoop reviews every kitchen, including its FSSAI registration, before it can
            list food. You'll be able to set up your dashboard straight away.
          </p>
          <ul className="mt-6 flex flex-wrap gap-2 text-[13px]">
            {[
              { icon: Store, text: "Customers pay at your counter" },
              { icon: BadgeCheck, text: "FSSAI checked" },
              { icon: ShieldCheck, text: "You set the pickup window" },
            ].map((item) => (
              <li key={item.text} className="inline-flex items-center gap-1.5 rounded-full bg-white/12 px-3 py-1.5 ring-1 ring-white/20 backdrop-blur">
                <item.icon className="size-4" aria-hidden="true" /> {item.text}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <form className="mt-8 space-y-6" onSubmit={submit}>
        {register.isError && <Notice tone="danger">{register.error.message}</Notice>}
        <section className="card p-6 sm:p-8">
          <h2 className="text-xl font-semibold">Your login</h2>
          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            <Field id="r-name" label="Manager's name" error={errors.full_name}>
              <input className="input" required minLength={2} autoComplete="name" value={account.full_name} onChange={set("full_name")} {...describedBy("r-name", errors.full_name)} />
            </Field>
            <Field id="r-phone" label="Manager's mobile" optional error={errors.phone}>
              <input className="input" type="tel" inputMode="numeric" value={account.phone} onChange={set("phone")} {...describedBy("r-phone", errors.phone)} />
            </Field>
            <Field id="r-email" label="Email" error={errors.email}>
              <input className="input" type="email" required autoComplete="email" value={account.email} onChange={set("email")} {...describedBy("r-email", errors.email)} />
            </Field>
            <Field id="r-password" label="Password" error={errors.password} hint="At least 8 characters.">
              <PasswordInput id="r-password" value={account.password} onChange={(password) => setAccount({ ...account, password })} error={errors.password} autoComplete="new-password" />
            </Field>
          </div>
        </section>
        <section className="card p-6 sm:p-8">
          <h2 className="text-xl font-semibold">Your kitchen</h2>
          <div className="mt-5">
            <KitchenFields value={kitchen} onChange={setKitchen} errors={errors} prefix="kitchen." />
          </div>
        </section>
        <Notice tone="info" title="What happens next">
          Your kitchen starts as “awaiting approval”. Once FoodLoop has checked your FSSAI details you can publish
          surplus. Nothing you add is visible to customers before then.
        </Notice>
        <button className="btn-primary w-full sm:w-auto sm:px-8" disabled={register.isPending}>
          <BusyLabel busy={register.isPending} busyText="Submitting…">
            Submit for approval
          </BusyLabel>
        </button>
      </form>
    </div>
  );
}
