import { useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import type { Store } from '../lib/store';
import { KIND_LABEL, formatDateTime, lastReport, ncrpCategory } from '../lib/utils';
import { Empty, PageHeader, Panel } from '../components/Layout';
import { VerdictBadge } from './LiveChats';

async function download(caseId: string, ext: 'csv' | 'pdf'): Promise<string> {
  const r = await fetch(`/api/v1/cases/${caseId}/export.${ext}`);
  if (!r.ok) throw new Error('export failed ' + r.status);
  const hash = r.headers.get('X-SHA256') || '';
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${caseId}.${ext}`;
  a.click();
  URL.revokeObjectURL(url);
  return hash;
}

export const Cases = ({ store, selected, select }: { store: Store; selected: string | null; select: (id: string) => void }) => {
  const list = useMemo(() => Object.values(store.cases).sort((a, b) => b.case.updated_at.localeCompare(a.case.updated_at)), [store.cases]);
  const [hashes, setHashes] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const cd = (selected && store.cases[selected]) || list[0];
  const report = cd ? lastReport(cd) : null;
  const network = cd ? store.networks.find((n) => n.case_ids.includes(cd.case.id)) : undefined;
  const run = async (ext: 'csv' | 'pdf') => {
    if (!cd) return;
    setError('');
    try {
      const h = await download(cd.case.id, ext);
      setHashes((s) => ({ ...s, [cd.case.id + ext]: h }));
    } catch (e: any) {
      setError(String(e.message || e));
    }
  };
  return (
    <div>
      <PageHeader title="Cases and Export" subtitle="Case files, reports and evidence packs (CSV and PDF with SHA-256) for 1930 / NCRP." connected={store.connected} />
      {list.length === 0 ? <Panel><Empty /></Panel> : (
        <div className="grid grid-cols-12 gap-6">
          <Panel title="Cases" className="col-span-12 lg:col-span-4">
            <div className="space-y-2 max-h-[640px] overflow-y-auto">
              {list.map((c) => (
                <button key={c.case.id} onClick={() => select(c.case.id)} className={`w-full text-left p-3 rounded-lg border text-sm ${cd?.case.id === c.case.id ? 'bg-blue-50 border-blue-200' : 'bg-slate-50 border-slate-100 hover:bg-slate-100'}`}>
                  <div className="flex justify-between items-center"><span className="font-mono text-xs">{c.case.id}</span><VerdictBadge cd={c} /></div>
                  <div className="text-xs text-slate-400 mt-1">{c.case.channel}, {c.case.status}, {formatDateTime(c.case.updated_at)}</div>
                </button>
              ))}
            </div>
          </Panel>
          {cd && (
            <div className="col-span-12 lg:col-span-8 space-y-6">
              <Panel title={'Case ' + cd.case.id} right={<VerdictBadge cd={cd} />}>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div><p className="text-xs text-slate-400">Channel</p><p>{cd.case.channel} ({cd.case.external_id})</p></div>
                  <div><p className="text-xs text-slate-400">Status</p><p>{cd.case.status}</p></div>
                  <div><p className="text-xs text-slate-400">Scam type</p><p>{cd.case.scam_type}</p></div>
                  <div><p className="text-xs text-slate-400">NCRP category (suggested)</p><p>{ncrpCategory(cd.case.scam_type)}</p></div>
                  <div><p className="text-xs text-slate-400">Scammer network</p><p className="font-mono">{network ? network.network_id + ' (' + network.case_ids.length + ' cases)' : 'none'}</p></div>
                  <div><p className="text-xs text-slate-400">Messages</p><p>{cd.messages.length}</p></div>
                </div>
                <p className="text-sm text-slate-600 mt-4"><b>Summary:</b> {cd.case.summary || 'No summary yet'}</p>
              </Panel>
              <Panel title="Case Report">
                {report ? (
                  <div className="text-sm text-slate-600 space-y-2">
                    <p className="font-semibold text-slate-800">{report.summary}</p>
                    <p>{report.modus_operandi}</p>
                    {Array.isArray(report.key_points) && <ul className="list-disc pl-5">{report.key_points.map((k: string) => <li key={k}>{k}</li>)}</ul>}
                    <p className="text-xs text-slate-400">Risk: {report.risk}. Recommended: {report.recommended_action}</p>
                  </div>
                ) : <p className="text-sm text-slate-400">The report is written when the case closes.</p>}
              </Panel>
              <Panel title="Intel">
                {cd.intel.length === 0 ? <Empty text="No intel yet" /> : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {cd.intel.map((i) => (
                      <div key={i.kind + i.value} className="flex justify-between gap-2 p-2 rounded-lg bg-slate-50 border border-slate-100 text-sm">
                        <span className="text-xs font-bold uppercase text-slate-400">{KIND_LABEL[i.kind] || i.kind}</span>
                        <span className="font-mono break-all text-right">{i.value}</span>
                      </div>
                    ))}
                  </div>
                )}
              </Panel>
              <Panel title="Export">
                <div className="flex gap-3 mb-4">
                  <button onClick={() => run('csv')} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700"><Download size={16} /> CSV</button>
                  <button onClick={() => run('pdf')} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-charcoal text-white text-sm font-semibold hover:bg-black"><Download size={16} /> PDF</button>
                </div>
                {error && <p className="text-sm text-red-600 mb-2">{error}</p>}
                {(['csv', 'pdf'] as const).map((ext) => hashes[cd.case.id + ext] ? (
                  <p key={ext} className="text-xs font-mono text-slate-600 break-all">{ext.toUpperCase()} SHA-256: {hashes[cd.case.id + ext]}</p>
                ) : null)}
                {cd.evidence.length > 0 && (
                  <div className="mt-3 space-y-1">
                    <p className="text-xs text-slate-400">Recorded evidence</p>
                    {cd.evidence.map((e, i) => <p key={i} className="text-xs font-mono text-slate-500 break-all">{e.kind}: {e.sha256} ({formatDateTime(e.created_at)})</p>)}
                  </div>
                )}
              </Panel>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
