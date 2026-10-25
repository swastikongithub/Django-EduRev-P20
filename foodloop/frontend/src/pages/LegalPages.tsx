import type { ReactNode } from "react";

import { Notice } from "../components/ui";

function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="container-page max-w-3xl py-12 sm:py-16">
      <p className="eyebrow">Legal</p>
      <h1 className="mt-3 text-4xl sm:text-5xl">{title}</h1>
      <Notice tone="warning" className="mt-6" title="Draft for the pilot">
        This is a plain-language draft, not legal advice. Have it reviewed by a qualified professional before
        FoodLoop launches publicly.
      </Notice>
      <div className="mt-8 space-y-6 text-[15.5px] leading-relaxed text-fg-soft [&_h2]:mt-10 [&_h2]:text-2xl [&_h2]:text-fg">
        {children}
      </div>
    </article>
  );
}

export function PrivacyPage() {
  return (
    <LegalPage title="Privacy policy">
      <p>FoodLoop collects only what it needs to run reservations safely.</p>
      <h2>What we collect</h2>
      <p>
        Your name, email address and, if you give it, your mobile number; your reservations; and, for kitchens,
        business details including the FSSAI registration number. We don't collect health or allergy information
        about customers.
      </p>
      <h2>How we use it</h2>
      <p>
        To let you log in, to show kitchens who is collecting a reservation, to contact you if there's a problem
        with an order, and to keep the platform safe (for example, approving kitchens).
      </p>
      <h2>Sharing</h2>
      <p>
        A kitchen sees the name on a reservation it needs to hand over. We don't sell personal data. Login sessions
        use a secure cookie that only exists to keep you signed in.
      </p>
      <h2>Your choices</h2>
      <p>
        You can ask for your data to be corrected or deleted by writing to the contact address in the footer, in
        line with India's Digital Personal Data Protection Act, 2023.
      </p>
    </LegalPage>
  );
}

export function TermsPage() {
  return (
    <LegalPage title="Terms of use">
      <h2>What FoodLoop is</h2>
      <p>
        FoodLoop lists surplus food from kitchens that we have approved. The kitchen prepares, stores and hands over
        the food, and is responsible for its safety and for holding a valid FSSAI registration or licence.
      </p>
      <h2>Reservations and payment</h2>
      <p>
        A reservation holds portions for you until the end of the pickup window. During the pilot you pay the
        kitchen directly at the counter. Please cancel if you can't make it, so someone else can have the meal.
      </p>
      <h2>Food safety</h2>
      <p>
        Every listing shows when it was prepared, how it was stored, its allergens and an eat-by time. Eat food soon
        after collecting it. If you have a severe allergy, confirm with the kitchen before eating.
      </p>
      <h2>Acceptable use</h2>
      <p>
        Don't make reservations you don't intend to collect, and don't resell food bought through FoodLoop. Accounts
        that repeatedly miss pickups may be limited.
      </p>
    </LegalPage>
  );
}
