import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/providers/query-provider";
import { WorkHoursProvider } from "@/providers/work-hours-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppSidebar } from "@/components/app-sidebar";
import { WorkHoursMonitor } from "@/components/work-hours-monitor";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Parker Scheduling Intelligence",
  description: "Same-day call-out replacement decision support",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex">
        <QueryProvider>
          <WorkHoursProvider>
            <TooltipProvider>
              <AppSidebar />
              <main className="flex-1 p-6 overflow-auto">{children}</main>
              <WorkHoursMonitor />
            </TooltipProvider>
          </WorkHoursProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
