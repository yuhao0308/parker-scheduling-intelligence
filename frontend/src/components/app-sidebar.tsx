"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/schedule", label: "Schedule", icon: "📅" },
  { href: "/callout", label: "Callout", icon: "📞" },
  { href: "/dashboard", label: "Dashboard", icon: "📊" },
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
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
              pathname.startsWith(item.href)
                ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                : "hover:bg-sidebar-accent/50"
            )}
          >
            <span>{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="p-4 border-t text-xs text-muted-foreground">
        v0.1.0
      </div>
    </aside>
  );
}
