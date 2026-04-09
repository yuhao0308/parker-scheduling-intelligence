"use client";

import { Badge } from "@/components/ui/badge";
import type { FilterStats } from "@/lib/types";

export function FilterStatsBadge({ stats }: { stats: FilterStats }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="secondary">
        {stats.passed_filter} eligible of {stats.total_pool}
      </Badge>
      {Object.entries(stats.filtered_out).map(([reason, count]) => (
        <Badge key={reason} variant="outline" className="text-muted-foreground">
          {count} {reason.replace(/_/g, " ")}
        </Badge>
      ))}
    </div>
  );
}
