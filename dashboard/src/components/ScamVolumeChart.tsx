import { AreaChart, Area, ResponsiveContainer, YAxis, XAxis, Tooltip } from 'recharts';

export interface ChartPoint { name: string; messages: number; }

export const ScamVolumeChart = ({ data }: { data: ChartPoint[] }) => (
  <div className="w-full h-full relative min-h-[260px]">
    <p className="text-xs font-mono text-gray-400 mb-2">SCAMMER MESSAGES PER MINUTE, LAST 60 MINUTES (IST)</p>
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="colorMsg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }} interval={9} />
        <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: '#94a3b8' }} width={28} />
        <Tooltip />
        <Area type="monotone" dataKey="messages" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorMsg)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  </div>
);
