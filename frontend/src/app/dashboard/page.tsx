"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useRecentCallouts } from "@/lib/queries";

export default function DashboardPage() {
  const { data: callouts, isLoading, isError, error } = useRecentCallouts();

  const totalCallouts = callouts?.length ?? 0;
  const overrideCount =
    callouts?.filter(
      (c) => c.selected_rank !== null && c.selected_rank !== 1
    ).length ?? 0;
  const overrideRate =
    totalCallouts > 0 ? ((overrideCount / totalCallouts) * 100).toFixed(0) : "0";

  return (
    <div className="max-w-6xl space-y-6">
      <h2 className="text-2xl font-bold">Dashboard</h2>

      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground font-normal">
              Recent Callouts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{totalCallouts}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground font-normal">
              Overrides
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{overrideCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground font-normal">
              Override Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{overrideRate}%</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Call-Outs</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="py-8 text-center text-muted-foreground">Loading...</div>
          ) : isError ? (
            <div className="py-8 text-center text-destructive">{error.message}</div>
          ) : !callouts || callouts.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">
              No callouts recorded yet.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Shift</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead>Called Out</TableHead>
                  <TableHead>Selected</TableHead>
                  <TableHead>Override?</TableHead>
                  <TableHead>Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {callouts.map((c) => {
                  const isOverride =
                    c.selected_rank !== null && c.selected_rank !== 1;
                  return (
                    <TableRow
                      key={c.callout_id}
                      className={isOverride ? "bg-amber-50" : ""}
                    >
                      <TableCell className="tabular-nums">{c.shift_date}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{c.shift_label}</Badge>
                      </TableCell>
                      <TableCell>{c.unit_id}</TableCell>
                      <TableCell>{c.employee_id}</TableCell>
                      <TableCell>{c.selected_employee_id ?? "—"}</TableCell>
                      <TableCell>
                        {c.selected_rank === null ? (
                          "—"
                        ) : isOverride ? (
                          <Badge className="bg-amber-100 text-amber-800">
                            #{c.selected_rank}
                          </Badge>
                        ) : (
                          <Badge className="bg-emerald-100 text-emerald-800">
                            Top Pick
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-48 truncate">
                        {c.override_reason ?? "—"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
