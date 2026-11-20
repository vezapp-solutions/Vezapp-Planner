"use client";

import Link from "next/link";

import { Panel } from "@/components/Panel";
import { PageHeader } from "@/components/States";
import { FAQ, GLOSSARY, GUIDE } from "@/lib/help-content";
import { useTour } from "@/lib/tour-store";

export default function HelpPage() {
  const startTour = useTour((s) => s.start);

  return (
    <>
      <PageHeader title="Help" subtitle="From first login to your first plan, in plain words">
        <button type="button" className="btn btn-primary" onClick={startTour}>
          Take the tour
        </button>
      </PageHeader>

      <div className="space-y-6">
        <Panel title="What Vezapp Planner does">
          <p className="max-w-3xl text-[0.9375rem] leading-relaxed">
            A foundry makes metal parts by pouring melted metal into sand moulds. Every month you get orders with dates, and someone has to decide what to mould and melt on which day and shift. Vezapp does that arithmetic for you, using your real machines and shifts, and tells you which orders are safe and which are in danger, with the reason.
          </p>
          <p className="mt-3 max-w-3xl text-[0.9375rem] leading-relaxed text-ink-soft">
            You set it up once, upload the month&apos;s orders, tell it what you already have in stock, and press one button.
          </p>
        </Panel>

        <section aria-label="The steps from start to finish" className="space-y-4">
          <h2 className="font-display text-xl font-bold tracking-tight">The whole process, step by step</h2>
          <ol className="space-y-4">
            {GUIDE.map((step, i) => (
              <li key={step.title} className="panel flex gap-4 p-5 sm:p-6">
                <span className="step-num mt-0.5">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <h3 className="font-display text-lg font-semibold tracking-tight">{step.title}</h3>
                    <Link href={step.href} className="inline-flex min-h-8 items-center text-sm font-medium text-link underline-offset-2 hover:underline">
                      Open {step.where} →
                    </Link>
                  </div>
                  <p className="mt-1.5 text-[0.9375rem] leading-relaxed">{step.body}</p>
                  <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink-soft">
                    {step.tips.map((tip) => (
                      <li key={tip}>{tip}</li>
                    ))}
                  </ul>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <Panel title="Words you will see" note={`${GLOSSARY.length} terms`}>
          <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
            {GLOSSARY.map((g) => (
              <div key={g.term}>
                <dt className="font-semibold">{g.term}</dt>
                <dd className="mt-0.5 text-sm leading-relaxed text-ink-soft">{g.meaning}</dd>
              </div>
            ))}
          </dl>
        </Panel>

        <Panel title="Common questions">
          <div className="divide-y divide-line">
            {FAQ.map((f) => (
              <details key={f.q} className="group py-3">
                <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between gap-4 font-medium [&::-webkit-details-marker]:hidden">
                  {f.q}
                  <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 shrink-0 text-ink-soft transition-transform duration-200 group-open:rotate-180" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m5 8 5 5 5-5" />
                  </svg>
                </summary>
                <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-soft">{f.a}</p>
              </details>
            ))}
          </div>
        </Panel>

        <Panel title="Still stuck?">
          <p className="text-[0.9375rem]">
            Press <strong>Ask AI</strong> (the round button at the top) and type your question in plain words. It can explain what any number on screen means. Or <button type="button" className="font-medium text-link underline-offset-2 hover:underline" onClick={startTour}>replay the tour</button>.
          </p>
        </Panel>
      </div>
    </>
  );
}
