import { Link, useLocation } from "wouter";
import { 
  LayoutDashboard, 
  Wallet, 
  Settings, 
  Bot,
  Activity,
  LineChart
} from "lucide-react";
import { cn } from "@/lib/utils";

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Portfolio', href: '/portfolio', icon: Wallet },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Sidebar() {
  const [location] = useLocation();

  return (
    <div className="flex h-screen w-20 flex-col items-center border-r border-border bg-card/30 backdrop-blur-xl lg:w-64 lg:items-stretch">
      <div className="flex h-16 items-center justify-center border-b border-border lg:justify-start lg:px-6">
        <Bot className="h-8 w-8 text-primary" />
        <span className="ml-3 hidden text-lg font-bold tracking-tight text-foreground lg:block">
          CryptoBot<span className="text-primary">.ai</span>
        </span>
      </div>
      
      <div className="flex flex-1 flex-col gap-4 p-4">
        <nav className="flex flex-col gap-2">
          {navigation.map((item) => {
            const isActive = location === item.href;
            return (
              <Link key={item.name} href={item.href}>
                <div
                  className={cn(
                    "group flex cursor-pointer items-center rounded-xl px-3 py-3 transition-all duration-200",
                    isActive 
                      ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20" 
                      : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
                  )}
                >
                  <item.icon className={cn("h-6 w-6 shrink-0", isActive ? "stroke-2" : "stroke-1.5")} />
                  <span className={cn("ml-3 hidden font-medium lg:block", isActive && "font-semibold")}>
                    {item.name}
                  </span>
                  {isActive && (
                    <div className="ml-auto hidden h-2 w-2 rounded-full bg-white/30 lg:block" />
                  )}
                </div>
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto hidden rounded-xl bg-gradient-to-br from-primary/10 to-transparent p-4 lg:block border border-primary/20">
          <div className="flex items-center gap-2 text-sm font-medium text-primary">
            <Activity className="h-4 w-4" />
            <span>System Status</span>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
            </span>
            <span className="text-xs text-muted-foreground">Operational</span>
          </div>
        </div>
      </div>
    </div>
  );
}
