import { Phone, Building2, Link2, CreditCard, AtSign, Smartphone, Wallet, Hash, User } from 'lucide-react';
import { KIND_LABEL } from '../lib/utils';
import type { Intel } from '../lib/types';
import { Empty } from './Layout';

const ICON: Record<string, any> = {
  phone: Phone, bank_account: Building2, ifsc: Building2, upi: CreditCard, card: CreditCard, email: AtSign,
  url: Link2, apk: Smartphone, crypto_wallet: Wallet, name: User, organisation: User,
};

export const IntelCard = ({ items, max = 50 }: { items: Intel[]; max?: number }) => (
  <div className="flex flex-col gap-2 overflow-y-auto pr-2 max-h-[420px]">
    {items.length === 0 ? <Empty /> : items.slice(-max).reverse().map((item, idx) => {
      const Icon = ICON[item.kind] || Hash;
      return (
        <div key={item.kind + item.value + idx} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-100 hover:bg-slate-100 transition-colors">
          <div className="text-blue-500 bg-blue-50 p-1.5 rounded-md"><Icon size={12} /></div>
          <span className="text-sm font-medium text-slate-700 font-mono break-all">{item.value}</span>
          <span className="ml-auto text-[10px] uppercase font-bold text-slate-400 bg-white px-1.5 py-0.5 rounded border border-slate-200 whitespace-nowrap">
            {KIND_LABEL[item.kind] || item.kind}
          </span>
        </div>
      );
    })}
  </div>
);
