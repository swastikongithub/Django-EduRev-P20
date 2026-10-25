import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChefHat, KeyRound, Mail, ShieldCheck, Ticket, UserRound } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router";

import { api, ApiError } from "../api/client";
import { keys, useMe } from "../api/queries";
import type { Me } from "../api/types";
import { useToast } from "../components/Toast";
import { BusyLabel, describedBy, Field, Notice, PageHeader, PageLoader } from "../components/ui";

const ROLE_LABEL = { customer: "Customer", provider: "Kitchen account", admin: "FoodLoop admin" } as const;

function ProfileForm({ me }: { me: Me }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({ full_name: me.user.full_name, phone: me.user.phone ?? "" });
  useEffect(() => setForm({ full_name: me.user.full_name, phone: me.user.phone ?? "" }), [me.user.full_name, me.user.phone]);
  const save = useMutation({
    mutationFn: () => api<Me>("/auth/me", { method: "PUT", body: form }),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.me, updated);
      toast.success("Profile saved");
    },
  });
  const errors = save.error instanceof ApiError ? save.error.fieldErrors : {};
  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }
  return (
    <form className="card space-y-5 p-6 sm:p-8" onSubmit={submit}>
      <h2 className="flex items-center gap-2 text-xl">
        <UserRound className="size-5 text-brand-400" aria-hidden="true" /> Your details
      </h2>
      {save.isError && Object.keys(errors).length === 0 && <Notice tone="danger">{save.error.message}</Notice>}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <Field id="account-name" label="Name" error={errors.full_name}>
          <input
            className="input"
            required
            minLength={2}
            maxLength={100}
            autoComplete="name"
            value={form.full_name}
            onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            {...describedBy("account-name", errors.full_name)}
          />
        </Field>
        <Field id="account-phone" label="Mobile number" optional error={errors.phone} hint="Only shared with a kitchen if there's a problem with your order.">
          <input
            className="input"
            type="tel"
            inputMode="numeric"
            autoComplete="tel"
            value={form.phone}
            onChange={(event) => setForm({ ...form, phone: event.target.value })}
            {...describedBy("account-phone", errors.phone)}
          />
        </Field>
      </div>
      <div>
        <p className="label">Email</p>
        <p className="flex items-center gap-2 rounded-xl bg-raised px-3.5 py-2.5 text-[15px] text-fg-soft">
          <Mail className="size-4 text-fg-muted" aria-hidden="true" /> {me.user.email}
        </p>
        <p className="hint">To change your email, contact us.</p>
      </div>
      <button className="btn-primary" disabled={save.isPending}>
        <BusyLabel busy={save.isPending} busyText="Saving…">
          Save details
        </BusyLabel>
      </button>
    </form>
  );
}

function PasswordForm() {
  const toast = useToast();
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const change = useMutation({
    mutationFn: () => api<void>("/auth/change-password", { method: "POST", body: form }),
    onSuccess: () => {
      setForm({ current_password: "", new_password: "" });
      toast.success("Password changed", "You've been logged out on your other devices.");
    },
  });
  const errors = change.error instanceof ApiError ? change.error.fieldErrors : {};
  function submit(event: FormEvent) {
    event.preventDefault();
    change.mutate();
  }
  return (
    <form className="card space-y-5 p-6 sm:p-8" onSubmit={submit}>
      <h2 className="flex items-center gap-2 text-xl">
        <KeyRound className="size-5 text-brand-400" aria-hidden="true" /> Change password
      </h2>
      {change.isError && Object.keys(errors).length === 0 && <Notice tone="danger">{change.error.message}</Notice>}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <Field id="current-password" label="Current password" error={errors.current_password}>
          <input
            className="input"
            type="password"
            required
            autoComplete="current-password"
            value={form.current_password}
            onChange={(event) => setForm({ ...form, current_password: event.target.value })}
            {...describedBy("current-password", errors.current_password)}
          />
        </Field>
        <Field id="new-password" label="New password" error={errors.new_password} hint="At least 8 characters. A short phrase works well.">
          <input
            className="input"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={form.new_password}
            onChange={(event) => setForm({ ...form, new_password: event.target.value })}
            {...describedBy("new-password", errors.new_password)}
          />
        </Field>
      </div>
      <button className="btn-secondary" disabled={change.isPending}>
        <BusyLabel busy={change.isPending} busyText="Changing…">
          Change password
        </BusyLabel>
      </button>
    </form>
  );
}

export function AccountPage() {
  const { data: me } = useMe();
  if (!me) return <PageLoader />;
  const shortcut =
    me.user.role === "customer"
      ? { to: "/reservations", label: "My reservations", icon: Ticket }
      : me.user.role === "provider"
        ? { to: "/kitchen", label: "Kitchen dashboard", icon: ChefHat }
        : { to: "/admin", label: "Admin dashboard", icon: ShieldCheck };
  return (
    <div>
      <PageHeader
        narrow
        eyebrow="My account"
        title={`Hello, ${me.user.full_name.split(" ")[0]}`}
        description={
          <span className="inline-flex items-center gap-2">
            <span className="badge bg-brand-900 text-brand-300">{ROLE_LABEL[me.user.role]}</span>
            {me.provider && <span>{me.provider.name}</span>}
          </span>
        }
        actions={
          <Link to={shortcut.to} className="btn-primary">
            <shortcut.icon className="size-4" aria-hidden="true" /> {shortcut.label}
          </Link>
        }
      />
      <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
        <ProfileForm me={me} />
        <PasswordForm />
      </div>
    </div>
  );
}
