import { useMemo, useState } from 'react';
import { PhoneCall } from 'lucide-react';
import type { Store } from '../lib/store';
import { formatTime, lastReport } from '../lib/utils';
import { Empty, PageHeader, Panel } from '../components/Layout';
import { IntelCard } from '../components/IntelCard';
import { DetectionPanel } from './LiveChats';

export const Calls = ({ store }: { store: Store }) => {
  const calls = useMemo(() => Object.values(store.cases).filter((c) => c.case.channel === 'call')
    .sort((a, b) => b.case.updated_at.localeCompare(a.case.updated_at)), [store.cases]);
  const [sel, setSel] = useState<string | null>(null);
  const cd = (sel && store.cases[sel]) || calls[0];
  const statusEv = cd ? [...cd.events].reverse().find((e) => e.type === 'call.status') : undefined;
  const lines = cd ? cd.events.filter((e) => e.type === 'transcript.final') : [];
  const report = cd ? lastReport(cd) : null;
  return (
    <div>
      <PageHeader title="Calls" subtitle="Live Twilio calls answered by the GPT-Live persona." connected={store.connected} />
      {calls.length === 0 ? <Panel><Empty text="Waiting for the first scam call" /></Panel> : cd && (
        <div className="flex flex-col lg:flex-row gap-6">
          <div className="flex-1 flex flex-col gap-6">
            <div className="bg-gradient-to-br from-charcoal to-black rounded-[32px] p-8 text-white shadow-lg relative overflow-hidden flex flex-col items-center justify-center min-h-[300px]">
              <div className="w-24 h-24 bg-white/10 rounded-full mb-6 flex items-center justify-center border border-white/10 relative">
                <PhoneCall size={32} />
                {statusEv?.data?.status === 'live' && <div className="absolute inset-0 rounded-full border border-mint-500 animate-ping opacity-20" />}
              </div>
              <h2 className="text-2xl font-bold mb-2">{statusEv?.data?.from_masked || 'Caller'}</h2>
              <p className="text-gray-400">Status: {statusEv?.data?.status || 'unknown'}{statusEv ? ', ' + formatTime(statusEv.ts) : ''}</p>
              <p className="text-gray-500 text-xs font-mono mt-2">{statusEv?.data?.call_sid || cd.case.external_id}</p>
            </div>
            <Panel title="Calls">
              <div className="space-y-2">
                {calls.map((c) => (
                  <button key={c.case.id} onClick={() => setSel(c.case.id)} className={`w-full text-left p-3 rounded-lg border text-sm ${cd.case.id === c.case.id ? 'bg-blue-50 border-blue-200' : 'bg-slate-50 border-slate-100'}`}>
                    <span className="font-mono text-xs">{c.case.external_id}</span> <span className="text-xs text-slate-400">{formatTime(c.case.updated_at)}</span>
                  </button>
                ))}
              </div>
            </Panel>
          </div>
          <div className="w-full lg:w-[460px] flex flex-col gap-6">
            <Panel title="Live Transcript" className="max-h-[520px] overflow-y-auto">
              {lines.length === 0 && !cd.partial.caller && !cd.partial.persona ? <Empty text="Waiting for the caller to speak" /> : (
                <div className="space-y-2">
                  {lines.map((e, i) => (
                    <div key={(e.id ?? i) + ''} className={`p-3 rounded-xl text-sm ${e.data.speaker === 'caller' ? 'bg-red-50 border border-red-100' : 'bg-blue-50 border border-blue-100'}`}>
                      <p className="text-xs font-semibold opacity-70 mb-1">{e.data.speaker === 'caller' ? 'Caller' : 'Meena (GPT-Live)'}, {formatTime(e.ts)}</p>
                      <p>{e.data.text}</p>
                    </div>
                  ))}
                  {['caller', 'persona'].map((s) => cd.partial[s] ? <p key={s} className="text-sm italic text-slate-400">{s === 'caller' ? 'Caller' : 'Meena'}: {cd.partial[s]}</p> : null)}
                </div>
              )}
            </Panel>
            <DetectionPanel cd={cd} />
            <Panel title="Extracted Intel"><IntelCard items={cd.intel} /></Panel>
            <Panel title="End-of-Call Report">
              {report ? (
                <div className="text-sm text-slate-600 space-y-2">
                  <p className="font-semibold text-slate-800">{report.summary}</p>
                  <p>{report.modus_operandi}</p>
                  <p className="text-xs text-slate-400">Risk: {report.risk}</p>
                </div>
              ) : <p className="text-sm text-slate-400">{cd.case.summary || 'The report appears when the call ends.'}</p>}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
};
