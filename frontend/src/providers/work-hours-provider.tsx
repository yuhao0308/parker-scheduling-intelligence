"use client";

import {
  createContext,
  useContext,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";

type WorkHoursScope = {
  year: number;
  month: number;
};

type WorkHoursContextValue = {
  open: boolean;
  setOpen: Dispatch<SetStateAction<boolean>>;
  scope: WorkHoursScope;
  setScope: Dispatch<SetStateAction<WorkHoursScope>>;
};

const WorkHoursContext = createContext<WorkHoursContextValue | null>(null);

export function WorkHoursProvider({ children }: { children: ReactNode }) {
  const today = new Date();
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState<WorkHoursScope>({
    year: today.getFullYear(),
    month: today.getMonth() + 1,
  });

  return (
    <WorkHoursContext.Provider value={{ open, setOpen, scope, setScope }}>
      {children}
    </WorkHoursContext.Provider>
  );
}

export function useWorkHoursMonitor() {
  const context = useContext(WorkHoursContext);
  if (!context) {
    throw new Error("useWorkHoursMonitor must be used within WorkHoursProvider");
  }
  return context;
}
