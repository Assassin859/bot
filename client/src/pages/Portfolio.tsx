import { usePortfolio } from "@/hooks/use-dashboard";
import { Wallet, PieChart } from "lucide-react";
import { Cell, Pie, PieChart as RechartsPie, ResponsiveContainer, Tooltip } from "recharts";

export default function Portfolio() {
  const { data: portfolio, isLoading } = usePortfolio();

  // Prepare data for pie chart (filtering out tiny balances)
  const chartData = portfolio?.filter(item => item.total > 0).map(item => ({
    name: item.asset,
    value: parseFloat(item.total.toString()) // Mock value, in real app total is quantity, need price
  })) || [];

  const COLORS = ['#10B981', '#8B5CF6', '#3B82F6', '#F59E0B', '#EF4444'];

  return (
    <div className="p-4 md:p-8 space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-display font-bold text-gradient">Portfolio</h1>
          <p className="text-muted-foreground mt-1">Manage your assets and allocation.</p>
        </div>
        <div className="p-3 bg-card/50 rounded-xl border border-white/5">
          <Wallet className="w-6 h-6 text-primary" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Asset Allocation Chart */}
        <div className="lg:col-span-1 rounded-2xl border border-white/5 bg-card/50 p-6 backdrop-blur-xl flex flex-col items-center justify-center min-h-[300px]">
          <h3 className="w-full font-semibold text-lg mb-4 flex items-center gap-2">
            <PieChart className="w-5 h-5 text-accent" />
            Allocation
          </h3>
          <div className="h-[250px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsPie>
                <Pie
                  data={chartData}
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {chartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff' }}
                />
              </RechartsPie>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-2 justify-center mt-4">
            {chartData.map((entry, index) => (
              <div key={entry.name} className="flex items-center gap-1 text-xs text-muted-foreground">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                {entry.name}
              </div>
            ))}
          </div>
        </div>

        {/* Assets Table */}
        <div className="lg:col-span-2 rounded-2xl border border-white/5 bg-card/50 p-6 backdrop-blur-xl">
          <h3 className="font-semibold text-lg mb-6">Asset Balances</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-muted-foreground uppercase text-xs border-b border-white/5">
                <tr>
                  <th className="px-4 py-3 font-medium">Asset</th>
                  <th className="px-4 py-3 font-medium text-right">Available</th>
                  <th className="px-4 py-3 font-medium text-right">In Orders (Locked)</th>
                  <th className="px-4 py-3 font-medium text-right">Total Balance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {isLoading ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">Loading assets...</td>
                  </tr>
                ) : portfolio?.map((asset) => (
                  <tr key={asset.asset} className="hover:bg-white/5 transition-colors">
                    <td className="px-4 py-4 font-bold">{asset.asset}</td>
                    <td className="px-4 py-4 text-right font-mono text-muted-foreground">{asset.free}</td>
                    <td className="px-4 py-4 text-right font-mono text-muted-foreground">{asset.locked}</td>
                    <td className="px-4 py-4 text-right font-mono font-semibold text-foreground">{asset.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
