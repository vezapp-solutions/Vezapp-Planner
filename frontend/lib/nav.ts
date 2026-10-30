import type { Role } from "./types";

export interface NavItem {
  href: string;
  label: string;
  roles: Role[];
  /** Build phase that delivers this screen. Items without one are live now. */
  phase?: number;
  children?: { href: string; label: string }[];
}

const everyone: Role[] = ["vezapp_admin", "company_admin", "planner", "viewer"];
const planners: Role[] = ["vezapp_admin", "company_admin", "planner"];
const admins: Role[] = ["vezapp_admin", "company_admin"];

export const NAV: NavItem[] = [
  { href: "/home", label: "Home", roles: everyone },
  {
    href: "/masters",
    label: "Masters",
    roles: everyone,
    children: [
      { href: "/masters/company", label: "Company calendar" },
      { href: "/masters/resources", label: "Resources" },
      { href: "/masters/customers", label: "Customers" },
      { href: "/masters/parts", label: "Parts and routes" },
    ],
  },
  {
    href: "/scheduler",
    label: "Monthly Scheduler",
    roles: everyone,
    children: [
      { href: "/scheduler", label: "Month grid" },
      { href: "/scheduler/upload", label: "Upload Excel" },
    ],
  },
  { href: "/plan", label: "Plan", roles: everyone },
  { href: "/machine-shop", label: "Machine shop", roles: everyone },
  { href: "/what-if", label: "What-if", roles: planners },
  { href: "/insights", label: "Insights", roles: everyone },
  { href: "/reports", label: "Reports", roles: everyone },
  { href: "/companies", label: "Companies", roles: ["vezapp_admin"] },
  { href: "/settings/users", label: "Users", roles: admins },
  { href: "/settings/data-health", label: "Data health", roles: planners },
  { href: "/settings/audit", label: "Audit log", roles: admins },
];

export function navFor(role: Role): NavItem[] {
  return NAV.filter((item) => item.roles.includes(role));
}

export const canEditMasters = (role: Role) => role === "vezapp_admin" || role === "company_admin";
