import { useEffect } from 'react';
import { Database, Cpu, BrainCircuit, Radio } from 'lucide-react';
import type { Store } from '../lib/store';
import { PageHeader } from '../components/Layout';
import { SpeedPanel } from './LiveChats';

const StatusCard = ({ icon: Icon, label, ok, value, subtext }: any) => (
  <div className="bg-white rounded-[24px] p-6 shadow-soft border border-slate-200">
    <div className="flex justify-between items-start mb-4">
      <div className={`p-3 rounded-2xl ${ok ? 'bg-mint-50 text-mint-600' : 'bg-pastelRed-50 text-pastelRed-500'}`}><Icon size={24} /></div>
      <div className={`text-xs font-bold px-2 py-1 rounded-lg ${ok ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>{ok ? 'Healthy' : 'Down'}</div>
    </div>
    <h3 className="text-xl font-bold text-charcoal mb-1 break-words">{value}</h3>
    <p className="text-sm font-medium text-gray-400">{label}</p>
    {subtext && <p className="text-xs text-gray-400 mt-4 pt-4 border-t border-gray-50 break-words">{subtext}</p>}
  </div>
);

export const System = ({ store }: { store: Store }) => {
  useEffect(() => {
    store.refreshHealth();
    const t = window.setInterval(store.refreshHealth, 15000);
    return () => window.clearInterval(t);
  }, []);
  const h = store.health;
  return (
    <div>
      <PageHeader title="System Health" subtitle="Live checks from GET /health, refreshed every 15 seconds." connected={store.connected} />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatusCard icon={Database} label="Database (SQLite)" ok={!!h?.checks.database} value={h ? (h.checks.database ? 'Connected' : 'Unreachable') : 'No answer'} />
        <StatusCard icon={Cpu} label="Cerebras models" ok={!!h?.checks.models.ok} value={h?.checks.models.models?.join(', ') || 'Not verified'} subtext={h?.checks.models.detail} />
        <StatusCard icon={BrainCircuit} label="OpenAI Decisions" ok={!!h?.checks.decisions.available} value={h ? (h.checks.decisions.available ? 'Available' : 'Decisions unavailable') : 'No answer'} subtext={h?.checks.decisions.reason || undefined} />
        <StatusCard icon={Radio} label="Live event stream (SSE)" ok={store.connected} value={store.connected ? 'Connected' : 'Reconnecting'} />
      </div>
      <SpeedPanel store={store} />
    </div>
  );
};
