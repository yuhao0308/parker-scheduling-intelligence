"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setDemoAuthenticated } from "@/components/app-shell";

// Demo-only credentials. The POC has no real authentication backend; this
// gate exists so the demo flow matches the supervisor expectation of a login
// before the schedule view. Swap for a real auth flow before production.
const DEMO_EMAIL = "admin@unitedhebrew.demo";
const DEMO_PASSWORD = "unitedhebrew2026";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (email.trim().toLowerCase() === DEMO_EMAIL && password === DEMO_PASSWORD) {
      setDemoAuthenticated(true);
      router.replace("/schedule");
      return;
    }
    setError("Email or password is incorrect.");
  }

  return (
    <div className="min-h-screen w-full flex bg-white">
      {/* Left — hero panel */}
      <div className="relative hidden md:block md:w-1/2 overflow-hidden bg-slate-200">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{
            backgroundImage:
              "linear-gradient(135deg, rgba(20,45,90,0.15), rgba(0,0,0,0.35)), url('/login-hero.png')",
          }}
          aria-hidden
        />
        {/* Logo card */}
        <div className="absolute top-6 left-6 flex items-center gap-3 rounded-xl bg-white/95 px-4 py-3 shadow-lg">
          <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-100">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="#1e3a8a"
              strokeWidth="1.8"
              className="h-6 w-6"
              aria-hidden
            >
              <path d="M12 2v20M4 8l8 4 8-4M4 16l8 4 8-4" />
            </svg>
          </div>
          <div className="leading-tight">
            <div className="text-xs font-bold tracking-wider text-slate-900">
              UNITED HEBREW
            </div>
            <div className="text-[11px] text-slate-600">
              Scheduling Intelligence
            </div>
          </div>
        </div>
        {/* Tagline */}
        <div className="absolute bottom-12 left-6 right-6 text-white drop-shadow-lg">
          <div className="text-2xl md:text-3xl font-bold tracking-tight">
            Smarter shifts. Better care. Driven by AI.
          </div>
        </div>
        {/* Copyright */}
        <div className="absolute bottom-3 left-6 text-[11px] text-white/70">
          Copyright © 2026 United Hebrew &nbsp;|&nbsp; All rights reserved
        </div>
      </div>

      {/* Right — form panel */}
      <div className="flex w-full md:w-1/2 items-center justify-center px-6 py-12">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-sm space-y-5"
          aria-label="Login form"
        >
          <h1 className="text-xl font-bold text-slate-900">
            Log in to your account
          </h1>

          <div className="space-y-1.5">
            <label
              htmlFor="email"
              className="block text-sm font-medium text-slate-700"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="example@email.com"
              className="w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
              required
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="password"
              className="block text-sm font-medium text-slate-700"
            >
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="******"
                className="w-full rounded border border-slate-300 px-3 py-2 pr-10 text-sm outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-500 hover:text-slate-700"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? (
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    className="h-5 w-5"
                  >
                    <path d="M3 3l18 18" />
                    <path d="M10.58 10.58a2 2 0 002.83 2.83" />
                    <path d="M9.88 4.24A10.94 10.94 0 0112 4c7 0 10 8 10 8a18.5 18.5 0 01-3.17 4.19M6.61 6.61A18.5 18.5 0 002 12s3 8 10 8a10.94 10.94 0 004.88-1.16" />
                  </svg>
                ) : (
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    className="h-5 w-5"
                  >
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between text-sm">
            <label className="flex items-center gap-2 cursor-pointer text-slate-700">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4"
              />
              Remember me
            </label>
            <button
              type="button"
              className="text-blue-700 hover:underline"
              onClick={() =>
                setError("Password recovery isn't set up for the demo.")
              }
            >
              Forgot Password?
            </button>
          </div>

          {error && (
            <div
              className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
              role="alert"
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            className="w-full rounded bg-[#1e3a8a] py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#172d6b]"
          >
            Login
          </button>

          <p className="text-[11px] text-slate-500 text-center">
            Demo credentials: {DEMO_EMAIL} / {DEMO_PASSWORD}
          </p>
        </form>
      </div>
    </div>
  );
}
