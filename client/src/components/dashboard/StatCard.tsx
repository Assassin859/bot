import { ReactNode } from "react";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: string | number;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  icon: ReactNode;
  subtitle?: string;
}

export function StatCard({ title, value, trend, icon, subtitle }: StatCardProps) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-card/50 p-6 backdrop-blur-xl transition-all duration-300 hover:border-white/10 hover:shadow-2xl hover:shadow-black/20">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{title}</p>
          <h3 className="mt-2 font-display text-3xl font-bold tracking-tight text-foreground">
            {value}
          </h3>
        </div>
        <div className="rounded-xl bg-white/5 p-3 text-primary ring-1 ring-white/10">
          {icon}
        </div>
      </div>
      
      <div className="mt-4 flex items-center gap-2">
        {trend && (
          <div className={cn(
            "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
            trend.isPositive 
              ? "bg-green-500/10 text-green-500" 
              : "bg-red-500/10 text-red-500"
          )}>
            {trend.isPositive ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {trend.value}%
          </div>
        )}
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
