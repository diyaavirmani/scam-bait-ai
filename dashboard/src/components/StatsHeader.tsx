import { ShieldCheck, Timer, Fingerprint, MessagesSquare } from 'lucide-react';

interface Props { scams: number; minutesWasted: number; intelItems: number; activeChats: number; }

const Tile = ({ icon: Icon, value, label, tone }: any) => (
  <div className="flex-1 bg-white rounded-xl p-6 flex items-center gap-6 shadow-sm border border-slate-200">
    <div className={`p-4 rounded-xl ${tone}`}><Icon size={28} /></div>
    <div>
      <h2 className="text-3xl font-bold text-slate-900">{value}</h2>
      <p className="text-sm font-medium text-slate-500">{label}</p>
    </div>
  </div>
);

export const StatsHeader = ({ scams, minutesWasted, intelItems, activeChats }: Props) => (
  <div className="flex flex-col md:flex-row gap-4 mb-6">
    <Tile icon={ShieldCheck} value={scams} label="Scams Intercepted" tone="bg-blue-50 text-blue-600" />
    <Tile icon={Timer} value={minutesWasted} label="Scammer Minutes Wasted" tone="bg-purple-50 text-purple-600" />
    <Tile icon={Fingerprint} value={intelItems} label="Intel Items Extracted" tone="bg-mint-50 text-mint-600" />
    <Tile icon={MessagesSquare} value={activeChats} label="Active Engagements" tone="bg-pastelRed-50 text-pastelRed-500" />
  </div>
);
