"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/schedule", label: "Schedule", icon: "📅" },
  { href: "/callout", label: "Call Out", icon: "📞" },
  { href: "/dashboard", label: "Dashboard", icon: "📊" },
  { href: "/workload", label: "Workload Monitor", icon: "📈" },
  { href: "/admin/weights", label: "Weights", icon: "⚙️" },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 border-r bg-sidebar text-sidebar-foreground flex flex-col min-h-screen">
      <div className="p-4 border-b">
        <h1 className="text-lg font-bold tracking-tight">United Hebrew</h1>
        <p className="text-xs text-muted-foreground">Scheduling Intelligence</p>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative flex items-center gap-2 px-3 py-2 rounded-md text-sm",
                "transition-all duration-200 ease-out",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                  : "hover:bg-sidebar-accent/50 hover:translate-x-0.5"
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary",
                  "transition-all duration-300 ease-out",
                  active ? "opacity-100 scale-y-100" : "opacity-0 scale-y-50"
                )}
              />
              <span
                className={cn(
                  "transition-transform duration-200 ease-out",
                  "group-hover:scale-110"
                )}
              >
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t text-xs text-muted-foreground">
        v0.1.0
      </div>
    </aside>
  );
}
