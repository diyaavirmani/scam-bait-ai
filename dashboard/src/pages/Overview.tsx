import { useMemo } from 'react';
import type { Store } from '../lib/store';
import { personaMeta } from '../lib/utils';
import { PageHeader, Panel } from '../components/Layout';
import { StatsHeader } from '../components/StatsHeader';
import { ScamVolumeChart } from '../components/ScamVolumeChart';
import { IntelCard } from '../components/IntelCard';
import { LiveFeed, type FeedMsg } from '../components/LiveFeed';

export const Overview = ({ store }: { store: Store }) => {
  const all = Object.values(store.cases);
  const stats = useMemo(() => {
    const scamCases = all.filter((c) => c.case.verdict === 'scam');
    let minutes = 0;
    for (const c of scamCases) {
      const ts = c.messages.map((m) => new Date(m.ts).getTime()).filter((t) => !isNaN(t));
      if (ts.length > 1) minutes += (Math.max(...ts) - Math.min(...ts)) / 60000;
    }
    return {
      scams: scamCases.length,
      minutes: Math.round(minutes),
      intel: all.reduce((n, c) => n + c.intel.length, 0),
      active: all.filter((c) => c.case.status === 'engaged').length,
    };
  }, [all]);
  const chart = useMemo(() => {
    const now = Date.now();
    const buckets = Array.from({ length: 60 }, (_, i) => {
      const t = new Date(now - (59 - i) * 60000);
      return { name: t.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false }), messages: 0 };
    });
    for (const c of all) for (const m of c.messages) {
      if (m.role !== 'scammer') continue;
      const age = Math.floor((now - new Date(m.ts).getTime()) / 60000);
      if (age >= 0 && age < 60) buckets[59 - age].messages += 1;
    }
    return buckets;
  }, [all]);
  const feed: FeedMsg[] = useMemo(() => {
    const out: FeedMsg[] = [];
    for (const c of all) {
      const meta = personaMeta(c);
      for (const m of c.messages) out.push({ ...m, meta: meta[m.id] });
    }
    return out.sort((a, b) => a.ts.localeCompare(b.ts));
  }, [all]);
  const intel = useMemo(() => all.flatMap((c) => c.intel).sort((a, b) => (a.first_seen || '').localeCompare(b.first_seen || '')), [all]);

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard Overview" subtitle="Real-time scam detection and intelligence monitoring." connected={store.connected} />
      <StatsHeader scams={stats.scams} minutesWasted={stats.minutes} intelItems={stats.intel} activeChats={stats.active} />
      <div className="grid grid-cols-12 gap-6">
        <Panel title="Scam Volume Trends" className="col-span-12 lg:col-span-8">
          <ScamVolumeChart data={chart} />
        </Panel>
        <Panel title="Live Intelligence" className="col-span-12 lg:col-span-4">
          <IntelCard items={intel} max={8} />
        </Panel>
        <Panel title="Live Feed" right={<span className="text-xs text-slate-400 font-mono">Real-time</span>} className="col-span-12 h-[420px] flex flex-col">
          <div className="flex-1 overflow-hidden"><LiveFeed messages={feed} /></div>
        </Panel>
      </div>
    </div>
  );
};
