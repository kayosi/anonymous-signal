'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area
} from 'recharts';
import {
  Shield, AlertTriangle, TrendingUp, Bell,
  MessageSquare, Send, RefreshCw,
  Activity, Zap, LogOut, CheckCircle,
  FileText, Clock, AlertOctagon,
  BarChart2, Layers
} from 'lucide-react';
import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
const POLL_INTERVAL_MS = 30000;

const api = axios.create({ baseURL: API_BASE });
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('analyst_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('analyst_token');
      localStorage.removeItem('analyst_role');
      window.location.reload();
    }
    return Promise.reject(err);
  }
);

const CATEGORY_COLORS: Record<string, string> = {
  terrorism:           '#DC2626',
  corruption:          '#F59E0B',
  crime_signals:       '#EF4444',
  public_safety:       '#3B82F6',
  health_sanitation:   '#10B981',
  environmental_risks: '#22C55E',
  infrastructure:      '#8B5CF6',
  service_delivery:    '#6B7280',
  other:               '#9CA3AF',
};

const URGENCY_COLORS: Record<string, string> = {
  critical: '#DC2626',
  high:     '#F97316',
  medium:   '#F59E0B',
  low:      '#10B981',
};

interface DashboardStats {
  total_reports: number;
  pending_reports: number;
  high_urgency_reports: number;
  active_clusters: number;
  unacknowledged_alerts: number;
  reports_last_24h: number;
  reports_last_7d: number;
  category_breakdown: Array<{ category: string; count: number; avg_severity: number | null }>;
  recent_trends: Record<string, number>;
  urgency_breakdown: Record<string, number>;
}

interface AlertItem {
  id: string;
  alert_type: string;
  category: string;
  title: string;
  description: string;
  severity_level: string;
  report_count: number;
  time_window_hours: number;
  created_at: string;
  acknowledged: boolean;
  resolved: boolean;
}

interface Cluster {
  id: string;
  category: string;
  label: string;
  report_count: number;
  last_updated: string;
  escalation_flag: boolean;
  is_active: boolean;
  notes?: string;
}

