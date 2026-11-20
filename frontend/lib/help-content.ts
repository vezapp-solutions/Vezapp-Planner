import type { Role } from "./types";

/**
 * Everything the welcome tour and the Help page say, in one place so the two never disagree.
 * Written for someone who has never seen a foundry planning screen: short sentences, no jargon without a gloss.
 */

export interface TourStep {
  id: string;
  title: string;
  body: string;
  /** A CSS selector for the thing to spotlight. When it is not on screen (it sits under More) the card just shows. */
  target?: string;
  /** Only for these roles; everyone when absent. */
  roles?: Role[];
}

const nav = (href: string) => `nav[aria-label="Main"] a[href="${href}"]`;
const PLANNERS: Role[] = ["vezapp_admin", "company_admin", "planner"];

export const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    title: "Welcome aboard!",
    body: "Vezapp Planner turns your monthly orders into a day-by-day plan for moulding and melting, so you know what to make, when, and which orders are in danger. Take a one-minute tour and you'll be ready to go.",
  },
  {
    id: "home",
    title: "Home: your morning view",
    body: "Open this first thing. It shows today's and tomorrow's plan, how many orders will miss their date, and which machine is the bottleneck. Red means look here first.",
    target: nav("/home"),
  },
  {
    id: "masters",
    title: "Masters: teach it your foundry once",
    body: "Add your shifts, machines, customers and parts here. You fill it in once, and every plan after that uses it. If a part is missing something, the app tells you exactly what.",
    target: nav("/masters"),
  },
  {
    id: "scheduler",
    title: "Scheduler: drop in this month's orders",
    body: "Upload your Excel sheet and see a preview before anything is saved. A part that isn't set up yet won't block the file: the other rows load, and you can create the missing part on the spot.",
    target: nav("/scheduler"),
  },
  {
    id: "plan",
    title: "Plan: one button, a full plan",
    body: "Press Run planning and get a mould plan (what to make on each machine, shift by shift) and a melt plan (which heats to melt, one metal grade each). Every late order comes with a reason.",
    target: nav("/plan"),
  },
  {
    id: "whatif",
    title: "What-if: try it before it happens",
    body: "A furnace may break down on Thursday? Test it on a copy of the plan and see which orders slip. Nothing real changes until you say so.",
    target: nav("/what-if"),
    roles: PLANNERS,
  },
  {
    id: "insights",
    title: "Insights: the advisor",
    body: "Plain-language cards that point out what needs attention, like a low on-time rate or parts with no route, each with a next step. Print the daily digest for your morning meeting.",
    target: nav("/insights"),
  },
  {
    id: "ask",
    title: "Ask AI: just ask",
    body: "Type a question in plain words, even in Hindi or Hinglish: which orders are late, why, is this machine free tomorrow. It only uses your own data and never changes anything.",
    target: ".ask-btn",
  },
  {
    id: "reports",
    title: "Reports: proof and numbers",
    body: "On-time delivery, machine utilisation, and plan versus what really happened. Download any of them as PDF or Excel for your team or your customer.",
    target: nav("/reports"),
  },
  {
    id: "help",
    title: "Stuck? Help is one tap away",
    body: "The Help page walks through the whole process from setup to the final plan, with a short glossary of foundry words. You can also replay this tour from there whenever you like.",
    target: nav("/help"),
  },
  {
    id: "done",
    title: "You're all set",
    body: "That's everything. Start with Masters if your foundry isn't set up yet, or go straight to the Scheduler to upload this month's orders. Your first plan is only a few clicks away.",
  },
];

export function stepsFor(role: Role): TourStep[] {
  return TOUR_STEPS.filter((s) => !s.roles || s.roles.includes(role));
}

/** Where the "seen the tour" flag lives, one per person per browser. */
export const tourKey = (userId: number) => `vp-tour-seen:${userId}`;

export function hasSeenTour(userId: number): boolean {
  try {
    return window.localStorage.getItem(tourKey(userId)) === "1";
  } catch {
    return true; // storage blocked: do not nag on every page load
  }
}

export function markTourSeen(userId: number) {
  try {
    window.localStorage.setItem(tourKey(userId), "1");
  } catch {
    /* nothing to do: the tour just offers itself again next time */
  }
}

/* ------------------------------------------------------------------------------------------------------------ */
/* The Help page */

export interface GuideStep {
  title: string;
  where: string;
  href: string;
  body: string;
  tips: string[];
}

