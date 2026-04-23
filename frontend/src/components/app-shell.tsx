"use client";

import { useEffect, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { WorkHoursMonitor } from "@/components/work-hours-monitor";

const AUTH_STORAGE_KEY = "demo_auth";
const AUTH_EVENT = "parker:auth-change";

export function isDemoAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(AUTH_STORAGE_KEY) === "1";
}

export function setDemoAuthenticated(authed: boolean) {
  if (typeof window === "undefined") return;
  if (authed) window.localStorage.setItem(AUTH_STORAGE_KEY, "1");
  else window.localStorage.removeItem(AUTH_STORAGE_KEY);
  window.dispatchEvent(new Event(AUTH_EVENT));
}

function subscribeAuth(callback: () => void): () => void {
  window.addEventListener(AUTH_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(AUTH_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function getSnapshot(): "authed" | "unauthed" {
  return window.localStorage.getItem(AUTH_STORAGE_KEY) === "1"
    ? "authed"
    : "unauthed";
}

function getServerSnapshot(): "authed" | "unauthed" {
  return "unauthed";
}

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const isLoginRoute = pathname === "/login";
  const authState = useSyncExternalStore(
    subscribeAuth,
    getSnapshot,
    getServerSnapshot,
  );
  const authed = authState === "authed";

  useEffect(() => {
    if (!authed && !isLoginRoute) {
      router.replace("/login");
    }
  }, [authed, isLoginRoute, router]);

  if (isLoginRoute) {
    return <>{children}</>;
  }

  if (!authed) {
    // Blank screen while redirect is in flight. Prevents sidebar flash.
    return <div className="min-h-screen w-full bg-background" />;
  }

  return (
    <div className="flex min-h-screen w-full">
      <AppSidebar />
      <main className="flex-1 p-6 overflow-auto">{children}</main>
      <WorkHoursMonitor />
    </div>
  );
}