interface IntelligenceSummary {
  window_hours: number;
  total_reports_in_window: number;
  critical_high_count: number;
  new_clusters_detected: number;
  surging_clusters: string[];
  insights: string[];
  top_risk_categories: Array<{ category: string; count: number; avg_severity: number }>;
  generated_at: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

type Tab = 'overview' | 'reports' | 'clusters' | 'alerts' | 'intelligence' | 'chat';
type Role = 'analyst' | 'senior_analyst' | 'admin';

// Custom XAxis tick — avoids TypeScript error with angle/textAnchor on tick prop
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const AngledTick = (props: any) => {
  const { x, y, payload } = props;
  return (
    <g transform={`translate(${x},${y})`}>
      <text x={0} y={0} dy={14} textAnchor="end" fill="#94a3b8" fontSize={10} transform="rotate(-25)">
        {payload.value}
      </text>
    </g>
  );
};

function LoginScreen({ onLogin }: { onLogin: (token: string, role: string) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await axios.post(`${API_BASE}/auth/login`, { username, password });
      onLogin(res.data.access_token, res.data.role);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg || 'Login failed. Check credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem' }}>
      <div style={{ width: '100%', maxWidth: '400px' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: '64px', height: '64px', background: 'rgba(59,130,246,0.15)', borderRadius: '16px', border: '1px solid rgba(59,130,246,0.3)', marginBottom: '1rem' }}>
            <Shield style={{ width: 32, height: 32, color: '#60a5fa' }} />
          </div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'white', margin: 0 }}>Anonymous Signal</h1>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginTop: '0.25rem' }}>Analyst Intelligence Dashboard</p>
        </div>
        <div style={{ background: '#1e293b', borderRadius: '16px', border: '1px solid #334155', padding: '2rem' }}>
          <form onSubmit={handleLogin}>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, color: '#cbd5e1', marginBottom: '0.5rem' }}>Username</label>
              <input type="text" value={username} onChange={(e) => setUsername(e.target.value)}
                style={{ width: '100%', background: '#334155', border: '1px solid #475569', borderRadius: '12px', padding: '0.75rem 1rem', color: 'white', outline: 'none', boxSizing: 'border-box' }}
                placeholder="analyst" required />
            </div>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.875rem', fontWeight: 500, color: '#cbd5e1', marginBottom: '0.5rem' }}>Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                style={{ width: '100%', background: '#334155', border: '1px solid #475569', borderRadius: '12px', padding: '0.75rem 1rem', color: 'white', outline: 'none', boxSizing: 'border-box' }}
                placeholder="••••••••" required />
            </div>
            {error && <div style={{ background: 'rgba(127,29,29,0.4)', border: '1px solid #991b1b', borderRadius: '12px', padding: '0.75rem', color: '#fca5a5', fontSize: '0.875rem', marginBottom: '1rem' }}>{error}</div>}
            <button type="submit" disabled={loading}
              style={{ width: '100%', background: '#2563eb', border: 'none', borderRadius: '12px', padding: '0.75rem', color: 'white', fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.5 : 1 }}>
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>
          <p style={{ textAlign: 'center', color: '#64748b', fontSize: '0.75rem', marginTop: '1rem' }}>🔒 Secured access — Analyst accounts only</p>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, icon: Icon, color = 'blue', alert = false }: {
  label: string; value: string | number; sub?: string; icon: React.ElementType; color?: string; alert?: boolean;
}) {
  const iconColors: Record<string, string> = {
    blue: '#60a5fa', red: '#f87171', green: '#4ade80', yellow: '#fbbf24', purple: '#c084fc', orange: '#fb923c',
  };
  const iconBgs: Record<string, string> = {
    blue: 'rgba(59,130,246,0.15)', red: 'rgba(239,68,68,0.15)', green: 'rgba(34,197,94,0.15)',
    yellow: 'rgba(245,158,11,0.15)', purple: 'rgba(168,85,247,0.15)', orange: 'rgba(249,115,22,0.15)',
  };
  return (
    <div style={{ background: '#1e293b', borderRadius: '16px', border: `1px solid ${alert ? '#991b1b' : '#334155'}`, padding: '1.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
        <span style={{ color: '#94a3b8', fontSize: '0.875rem', fontWeight: 500 }}>{label}</span>
        <div style={{ width: 36, height: 36, borderRadius: '10px', background: iconBgs[color] || iconBgs.blue, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon style={{ width: 16, height: 16, color: iconColors[color] || iconColors.blue }} />
        </div>
      </div>
      <div style={{ fontSize: '1.875rem', fontWeight: 700, color: 'white' }}>{value}</div>
      {sub && <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.25rem' }}>{sub}</div>}
    </div>
  );
}

function UrgencyBadge({ level }: { level: string }) {
  const styles: Record<string, { background: string; color: string; border: string }> = {
    critical: { background: 'rgba(127,29,29,0.4)', color: '#fca5a5', border: '1px solid #991b1b' },
    high:     { background: 'rgba(124,45,18,0.4)', color: '#fdba74', border: '1px solid #c2410c' },
    medium:   { background: 'rgba(120,53,15,0.4)', color: '#fcd34d', border: '1px solid #b45309' },
    low:      { background: 'rgba(6,78,59,0.4)',   color: '#6ee7b7', border: '1px solid #065f46' },
  };
  const s = styles[level] || styles.low;
  return <span style={{ ...s, fontSize: '0.7rem', fontWeight: 700, padding: '0.15rem 0.5rem', borderRadius: '9999px' }}>{level.toUpperCase()}</span>;
}

function CategoryBadge({ category }: { category: string }) {
  const color = CATEGORY_COLORS[category] || '#9CA3AF';
  return (
    <span style={{ background: color + '22', color, border: `1px solid ${color}55`, fontSize: '0.7rem', fontWeight: 500, padding: '0.15rem 0.5rem', borderRadius: '9999px' }}>
      {category.replace(/_/g, ' ')}
    </span>
  );
}

export default function Dashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<Role>('analyst');
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [intelligence, setIntelligence] = useState<IntelligenceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([{
    role: 'assistant',
    content: "👋 I'm your intelligence analyst assistant. Ask me about report trends, categories, urgency levels, or emerging patterns.\n\nTry: **\"Show me today's surges\"** or **\"Which categories are most urgent?\"**",
    timestamp: new Date(),
  }]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [acknowledging, setAcknowledging] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const t = localStorage.getItem('analyst_token');
      const r = localStorage.getItem('analyst_role') as Role;
      if (t) { setToken(t); setRole(r || 'analyst'); }
      else setLoading(false);
    }
  }, []);

  const handleLogin = (t: string, r: string) => {
    localStorage.setItem('analyst_token', t);
    localStorage.setItem('analyst_role', r);
    setToken(t); setRole(r as Role);
  };

  const handleLogout = () => {
    localStorage.removeItem('analyst_token');
    localStorage.removeItem('analyst_role');
    setToken(null);
  };

  const fetchAll = useCallback(async () => {
    if (!token) return;
    try {
      const [s, a, c] = await Promise.all([
        api.get('/analytics/stats'),
        api.get('/analytics/alerts'),
        api.get('/analytics/clusters'),
      ]);
      setStats(s.data);
      setAlerts(a.data);
      setClusters(c.data);
      setLastRefresh(new Date());
    } catch (err) {
      console.error('Fetch failed:', err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  const fetchIntelligence = useCallback(async () => {
    if (!token || role === 'analyst') return;
    try {
      const res = await api.get('/analytics/intelligence-summary?hours=24');
      setIntelligence(res.data);
    } catch (err) {
      console.error('Intelligence fetch failed:', err);
    }
  }, [token, role]);

  useEffect(() => {
    if (!token) return;
    fetchAll();
    fetchIntelligence();
    pollRef.current = setInterval(fetchAll, POLL_INTERVAL_MS);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [token, fetchAll, fetchIntelligence]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatMessages]);

  const sendChat = async () => {
    const q = chatInput.trim();
    if (!q || chatLoading) return;
    setChatMessages((p) => [...p, { role: 'user', content: q, timestamp: new Date() }]);
    setChatInput('');
    setChatLoading(true);
    try {
      const res = await api.post('/analytics/chatbot', { query: q });
      setChatMessages((p) => [...p, { role: 'assistant', content: res.data.answer, timestamp: new Date() }]);
    } catch {
      setChatMessages((p) => [...p, { role: 'assistant', content: '⚠️ Unable to process your query. Please try again.', timestamp: new Date() }]);
    } finally {
      setChatLoading(false);
    }
  };

  const acknowledgeAlert = async (id: string) => {
    if (role === 'analyst') return;
    setAcknowledging(id);
    try {
      await api.post(`/analytics/alerts/${id}/acknowledge`);
      setAlerts((p) => p.map((a) => a.id === id ? { ...a, acknowledged: true } : a));
    } catch (err) { console.error(err); }
    finally { setAcknowledging(null); }
  };

  if (!token) return <LoginScreen onLogin={handleLogin} />;

  if (loading) return (
    <div style={{ minHeight: '100vh', background: '#0f172a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ width: 48, height: 48, border: '4px solid #3b82f6', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 1rem' }} />
        <p style={{ color: '#94a3b8' }}>Loading intelligence data…</p>
      </div>
    </div>
  );

  const trendData = stats ? Object.entries(stats.recent_trends).map(([date, count]) => ({ date: date.slice(5), count })) : [];
  const categoryData = stats?.category_breakdown.map((c) => ({ name: c.category.replace(/_/g, ' '), count: c.count, fill: CATEGORY_COLORS[c.category] || '#9CA3AF' })) || [];
  const urgencyData = stats ? Object.entries(stats.urgency_breakdown).map(([k, v]) => ({ name: k, value: v, fill: URGENCY_COLORS[k] || '#9CA3AF' })) : [];
  const unacked = alerts.filter((a) => !a.acknowledged);
  const critical = alerts.filter((a) => a.severity_level === 'critical' && !a.acknowledged);

  const tabs: { id: Tab; label: string; icon: React.ElementType; badge?: number }[] = [
    { id: 'overview',     label: 'Overview',     icon: BarChart2 },
    { id: 'alerts',       label: 'Alerts',        icon: Bell,         badge: unacked.length },
    { id: 'clusters',     label: 'Clusters',      icon: Layers,       badge: clusters.filter(c => c.escalation_flag).length },
    { id: 'reports',      label: 'Reports',       icon: FileText },
    { id: 'intelligence', label: 'Intelligence',  icon: Zap },
    { id: 'chat',         label: 'AI Chat',       icon: MessageSquare },
  ];

  const card: React.CSSProperties = { background: '#1e293b', borderRadius: '16px', border: '1px solid #334155', padding: '1.25rem' };
  const sectionTitle: React.CSSProperties = { fontSize: '0.875rem', fontWeight: 600, color: '#cbd5e1', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' };

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: 'white', fontFamily: 'system-ui, sans-serif' }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } } @keyframes bounce { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-4px); } } * { box-sizing: border-box; }`}</style>

      {/* Header */}
      <header style={{ borderBottom: '1px solid #1e293b', background: '#0f172a', position: 'sticky', top: 0, zIndex: 40 }}>
        <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0.75rem 1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{ width: 32, height: 32, background: 'rgba(59,130,246,0.15)', borderRadius: '10px', border: '1px solid rgba(59,130,246,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Shield style={{ width: 16, height: 16, color: '#60a5fa' }} />
            </div>
            <span style={{ fontWeight: 700, color: 'white' }}>Anonymous Signal</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: '#64748b' }}>
              <div style={{ width: 8, height: 8, background: '#4ade80', borderRadius: '50%' }} />
              Live · {lastRefresh.toLocaleTimeString()}
            </div>
            {critical.length > 0 && (
              <button onClick={() => setActiveTab('alerts')} style={{ display: 'flex', alignItems: 'center', gap: '0.375rem', background: 'rgba(127,29,29,0.4)', border: '1px solid #991b1b', color: '#fca5a5', fontSize: '0.75rem', fontWeight: 700, padding: '0.375rem 0.75rem', borderRadius: '12px', cursor: 'pointer' }}>
                <AlertOctagon style={{ width: 12, height: 12 }} /> {critical.length} CRITICAL
              </button>
            )}
            <span style={{ fontSize: '0.75rem', background: '#1e293b', border: '1px solid #334155', color: '#94a3b8', padding: '0.25rem 0.625rem', borderRadius: '8px' }}>{role}</span>
            <button onClick={() => fetchAll()} style={{ padding: '0.5rem', background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}><RefreshCw style={{ width: 16, height: 16 }} /></button>
            <button onClick={handleLogout} style={{ padding: '0.5rem', background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}><LogOut style={{ width: 16, height: 16 }} /></button>
          </div>
        </div>
        <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 1.5rem', display: 'flex', overflowX: 'auto' }}>
          {tabs.map((tab) => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.625rem 1rem', fontSize: '0.875rem', fontWeight: 500, background: 'none', border: 'none', borderBottom: activeTab === tab.id ? '2px solid #3b82f6' : '2px solid transparent', color: activeTab === tab.id ? '#60a5fa' : '#94a3b8', cursor: 'pointer', whiteSpace: 'nowrap' }}>
              <tab.icon style={{ width: 14, height: 14 }} />
              {tab.label}
              {tab.badge != null && tab.badge > 0 && <span style={{ background: '#dc2626', color: 'white', fontSize: '0.65rem', width: 16, height: 16, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{tab.badge > 9 ? '9+' : tab.badge}</span>}
            </button>
          ))}
        </div>
      </header>

      <main style={{ maxWidth: 1400, margin: '0 auto', padding: '1.5rem' }}>

        {/* OVERVIEW */}
        {activeTab === 'overview' && stats && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
              <StatCard label="Total Reports" value={stats.total_reports.toLocaleString()} icon={FileText} color="blue" sub={`${stats.reports_last_24h} in last 24h`} />
              <StatCard label="High Urgency" value={stats.high_urgency_reports} icon={AlertTriangle} color="red" alert={stats.high_urgency_reports > 0} sub="critical + high" />
              <StatCard label="Active Clusters" value={stats.active_clusters} icon={Layers} color="purple" sub="emerging patterns" />
              <StatCard label="Pending Alerts" value={stats.unacknowledged_alerts} icon={Bell} color="yellow" alert={stats.unacknowledged_alerts > 0} sub="unacknowledged" />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
              <div style={card}>
                <div style={sectionTitle}><TrendingUp style={{ width: 16, height: 16, color: '#60a5fa' }} />Report Volume (7 Days)</div>
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={trendData}>
                    <defs>
                      <linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="date" stroke="#64748b" tick={{ fontSize: 11, fill: '#64748b' }} />
                    <YAxis stroke="#64748b" tick={{ fontSize: 11, fill: '#64748b' }} />
                    <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }} />
                    <Area type="monotone" dataKey="count" stroke="#3B82F6" fill="url(#cg)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div style={card}>
                <div style={sectionTitle}><Activity style={{ width: 16, height: 16, color: '#fb923c' }} />Urgency Breakdown</div>
                {urgencyData.length > 0 ? (
                  <>
                    <ResponsiveContainer width="100%" height={160}>
                      <PieChart>
                        <Pie data={urgencyData} cx="50%" cy="50%" innerRadius={45} outerRadius={70} paddingAngle={3} dataKey="value">
                          {urgencyData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                        </Pie>
                        <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem' }}>
                      {urgencyData.map((u) => (
                        <div key={u.name} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: u.fill }} />
                          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{u.name} ({u.value})</span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 160, color: '#64748b', fontSize: '0.875rem' }}>No data yet</div>}
              </div>
            </div>
            <div style={card}>
              <div style={sectionTitle}><BarChart2 style={{ width: 16, height: 16, color: '#c084fc' }} />Reports by Category</div>
              {categoryData.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={categoryData} margin={{ top: 5, right: 10, left: 0, bottom: 55 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    {/* Use custom AngledTick component to avoid TypeScript angle/textAnchor error */}
                    <XAxis dataKey="name" tick={<AngledTick />} interval={0} stroke="#64748b" />
                    <YAxis stroke="#64748b" tick={{ fontSize: 11, fill: '#64748b' }} />
                    <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0' }} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {categoryData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 160, color: '#64748b', fontSize: '0.875rem' }}>No categorized reports yet</div>}
            </div>
          </div>
        )}

        {/* ALERTS */}
        {activeTab === 'alerts' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Intelligence Alerts</h2>
              <span style={{ fontSize: '0.875rem', color: '#64748b' }}>{unacked.length} unacknowledged</span>
            </div>
            {alerts.length === 0 ? (
              <div style={{ ...card, textAlign: 'center', padding: '3rem' }}>
                <CheckCircle style={{ width: 48, height: 48, color: '#4ade80', margin: '0 auto 0.75rem', opacity: 0.5 }} />
                <p style={{ color: '#64748b', margin: 0 }}>No alerts. System is nominal.</p>
              </div>
            ) : alerts.map((alert) => (
              <div key={alert.id} style={{ ...card, border: `1px solid ${!alert.acknowledged && alert.severity_level === 'critical' ? '#991b1b' : !alert.acknowledged && alert.severity_level === 'high' ? '#c2410c' : '#334155'}`, opacity: alert.acknowledged ? 0.6 : 1 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.25rem' }}>
                      <UrgencyBadge level={alert.severity_level} />
                      {alert.category && <CategoryBadge category={alert.category} />}
                      <span style={{ fontSize: '0.7rem', color: '#64748b' }}>{alert.alert_type.replace(/_/g, ' ')}</span>
                    </div>
                    <h3 style={{ margin: '0 0 0.25rem', fontWeight: 600, color: 'white' }}>{alert.title}</h3>
                    <p style={{ margin: 0, fontSize: '0.875rem', color: '#94a3b8' }}>{alert.description}</p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.5rem', fontSize: '0.75rem', color: '#64748b' }}>
                      <span><Clock style={{ width: 12, height: 12, display: 'inline', marginRight: '0.25rem' }} />{new Date(alert.created_at).toLocaleString()}</span>
                      {alert.report_count != null && <span>{alert.report_count} reports in {alert.time_window_hours}h</span>}
                    </div>
                  </div>
                  <div>
                    {alert.acknowledged
                      ? <span style={{ fontSize: '0.75rem', color: '#4ade80', display: 'flex', alignItems: 'center', gap: '0.25rem' }}><CheckCircle style={{ width: 12, height: 12 }} />Acknowledged</span>
                      : role !== 'analyst'
                        ? <button onClick={() => acknowledgeAlert(alert.id)} disabled={acknowledging === alert.id} style={{ fontSize: '0.75rem', background: '#334155', border: 'none', color: 'white', padding: '0.375rem 0.75rem', borderRadius: '8px', cursor: 'pointer', opacity: acknowledging === alert.id ? 0.5 : 1 }}>
                            {acknowledging === alert.id ? 'Acknowledging…' : 'Acknowledge'}
                          </button>
                        : <span style={{ fontSize: '0.75rem', color: '#64748b' }}>Senior analyst required</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* CLUSTERS */}
        {activeTab === 'clusters' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Report Clusters</h2>
              <span style={{ fontSize: '0.875rem', color: '#64748b' }}>{clusters.length} active patterns</span>
            </div>
            {clusters.length === 0
              ? <div style={{ ...card, textAlign: 'center', padding: '3rem' }}><Layers style={{ width: 48, height: 48, margin: '0 auto 0.75rem', opacity: 0.2 }} /><p style={{ color: '#64748b', margin: 0 }}>No clusters detected yet.</p></div>
              : <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
                  {clusters.map((c) => (
                    <div key={c.id} style={{ ...card, border: `1px solid ${c.escalation_flag ? '#c2410c' : '#334155'}` }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                            {c.category && <CategoryBadge category={c.category} />}
                            {c.escalation_flag && <span style={{ fontSize: '0.7rem', background: 'rgba(124,45,18,0.4)', color: '#fdba74', border: '1px solid #c2410c', padding: '0.15rem 0.5rem', borderRadius: '9999px', fontWeight: 700 }}>⚡ ESCALATING</span>}
                          </div>
                          <h3 style={{ margin: '0.5rem 0 0', fontSize: '0.875rem', fontWeight: 600, color: 'white' }}>{c.label || c.category}</h3>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{c.report_count}</div>
                          <div style={{ fontSize: '0.7rem', color: '#64748b' }}>reports</div>
                        </div>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Last: {new Date(c.last_updated).toLocaleString()}</div>
                      {c.notes && <p style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '0.5rem', background: '#334155', borderRadius: '8px', padding: '0.5rem' }}>{c.notes}</p>}
                    </div>
                  ))}
                </div>}
          </div>
        )}

        {/* REPORTS */}
        {activeTab === 'reports' && (
          <div>
            <h2 style={{ fontSize: '1.125rem', fontWeight: 700, marginTop: 0 }}>Reports</h2>
            <div style={card}>
              <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginTop: 0 }}>Query reports via <code style={{ background: '#334155', padding: '0.125rem 0.375rem', borderRadius: '4px', color: '#93c5fd' }}>GET /api/v1/reports/</code></p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
                {['pending', 'processing', 'analyzed', 'flagged'].map((s) => (
                  <div key={s} style={{ background: '#334155', borderRadius: '10px', padding: '0.75rem', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem', textTransform: 'capitalize' }}>{s}</div>
                    <div style={{ fontWeight: 700 }}>—</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* INTELLIGENCE */}
        {activeTab === 'intelligence' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 700 }}>Intelligence Summary</h2>
              <button onClick={fetchIntelligence} style={{ fontSize: '0.75rem', background: '#334155', border: 'none', color: '#cbd5e1', padding: '0.375rem 0.75rem', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <RefreshCw style={{ width: 12, height: 12 }} /> Regenerate
              </button>
            </div>
            {role === 'analyst'
              ? <div style={{ ...card, border: '1px solid #b45309', textAlign: 'center', padding: '2rem' }}><AlertTriangle style={{ width: 40, height: 40, color: '#fbbf24', margin: '0 auto 0.75rem' }} /><p style={{ color: '#fcd34d', fontWeight: 600, margin: 0 }}>Senior Analyst or Admin access required</p></div>
              : intelligence
                ? <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                      <StatCard label="Reports (24h)" value={intelligence.total_reports_in_window} icon={FileText} color="blue" />
                      <StatCard label="Critical/High" value={intelligence.critical_high_count} icon={AlertTriangle} color="red" alert={intelligence.critical_high_count > 0} />
                      <StatCard label="New Clusters" value={intelligence.new_clusters_detected} icon={Layers} color="purple" />
                      <StatCard label="Surging" value={intelligence.surging_clusters.length} icon={Zap} color="orange" />
                    </div>
                    <div style={card}>
                      <div style={sectionTitle}><Zap style={{ width: 16, height: 16, color: '#fbbf24' }} />AI-Generated Insights</div>
                      {intelligence.insights.map((insight, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', background: 'rgba(51,65,85,0.5)', borderRadius: '10px', padding: '0.75rem', marginBottom: '0.75rem' }}>
                          <span style={{ color: '#64748b', fontSize: '0.75rem', fontWeight: 700, marginTop: 2 }}>{String(i + 1).padStart(2, '0')}</span>
                          <p style={{ margin: 0, fontSize: '0.875rem', color: '#e2e8f0' }}>{insight}</p>
                        </div>
                      ))}
                    </div>
                    {intelligence.surging_clusters.length > 0 && (
                      <div style={{ ...card, border: '1px solid #c2410c', background: 'rgba(124,45,18,0.15)' }}>
                        <div style={{ ...sectionTitle, color: '#fdba74' }}><Zap style={{ width: 16, height: 16 }} />Surging Patterns</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                          {intelligence.surging_clusters.map((label, i) => (
                            <span key={i} style={{ background: 'rgba(124,45,18,0.4)', border: '1px solid #c2410c', color: '#fed7aa', fontSize: '0.75rem', padding: '0.375rem 0.75rem', borderRadius: '10px' }}>⚡ {label}</span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                : <div style={{ ...card, textAlign: 'center', padding: '3rem' }}><div style={{ width: 32, height: 32, border: '4px solid #3b82f6', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 1rem' }} /><p style={{ color: '#94a3b8', margin: 0 }}>Generating intelligence summary…</p></div>}
          </div>
        )}

        {/* CHAT */}
        {activeTab === 'chat' && (
          <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 220px)', maxHeight: 700 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
              <div style={{ width: 32, height: 32, background: 'rgba(59,130,246,0.15)', borderRadius: '10px', border: '1px solid rgba(59,130,246,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <MessageSquare style={{ width: 16, height: 16, color: '#60a5fa' }} />
              </div>
              <div>
                <div style={{ fontWeight: 700 }}>Intelligence AI Assistant</div>
                <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Queries live report data — RAG-powered</div>
              </div>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem', paddingBottom: '0.5rem' }}>
              {chatMessages.map((msg, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                  <div
                    style={{ maxWidth: '80%', borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px', padding: '0.75rem 1rem', fontSize: '0.875rem', background: msg.role === 'user' ? '#2563eb' : '#1e293b', border: msg.role === 'user' ? 'none' : '1px solid #334155', color: '#e2e8f0' }}
                    dangerouslySetInnerHTML={{ __html: msg.content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\*(.*?)\*/g, '<em>$1</em>').replace(/\n/g, '<br/>') }}
                  />
                </div>
              ))}
              {chatLoading && (
                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '16px 16px 16px 4px', padding: '0.75rem 1rem', display: 'flex', gap: '0.25rem' }}>
                    {[0, 150, 300].map((d) => <div key={d} style={{ width: 8, height: 8, background: '#64748b', borderRadius: '50%', animation: `bounce 1s ${d}ms infinite` }} />)}
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', overflowX: 'auto', paddingBottom: '0.5rem', marginBottom: '0.5rem' }}>
              {["Show today's surges", "Critical alerts", "Top risk categories", "Active clusters", "Urgency breakdown"].map((p) => (
                <button key={p} onClick={() => setChatInput(p)} style={{ fontSize: '0.75rem', background: '#1e293b', border: '1px solid #334155', color: '#94a3b8', padding: '0.375rem 0.75rem', borderRadius: '10px', cursor: 'pointer', whiteSpace: 'nowrap' }}>{p}</button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <input
                type="text" value={chatInput} onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendChat()}
                placeholder="Ask about trends, risks, patterns…"
                disabled={chatLoading}
                style={{ flex: 1, background: '#1e293b', border: '1px solid #334155', borderRadius: '12px', padding: '0.75rem 1rem', color: 'white', outline: 'none', fontSize: '0.875rem' }}
              />
              <button onClick={sendChat} disabled={chatLoading || !chatInput.trim()} style={{ background: '#2563eb', border: 'none', borderRadius: '12px', padding: '0.75rem 1rem', color: 'white', cursor: 'pointer', opacity: chatLoading || !chatInput.trim() ? 0.4 : 1 }}>
                <Send style={{ width: 16, height: 16 }} />
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
