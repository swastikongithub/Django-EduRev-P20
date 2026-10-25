import { useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  BadgeCheck,
  ChefHat,
  CircleCheck,
  ExternalLink,
  HandHeart,
  HeartHandshake,
  MessageCircleQuestion,
  Scale,
  ShieldCheck,
  Sparkles,
  Store,
  UtensilsCrossed,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router";

import { api, ApiError } from "../api/client";
import { useMe, useMeta } from "../api/queries";
import type { ContactTopic } from "../api/types";
import { FaqList } from "../components/Faq";
import { Reveal } from "../components/Live";
import { Photo } from "../components/Photo";
import { useToast } from "../components/Toast";
import { BusyLabel, describedBy, Field, Notice, PageHeader } from "../components/ui";
import { FAQ } from "../lib/faq";
import { PHOTOS } from "../lib/photos";

// ---------------------------------------------------------------------------------------------------------
// About
// ---------------------------------------------------------------------------------------------------------

const PRINCIPLES = [
  {
    icon: ShieldCheck,
    title: "Safety first, always",
    body: "Only FSSAI-registered kitchens, approved by us. Storage-based time limits and eat-by times are enforced by the system, not left to good intentions.",
  },
  {
    icon: Scale,
    title: "Honest by design",
    body: "Stock photos are labelled “Representative image”, demo content is labelled “Sample data”, and we don't publish impact numbers we haven't measured.",
  },
  {
    icon: HeartHandshake,
    title: "Fair for kitchens",
    body: "Kitchens set their own prices and get paid directly at their counter. FoodLoop never sits between them and their money.",
  },
  {
    icon: Sparkles,
    title: "Simple for everyone",
    body: "Listing takes under a minute, reserving takes seconds, and the handover is a 6-character code.",
  },
];

export function AboutPage() {
  return (
    <div>
      <section className="relative overflow-hidden bg-night text-white">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0">
          <div className="absolute -top-40 -right-20 size-[34rem] rounded-full bg-brand-500/20 blur-3xl" />
          <div className="absolute inset-0 bg-[radial-gradient(rgb(255_255_255/0.06)_1px,transparent_1.3px)] [background-size:22px_22px]" />
        </div>
        <div className="container-page relative grid grid-cols-1 gap-10 py-14 sm:py-20 lg:grid-cols-[1.1fr_1fr] lg:items-center">
          <div className="animate-rise">
            <p className="text-xs font-bold tracking-[0.14em] text-turmeric-300 uppercase">About FoodLoop</p>
            <h1 className="mt-3 text-[2.4rem] leading-tight text-white sm:text-[3.4rem]">
              Making sure good food <span className="text-sunrise">gets eaten.</span>
            </h1>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-white/80">
              Every day, canteens and messes cook for a crowd they can't predict exactly. FoodLoop connects the safe,
              delicious food left after service with people nearby who'd love a good meal at a lower price.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link to="/meals" className="btn-accent btn-lg">
                Explore Meals <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
              <Link to="/register/kitchen" className="btn btn-lg glass text-white hover:bg-white/20">
                <ChefHat className="size-4" aria-hidden="true" /> Become a Partner
              </Link>
            </div>
          </div>
          <div className="relative h-72 sm:h-96" aria-hidden="true">
            <div className="absolute inset-y-0 right-0 left-10 overflow-hidden rounded-[2rem] shadow-lift ring-1 ring-white/10">
              <Photo photo={PHOTOS.canteenServing} sizes="(min-width: 1024px) 40vw, 90vw" priority />
            </div>
            <div className="absolute bottom-6 left-0 w-44 overflow-hidden rounded-2xl shadow-lift ring-4 ring-night sm:w-56">
              <div className="aspect-[4/3]">
                <Photo photo={PHOTOS.chefKitchen} sizes="224px" alt="" />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="container-page grid grid-cols-1 gap-10 py-16 sm:py-20 lg:grid-cols-2 lg:gap-16">
        <Reveal>
          <p className="eyebrow">The problem</p>
          <h2 className="mt-3 text-3xl sm:text-4xl">Good food, nowhere to go.</h2>
          <p className="mt-4 text-[16px] leading-relaxed text-fg-soft">
            At the end of service, a canteen often has trays of food that are still perfectly safe and tasty. Without
            a quick way to offer it to people nearby, much of it is thrown away. Worldwide, an estimated{" "}
            <strong>1.05 billion tonnes</strong> of food was wasted in 2022, about <strong>19%</strong> of the food
            available to consumers.
          </p>
          <p className="mt-3 text-[13px] text-fg-muted">
            Source:{" "}
            <a
              className="inline-flex items-center gap-1 font-medium text-brand-400 underline-offset-4 hover:underline"
              href="https://www.unep.org/resources/publication/food-waste-index-report-2024"
              target="_blank"
              rel="noreferrer noopener"
            >
              UNEP Food Waste Index Report 2024 <ExternalLink className="size-3" aria-hidden="true" />
            </a>
          </p>
        </Reveal>
        <Reveal delay={100}>
          <p className="eyebrow">Our answer</p>
          <h2 className="mt-3 text-3xl sm:text-4xl">A simple loop.</h2>
          <ol className="mt-5 space-y-4">
            {[
              { icon: Store, text: "An approved kitchen lists its surplus with the price, portions, pickup window and allergens." },
              { icon: UtensilsCrossed, text: "You reserve in seconds and get a pickup code. No payment online." },
              { icon: HandHeart, text: "You collect it before the deadline and pay at the counter. The food gets eaten, not binned." },
            ].map((step, index) => (
              <li key={step.text} className="flex gap-4">
                <span className="font-display grid size-10 shrink-0 place-items-center rounded-full bg-brand-500 text-lg font-bold text-night">
                  {index + 1}
                </span>
                <p className="pt-1.5 text-[15.5px] leading-relaxed text-fg-soft">{step.text}</p>
              </li>
            ))}
          </ol>
        </Reveal>
      </section>

      <section className="border-y border-line/70 bg-panel/85 backdrop-blur">
        <div className="container-page py-16 sm:py-20">
          <Reveal className="mx-auto max-w-2xl text-center">
            <p className="eyebrow">What we stand for</p>
            <h2 className="mt-3 text-3xl sm:text-4xl">Our principles</h2>
          </Reveal>
          <div className="mt-12 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {PRINCIPLES.map((item, index) => (
              <Reveal key={item.title} delay={index * 80} className="card p-6 transition duration-300 hover:-translate-y-1 hover:shadow-lift">
                <div className="grid size-12 place-items-center rounded-2xl bg-brand-950 text-brand-400">
                  <item.icon className="size-6" aria-hidden="true" />
                </div>
                <h3 className="mt-4 text-lg">{item.title}</h3>
                <p className="mt-1.5 text-[14.5px] leading-relaxed text-fg-soft">{item.body}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="container-page py-16 sm:py-20">
        <div className="card grid grid-cols-1 items-center gap-8 overflow-hidden p-8 sm:p-12 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <h2 className="text-3xl sm:text-4xl">Join the loop.</h2>
            <p className="mt-3 max-w-xl text-[16px] text-fg-soft">
              Hungry? See what's available nearby. Run a kitchen? Turn tonight's surplus into tomorrow's regulars.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link to="/menu" className="btn-primary btn-lg">
                See today's menu
              </Link>
              <Link to="/contact" className="btn-secondary btn-lg">
                Talk to us
              </Link>
            </div>
          </div>
          <div className="relative mx-auto hidden h-44 w-72 sm:block" aria-hidden="true">
            {[PHOTOS.vadaPav, PHOTOS.masalaDosa, PHOTOS.gulabJamun].map((item, index) => (
              <div
                key={item.slug}
                className="absolute top-1/2 size-36 -translate-y-1/2 overflow-hidden rounded-full shadow-lift ring-[6px] ring-panel"
                style={{ left: `${index * 72}px`, zIndex: index === 1 ? 2 : 1 }}
              >
                <Photo photo={item} sizes="144px" alt="" />
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
// FAQ
// ---------------------------------------------------------------------------------------------------------

export function FaqPage() {
  return (
    <div>
      <PageHeader
        narrow
        eyebrow={
          <span className="flex items-center gap-2">
            <MessageCircleQuestion className="size-4" aria-hidden="true" /> Help centre
          </span>
        }
        title="Frequently asked questions"
        description="How reserving, paying, pickups and food safety work on FoodLoop."
      />
      <div className="mx-auto max-w-4xl space-y-12 px-4 py-10 sm:px-6">
        {FAQ.map((group) => (
          <section key={group.title} aria-labelledby={`faq-${group.title}`}>
            <h2 id={`faq-${group.title}`} className="text-2xl">
              {group.title}
            </h2>
            <div className="mt-5">
              <FaqList items={group.items} />
            </div>
          </section>
        ))}
        <div className="card flex flex-col items-start gap-4 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
          <div>
            <h2 className="text-xl">Still have a question?</h2>
            <p className="mt-1 text-[15px] text-fg-soft">Send us a message and we'll reply by email.</p>
          </div>
          <Link to="/contact" className="btn-primary">
            Contact us
          </Link>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
// Contact
// ---------------------------------------------------------------------------------------------------------

const TOPICS: ContactTopic[] = ["question", "order", "kitchen", "safety", "feedback"];

export function ContactPage() {
  const { data: me } = useMe();
  const { data: meta } = useMeta();
  const toast = useToast();
  const [form, setForm] = useState({ name: "", email: "", topic: "question" as ContactTopic, message: "", website: "" });
  const [sent, setSent] = useState(false);
  // Logged in? Fill in your name and email once; you can still change them.
  useEffect(() => {
    if (me) setForm((current) => ({ ...current, name: current.name || me.user.full_name, email: current.email || me.user.email }));
  }, [me]);
  const send = useMutation({
    mutationFn: () => api<{ detail: string }>("/contact", { method: "POST", body: form }),
    onSuccess: () => {
      setSent(true);
      toast.success("Message sent", "We'll reply by email.");
    },
  });
  const errors = send.error instanceof ApiError ? send.error.fieldErrors : {};
  const set = (key: keyof typeof form) => (event: { target: { value: string } }) => setForm({ ...form, [key]: event.target.value });

  function submit(event: FormEvent) {
    event.preventDefault();
    send.mutate();
  }

  return (
    <div>
      <PageHeader
        eyebrow="Contact"
        title="We'd love to hear from you"
        description="Questions about a pickup, listing your kitchen, a safety concern or an idea? Write to us."
      />
      <div className="container-page grid grid-cols-1 gap-8 py-10 lg:grid-cols-[1.3fr_1fr]">
        <div className="card p-6 sm:p-8">
          {sent ? (
            <div className="animate-rise py-8 text-center">
              <div className="mx-auto grid size-16 place-items-center rounded-full bg-brand-950 text-brand-400 ring-8 ring-brand-950/50">
                <CircleCheck className="size-8" aria-hidden="true" />
              </div>
              <h2 className="mt-5 text-2xl">Thanks, your message is on its way</h2>
              <p className="mt-2 text-[15px] text-fg-soft">We'll reply to {form.email} by email.</p>
              <div className="mt-6 flex justify-center gap-3">
                <Link to="/menu" className="btn-primary">
                  Back to the menu
                </Link>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => {
                    setSent(false);
                    setForm({ ...form, message: "" });
                  }}
                >
                  Send another
                </button>
              </div>
            </div>
          ) : (
            <form className="space-y-5" onSubmit={submit} noValidate>
              {send.isError && Object.keys(errors).length === 0 && <Notice tone="danger">{send.error.message}</Notice>}
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                <Field id="contact-name" label="Your name" error={errors.name}>
                  <input
                    className="input"
                    autoComplete="name"
                    required
                    value={form.name}
                    onChange={set("name")}
                    {...describedBy("contact-name", errors.name)}
                  />
                </Field>
                <Field id="contact-email" label="Email" error={errors.email} hint="We'll reply here.">
                  <input
                    className="input"
                    type="email"
                    autoComplete="email"
                    required
                    value={form.email}
                    onChange={set("email")}
                    {...describedBy("contact-email", errors.email)}
                  />
                </Field>
              </div>
              <Field id="contact-topic" label="What's it about?" error={errors.topic}>
                <select className="input" value={form.topic} onChange={set("topic")} {...describedBy("contact-topic", errors.topic)}>
                  {TOPICS.map((topic) => (
                    <option key={topic} value={topic}>
                      {meta?.labels.contact_topic?.[topic] ?? topic}
                    </option>
                  ))}
                </select>
              </Field>
              {form.topic === "safety" && (
                <Notice tone="warning" title="If someone feels unwell">
                  Get medical help first. Then tell the kitchen and us, with the meal, kitchen and pickup time.
                </Notice>
              )}
              <Field id="contact-message" label="Message" error={errors.message} hint="At least 10 characters.">
                <textarea
                  className="input min-h-36 py-3"
                  required
                  minLength={10}
                  maxLength={2000}
                  value={form.message}
                  onChange={set("message")}
                  {...describedBy("contact-message", errors.message)}
                />
              </Field>
              {/* Hidden from people; spam bots fill it in and their message is dropped. */}
              <div className="hidden" aria-hidden="true">
                <label htmlFor="contact-website">Website</label>
                <input id="contact-website" tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} />
              </div>
              <button className="btn-primary btn-lg w-full sm:w-auto" disabled={send.isPending}>
                <BusyLabel busy={send.isPending} busyText="Sending…">
                  Send message
                </BusyLabel>
              </button>
            </form>
          )}
        </div>
        <aside className="space-y-4">
          {[
            { icon: MessageCircleQuestion, title: "Quick answers", body: "Paying, cancelling and pickups are covered in the FAQ.", to: "/faq", cta: "Read the FAQ" },
            { icon: ChefHat, title: "Run a kitchen?", body: "Register and we'll check your FSSAI details.", to: "/register/kitchen", cta: "Register your kitchen" },
            { icon: BadgeCheck, title: "About a reservation?", body: "Your pickup codes and kitchen phone numbers are in My reservations.", to: "/reservations", cta: "My reservations" },
          ].map((item) => (
            <div key={item.title} className="card flex gap-4 p-5">
              <div className="grid size-11 shrink-0 place-items-center rounded-2xl bg-brand-950 text-brand-400">
                <item.icon className="size-5" aria-hidden="true" />
              </div>
              <div>
                <p className="font-semibold">{item.title}</p>
                <p className="mt-0.5 text-[14px] text-fg-soft">{item.body}</p>
                <Link to={item.to} className="mt-2 inline-flex items-center gap-1 text-[14px] font-semibold text-brand-400 underline-offset-4 hover:underline">
                  {item.cta} <ArrowRight className="size-3.5" aria-hidden="true" />
                </Link>
              </div>
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}
