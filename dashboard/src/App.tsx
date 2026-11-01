import { useEffect, useState } from 'react';
import { Layout, NAV } from './components/Layout';
import { useStore } from './lib/store';
import { Overview } from './pages/Overview';
import { LiveChats } from './pages/LiveChats';
import { Calls } from './pages/Calls';
import { Intelligence } from './pages/Intelligence';
import { Networks } from './pages/Networks';
import { Cases } from './pages/Cases';
import { System } from './pages/System';

const ALIASES: Record<string, string> = { '/overview': '/', '/export': '/cases' };

function currentPath() {
  const p = window.location.pathname.replace(/\/+$/, '') || '/';
  const path = ALIASES[p] || p;
  return NAV.some((n) => n.path === path) ? path : '/';
}

export default function App() {
  const store = useStore();
  const [path, setPath] = useState(currentPath());
  const [selectedCase, setSelectedCase] = useState<string | null>(new URLSearchParams(window.location.search).get('case'));
  useEffect(() => {
    const onPop = () => setPath(currentPath());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const navigate = (p: string) => {
    window.history.pushState(null, '', p);
    setPath(p);
  };
  const openCase = (id: string) => {
    setSelectedCase(id);
    window.history.pushState(null, '', '/cases?case=' + id);
    setPath('/cases');
  };
  return (
    <Layout path={path} navigate={navigate} connected={store.connected}>
      {path === '/' && <Overview store={store} />}
      {path === '/chats' && <LiveChats store={store} />}
      {path === '/calls' && <Calls store={store} />}
      {path === '/intel' && <Intelligence store={store} />}
      {path === '/networks' && <Networks store={store} openCase={openCase} />}
      {path === '/cases' && <Cases store={store} selected={selectedCase} select={setSelectedCase} />}
      {path === '/system' && <System store={store} />}
    </Layout>
  );
}