/** The whole journey, in the order a new foundry does it. */
export const GUIDE: GuideStep[] = [
  {
    title: "Set up your foundry",
    where: "Masters",
    href: "/masters",
    body: "Tell Vezapp how your plant works. This is done once, and it is what makes the plan realistic. Work down the list, because each step uses the one before.",
    tips: [
      "Company calendar: your shifts (for example 6 AM to 2 PM), weekly offs and holidays.",
      "Resources: your moulding lines and furnaces, with how fast they work and when they are down for maintenance.",
      "Customers: a code, a name, and a priority (A, B or C). Priority breaks ties when two orders are due the same day.",
      "Parts and routes: each part's weight, its metal grade, how many castings fit in a mould, and the steps it goes through.",
    ],
  },
  {
    title: "Upload this month's orders",
    where: "Monthly Scheduler, Upload Excel",
    href: "/scheduler/upload",
    body: "Download the template, fill one row per order (part number, quantity, dispatch date), and upload it. You always see a preview first, and nothing is saved until you confirm.",
    tips: [
      "A part that is not in your Part Master does not stop the upload. The other rows load, and a box lists the missing parts with a Create part button.",
      "The same file can be uploaded again later to update stock. Blank stock cells leave what is already recorded.",
      "Rows are numbered the way Excel numbers them, so row 9 here is row 9 in your sheet.",
    ],
  },
  {
    title: "Tell it what is already made",
    where: "Monthly Scheduler or Plan, Orders tab",
    href: "/scheduler",
    body: "Type the WIP, FG and Dispatched numbers beside each order and press Enter. Only the balance still needs making, so stock you already hold is never planned twice.",
    tips: [
      "WIP is castings partly made and still in the shop. FG is finished and waiting. Dispatched is already sent.",
      "Balance = Order quantity - (WIP + FG + Dispatched). If the balance is 0, the order shows Covered by stock.",
      "The History link beside an order shows who changed what and when.",
    ],
  },
  {
    title: "Run planning",
    where: "Plan",
    href: "/plan",
    body: "Press Run planning. Vezapp works through your open orders, earliest date first, and fills each machine's shifts with moulds, then works out the metal that needs melting.",
    tips: [
      "Any change to orders, stock or settings marks the plan Stale. Press Run planning again to refresh it. It never changes on its own.",
      "Confirm plan freezes a version as your baseline, so you can compare it with what really happened later.",
    ],
  },
  {
    title: "Read the mould plan and the melt plan",
    where: "Plan, Mould plan and Melt plan tabs",
    href: "/plan",
    body: "The mould plan shows, for each day, shift and machine, which part to make and how full the machine is. The melt plan shows each heat: its metal grade, how many kilos, and how full the furnace is.",
    tips: [
      "One heat is one metal grade. Grades are never mixed in a heat.",
      "A heat below 70% full gets a warning, because half-empty melts waste electricity.",
      "Print and export gives you Excel files for the shop floor.",
    ],
  },
  {
    title: "Deal with the risks",
    where: "Home, Insights and What-if",
    href: "/home",
    body: "Start on Home: the red At risk tile and the Dispatch lines at risk list show which orders will miss their date and what is holding each one up. Then try fixes safely.",
    tips: [
      "What-if lets you test a machine breakdown, extra shift or overtime on a copy of the plan, and see which orders move.",
      "Ask AI answers questions like which orders are late and why, using only your own numbers.",
    ],
  },
  {
    title: "Learn from what happened",
    where: "Reports",
    href: "/reports",
    body: "Enter the real dispatch dates, and the reports show your on-time rate, how busy each machine was, and how the plan compared with reality.",
    tips: ["Every report downloads as PDF or Excel.", "On time means shipped on or before the internal due date."],
  },
];

export interface GlossaryItem {
  term: string;
  meaning: string;
}

export const GLOSSARY: GlossaryItem[] = [
  { term: "Mould", meaning: "A block of sand shaped like the part. Liquid metal is poured into it. One mould can make several copies." },
  { term: "Heat", meaning: "One batch of melted metal from a furnace. Every heat is a single metal grade." },
  { term: "Grade", meaning: "The metal recipe, for example GG25 cast iron." },
  { term: "Cavity", meaning: "How many copies of the part one mould makes." },
  { term: "Pouring weight", meaning: "The metal poured into one mould, including the channels that feed it. It is more than the finished part weighs." },
  { term: "Rejection %", meaning: "The share of parts that fail checks and are scrapped. The plan makes extra to cover it." },
  { term: "WIP", meaning: "Work in progress: castings partly made and still in the shop." },
  { term: "FG", meaning: "Finished goods: made, checked and waiting to be sent." },
  { term: "Balance", meaning: "What is still to be made: order quantity minus WIP, FG and dispatched." },
  { term: "Route", meaning: "The steps a part goes through, such as moulding and melting, and the machines allowed for each." },
  { term: "Fill %", meaning: "How full a furnace heat is compared with its size." },
  { term: "Stale plan", meaning: "The plan is out of date because something changed. Press Run planning to refresh it." },
  { term: "Internal due date", meaning: "The date you plan to dispatch by. Late and on-time are measured against it." },
  { term: "Bottleneck", meaning: "The machine that holds the plan back, the busiest one." },
];

export interface Faq {
  q: string;
  a: string;
}

export const FAQ: Faq[] = [
  { q: "A part in my file says it is not in the Part Master. What now?", a: "The other rows still load. Press Create part beside it, fill in the name, grade, weights and castings per mould, and the file is checked again. Or fix the part number in Excel and upload again." },
  { q: "Why does an order say Cannot plan?", a: "Its part is missing something the plan needs, such as a moulding step, a machine, a weight or a grade. The badge names exactly what to add in Masters." },
  { q: "Why is the plan marked Stale?", a: "You changed an order, stock or a setting after it was calculated. Press Run planning to refresh it." },
  { q: "Why does an order show At risk?", a: "It cannot be finished by its internal due date with the machines and shifts you have. The list shows how many working days late and what is holding it up." },
  { q: "Will the AI change my data?", a: "No. Ask AI can only read your plan and answer. It cannot add, edit or delete anything." },
  { q: "Who can do what?", a: "Viewers can look at everything. Planners can also upload orders, edit stock, run planning and use What-if. Company Admins can also edit Masters and manage users." },
];
