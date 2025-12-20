import { Signal } from "@shared/schema";
import { formatDistanceToNow } from "date-fns";
import { ArrowRight, Target, ShieldAlert, Clock } from "lucide-react";
import { cn } from "@/lib/utils";

export function SignalCard({ signal }: { signal: Signal }) {
  const isBuy = signal.type === "buy";
  
  return (
    <div className="group relative overflow-hidden rounded-xl border border-white/5 bg-card/30 p-5 transition-all hover:bg-card/50 hover:border-white/10">
      <div className={cn(
        "absolute left-0 top-0 h-full w-1",
        isBuy ? "bg-green-500" : "bg-red-500"
      )} />
      
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-white/5 px-3 py-1.5 font-mono text-sm font-bold text-foreground ring-1 ring-white/10">
            {signal.symbol}
          </div>
          <span className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium uppercase tracking-wider",
            isBuy 
              ? "bg-green-500/10 text-green-500" 
              : "bg-red-500/10 text-red-500"
          )}>
            {signal.type}
          </span>
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {signal.timestamp && formatDistanceToNow(new Date(signal.timestamp), { addSuffix: true })}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-background/50 p-2">
          <p className="text-[10px] uppercase text-muted-foreground">Entry</p>
          <p className="font-mono text-sm font-semibold">{signal.entry}</p>
        </div>
        <div className="rounded-lg bg-background/50 p-2">
          <p className="text-[10px] uppercase text-muted-foreground flex items-center justify-center gap-1">
            <Target className="h-3 w-3" /> Target
          </p>
          <p className="font-mono text-sm font-semibold text-green-500">{signal.exit}</p>
        </div>
        <div className="rounded-lg bg-background/50 p-2">
          <p className="text-[10px] uppercase text-muted-foreground flex items-center justify-center gap-1">
            <ShieldAlert className="h-3 w-3" /> Stop
          </p>
          <p className="font-mono text-sm font-semibold text-red-500">{signal.stopLoss}</p>
        </div>
      </div>

      {signal.reason && (
        <div className="mt-4 border-t border-white/5 pt-3">
          <p className="text-xs text-muted-foreground line-clamp-2">
            <span className="font-semibold text-primary/80">AI Logic: </span>
            {signal.reason}
          </p>
        </div>
      )}
    </div>
  );
}
