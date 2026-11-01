import { useMemo, useState } from 'react';
import type { Store } from '../lib/store';
import type { CaseData } from '../lib/types';
import { deciderLabel, detections, formatTime, pct, personaMeta, seconds } from '../lib/utils';
import { Empty, PageHeader, Panel } from '../components/Layout';
import { LiveFeed } from '../components/LiveFeed';
import { IntelCard } from '../components/IntelCard';

export const VerdictBadge = ({ cd }: { cd: CaseData }) => {
  const v = cd.case.verdict;
  const tone = v === 'scam' ? 'bg-red-50 text-red-700 border-red-200' : v === 'not_scam' ? 'bg-green-50 text-green-700 border-green-200' : 'bg-slate-50 text-slate-500 border-slate-200';
  return <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${tone}`}>{v === 'not_scam' ? 'not scam' : v}</span>;
};

export const DetectionPanel = ({ cd }: { cd: CaseData }) => {
  const rows = detections(cd);
  const decisionsDown = rows.some((e) => e.data?.decisions_available === false);
  return (
    <Panel title="Detection" right={decisionsDown ? <span className="text-xs font-semibold px-2 py-1 rounded bg-yellow-50 text-yellow-700 border border-yellow-200">Decisions unavailable</span> : undefined}>
      {rows.length === 0 ? <Empty text="No verdict yet" /> : (
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {rows.slice(-8).map((e, i) => (
            <div key={(e.id ?? i) + ''} className="grid grid-cols-12 gap-2 items-center text-sm p-2 rounded-lg bg-slate-50 border border-slate-100">
              <span className="col-span-2 text-xs font-bold uppercase text-slate-500">{e.data.recheck ? 'recheck' : e.data.stage}</span>
              <span className="col-span-3">qwen <b>{pct(e.data.p_cerebras)}</b></span>
              <span className="col-span-3">Decisions <b>{pct(e.data.p_decisions)}</b></span>
              <span className={`col-span-2 font-bold ${e.data.verdict === 'scam' ? 'text-red-600' : e.data.verdict === 'not_scam' ? 'text-green-600' : 'text-slate-500'}`}>{e.data.verdict}</span>
              <span className="col-span-2 text-[11px] text-slate-500">{deciderLabel(e.data.decided_by)}</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
};

export const SpeedPanel = ({ store }: { store: Store }) => {
  const steps = Object.values(store.speed);
  const limits = Object.values(store.ratelimit);
  return (
    <Panel title="Cerebras Speed Meter">
      {steps.length === 0 ? <Empty text="No model calls yet" /> : (
        <div className="space-y-2">
          {steps.map((s: any) => (
            <div key={s.step} className="flex justify-between text-sm p-2 rounded-lg bg-slate-50 border border-slate-100">
              <span className="font-semibold text-slate-700">{s.step}</span>
              <span className="text-slate-500">{s.provider === 'openai' ? 'OpenAI' : 'Cerebras'} {s.model}</span>
              <span className="font-mono">{seconds(s.ms)}{typeof s.tokens_per_s === 'number' ? ', ' + Math.round(s.tokens_per_s) + ' tok/s' : ''}</span>
            </div>
          ))}
        </div>
      )}
      {limits.length > 0 && (
        <div className="mt-4 space-y-2">
          {limits.map((l: any) => (
            <div key={l.model}>
              <div className="flex justify-between text-xs text-slate-500 mb-1"><span>{l.model}</span><span>{l.rpm_used} of {l.rpm_limit} per min{l.waiting ? ', ' + l.waiting + ' waiting' : ''}</span></div>
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${l.waiting ? 'bg-yellow-400' : 'bg-mint-500'}`} style={{ width: Math.min(100, (100 * l.rpm_used) / Math.max(1, l.rpm_limit)) + '%' }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
};

export const LiveChats = ({ store }: { store: Store }) => {
  const chats = useMemo(() => Object.values(store.cases).filter((c) => c.case.channel !== 'call')
    .sort((a, b) => b.case.updated_at.localeCompare(a.case.updated_at)), [store.cases]);
  const [sel, setSel] = useState<string | null>(null);
  const cd = (sel && store.cases[sel]) || chats[0];
  const meta = cd ? personaMeta(cd) : {};
  const scammerTurns = cd ? cd.messages.filter((m) => m.role === 'scammer').length : 0;
  return (
    <div>
      <PageHeader title="Live Chats" subtitle="Telegram and API conversations, side by side with detection, intel and speed." connected={store.connected} />
      {chats.length === 0 ? <Panel><Empty /></Panel> : (
        <div className="grid grid-cols-12 gap-6">
          <Panel title="Chats" className="col-span-12 lg:col-span-3">
            <div className="space-y-2 max-h-[640px] overflow-y-auto">
              {chats.map((c) => (
                <button key={c.case.id} onClick={() => setSel(c.case.id)} className={`w-full text-left p-3 rounded-lg border text-sm ${cd?.case.id === c.case.id ? 'bg-blue-50 border-blue-200' : 'bg-slate-50 border-slate-100 hover:bg-slate-100'}`}>
                  <div className="flex justify-between items-center"><span className="font-mono text-xs">{c.case.external_id}</span><VerdictBadge cd={c} /></div>
                  <div className="text-xs text-slate-400 mt-1">{c.case.channel}, {formatTime(c.case.updated_at)}</div>
                </button>
              ))}
            </div>
          </Panel>
          {cd && (
            <>
              <Panel title="Transcript" right={<span className="text-xs text-slate-500">{scammerTurns} of 20 scammer messages</span>} className="col-span-12 lg:col-span-5 h-[700px] flex flex-col">
                <div className="flex-1 overflow-hidden"><LiveFeed messages={cd.messages.map((m) => ({ ...m, meta: meta[m.id] }))} limit={200} /></div>
              </Panel>
              <div className="col-span-12 lg:col-span-4 space-y-6">
                <DetectionPanel cd={cd} />
                <Panel title="Rolling Summary"><p className="text-sm text-slate-600">{cd.case.summary || 'No summary yet'}</p></Panel>
                <Panel title="Extracted Intel"><IntelCard items={cd.intel} /></Panel>
                <SpeedPanel store={store} />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
