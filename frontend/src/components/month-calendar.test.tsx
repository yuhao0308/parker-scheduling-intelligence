import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MonthCalendar } from "@/components/month-calendar";
import type { MonthlySchedule } from "@/lib/types";

afterEach(() => {
  cleanup();
});

function emptyMonth(year: number, month: number): MonthlySchedule {
  const daysInMonth = new Date(year, month, 0).getDate();

  return {
    year,
    month,
    days: Array.from({ length: daysInMonth }, (_, i) => ({
      date: `${year}-${String(month).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`,
      slots: [],
    })),
  };
}

function monthWithSingleDayShift(
  year: number,
  month: number,
  day: number,
): MonthlySchedule {
  const schedule = emptyMonth(year, month);
  const date = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

  return {
    ...schedule,
    days: schedule.days.map((entry) =>
      entry.date === date
        ? {
            ...entry,
            slots: [
              {
                unit_id: "U-SA1",
                unit_name: "Subacute Unit 1",
                shift_date: date,
                shift_label: "DAY",
                status: "fully_staffed",
                assigned_employees: [
                  {
                    employee_id: "RN001",
                    name: "Maria Rodriguez",
                    license: "RN",
                    confirmation_status: "ACCEPTED",
                  },
                ],
                callout_count: 0,
                callout_employee_ids: [],
                required_count: 1,
                unresolved_callout_count: 0,
              },
            ],
          }
        : entry,
    ),
  };
}

describe("MonthCalendar", () => {
  it("shows muted adjacent-month dates to complete the calendar weeks", () => {
    render(
      <MonthCalendar
        data={emptyMonth(2026, 4)}
        isLoading={false}
        onSlotClick={vi.fn()}
        onDayClick={vi.fn()}
        selectedUnit={null}
        statusFilter="all"
        today={new Date("2026-04-15T00:00:00")}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "2026-03-31 outside current month",
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", {
        name: "2026-05-01 outside current month",
      }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "2026-04-30 schedule" }),
    ).toBeEnabled();
  });

  it("shows lighter shift information for adjacent-month dates when available", () => {
    render(
      <MonthCalendar
        data={emptyMonth(2026, 4)}
        adjacentData={[monthWithSingleDayShift(2026, 5, 1)]}
        isLoading={false}
        onSlotClick={vi.fn()}
        onDayClick={vi.fn()}
        selectedUnit={null}
        statusFilter="all"
        today={new Date("2026-04-15T00:00:00")}
      />,
    );

    expect(
      screen.getByRole("button", {
        name: "2026-05-01 outside current month",
      }),
    ).toBeDisabled();
    expect(screen.getByTitle("Day — Fully Staffed (1/1)")).toBeInTheDocument();
  });

  it("does not open day details for adjacent-month placeholders", async () => {
    const user = userEvent.setup();
    const onDayClick = vi.fn();

    render(
      <MonthCalendar
        data={emptyMonth(2026, 4)}
        isLoading={false}
        onSlotClick={vi.fn()}
        onDayClick={onDayClick}
        selectedUnit={null}
        statusFilter="all"
        today={new Date("2026-04-15T00:00:00")}
      />,
    );

    await user.click(
      screen.getByRole("button", {
        name: "2026-05-01 outside current month",
      }),
    );

    expect(onDayClick).not.toHaveBeenCalled();
  });
});
