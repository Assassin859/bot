import { useSettings, useUpdateSetting } from "@/hooks/use-dashboard";
import { Settings as SettingsIcon, Shield, Key, Sliders, Bell } from "lucide-react";
import { cn } from "@/lib/utils";

export default function Settings() {
  const { data: settings, isLoading } = useSettings();
  const { mutate: updateSetting, isPending } = useUpdateSetting();

  // Helper to get value
  const getValue = (key: string) => settings?.find(s => s.key === key)?.value || "";

  return (
    <div className="p-4 md:p-8 space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-display font-bold text-gradient">Configuration</h1>
          <p className="text-muted-foreground mt-1">Adjust bot parameters and API keys.</p>
        </div>
        <div className="p-3 bg-card/50 rounded-xl border border-white/5">
          <SettingsIcon className="w-6 h-6 text-primary" />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Risk Management */}
        <div className="rounded-2xl border border-white/5 bg-card/50 p-6 backdrop-blur-xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <Shield className="w-5 h-5" />
            </div>
            <h3 className="font-semibold text-lg">Risk Management</h3>
          </div>
          
          <div className="space-y-6">
            <div>
              <label className="text-sm font-medium text-muted-foreground mb-2 block">Risk Level</label>
              <div className="grid grid-cols-3 gap-3">
                {['low', 'medium', 'high'].map((level) => (
                  <button
                    key={level}
                    onClick={() => updateSetting({ key: 'risk_level', value: level })}
                    className={cn(
                      "px-4 py-2 rounded-lg text-sm font-semibold capitalize transition-all border",
                      getValue('risk_level') === level
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-white/5 text-muted-foreground border-transparent hover:bg-white/10"
                    )}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground mb-2 block">Max Position Size (%)</label>
              <input 
                type="number"
                placeholder="e.g. 10"
                className="w-full bg-background/50 border border-white/10 rounded-lg px-4 py-2 text-foreground focus:outline-none focus:border-primary/50 transition-colors"
              />
            </div>
          </div>
        </div>

        {/* API Configuration */}
        <div className="rounded-2xl border border-white/5 bg-card/50 p-6 backdrop-blur-xl opacity-75">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-accent/10 rounded-lg text-accent">
              <Key className="w-5 h-5" />
            </div>
            <h3 className="font-semibold text-lg">API Configuration</h3>
          </div>
          
          <div className="space-y-4">
            <div className="p-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-xs text-yellow-500 mb-4">
              API Keys are managed via Environment Variables for security.
            </div>
            
            <div>
              <label className="text-sm font-medium text-muted-foreground mb-2 block">Binance API Key</label>
              <input 
                type="password"
                value="************************"
                disabled
                className="w-full bg-background/50 border border-white/5 rounded-lg px-4 py-2 text-muted-foreground cursor-not-allowed"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground mb-2 block">CryptoPanic API Key</label>
              <input 
                type="password"
                value="************************"
                disabled
                className="w-full bg-background/50 border border-white/5 rounded-lg px-4 py-2 text-muted-foreground cursor-not-allowed"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
