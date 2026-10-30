"use client";

import Link from "next/link";

import { PageHeader } from "@/components/States";

const SECTIONS = [
  {
    href: "/masters/company",
    title: "Company calendar",
    text: "Shifts, the weekly pattern, holidays, planning settings and the list of operations.",
  },
  {
    href: "/masters/resources",
    title: "Resources",
    text: "Core machines, moulding lines, furnaces and work centres: rated capacity, shifts worked and downtime.",
  },
  {
    href: "/masters/customers",
    title: "Customers",
    text: "Who you dispatch to, with the A, B or C priority used as the scheduling tie-breaker.",
  },
  {
    href: "/masters/parts",
    title: "Parts and routes",
    text: "Part weights and moulds, plus each part's operation route with times and allowed resources.",
  },
];

export default function MastersHome() {
  return (
    <>
      <PageHeader title="Masters" subtitle="The data every plan is calculated from" />
      <ol className="grid gap-4 sm:grid-cols-2">
        {SECTIONS.map((s, i) => (
          <li key={s.href}>
            <Link href={s.href} className="panel block h-full p-4 hover:bg-sunken active:bg-line">
              <span className="font-mono text-xs text-ink-soft">{String(i + 1).padStart(2, "0")}</span>
              <span className="mt-1 block font-display text-xl font-semibold">{s.title}</span>
              <span className="mt-1 block text-sm text-ink-soft">{s.text}</span>
            </Link>
          </li>
        ))}
      </ol>
    </>
  );
}
