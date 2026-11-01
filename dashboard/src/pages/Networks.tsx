import { Network as NetIcon } from 'lucide-react';
import type { Store } from '../lib/store';
import { KIND_LABEL, formatDateTime, mask } from '../lib/utils';
import { Empty, PageHeader, Panel } from '../components/Layout';

export const Networks = ({ store, openCase }: { store: Store; openCase: (id: string) => void }) => (
  <div>
    <PageHeader title="Scammer Networks" subtitle="Cases linked by an identical UPI ID, phone, account, link or wallet (exact match only)." connected={store.connected} />
    {store.networks.length === 0 ? <Panel><Empty text="No shared identifiers between cases yet" /></Panel> : (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {store.networks.map((n) => (
          <div key={n.network_id} className={`bg-white rounded-[24px] p-6 shadow-soft border border-slate-200 ${store.flashNetwork === n.network_id ? 'flash' : ''}`}>
            <div className="flex justify-between items-start mb-4">
              <div className="p-3 rounded-2xl bg-purple-50 text-purple-600"><NetIcon size={22} /></div>
              <span className="text-xs font-bold px-2 py-1 bg-gray-50 rounded-lg text-slate-600">{n.case_ids.length} cases</span>
            </div>
            <h3 className="font-mono text-sm text-charcoal mb-1">{n.network_id}</h3>
            <p className="text-xs text-gray-400 mb-4">{(n.scam_types || []).join(', ') || 'scam type not set'}{n.last_seen ? ', last seen ' + formatDateTime(n.last_seen) : ''}</p>
            <div className="space-y-1 mb-4">
              {n.shared.map((s) => (
                <div key={s.field + s.value} className="flex justify-between text-sm p-2 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="text-xs font-bold uppercase text-slate-400">{KIND_LABEL[s.field] || s.field}</span>
                  <span className="font-mono">{mask(s.value)}</span>
                  <span className="text-xs text-slate-500">{s.case_count} cases</span>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              {n.case_ids.map((id) => (
                <button key={id} onClick={() => openCase(id)} className="text-xs font-mono px-2 py-1 rounded bg-blue-50 text-blue-700 hover:bg-blue-100">{id}</button>
              ))}
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);
