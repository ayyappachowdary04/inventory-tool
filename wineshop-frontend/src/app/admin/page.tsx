'use client';
import { useState, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import { useAuth } from '@/context/AuthContext';
import { fetchApi, API_BASE } from '@/lib/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function AdminDashboard() {
  const { session } = useAuth();
  const [trendData, setTrendData] = useState([]);
  const [todayData, setTodayData] = useState({ data: [], total_revenue: 0 });
  const [todayStr, setTodayStr] = useState('');
  
  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const todayRes = await fetchApi('/today');
      setTodayStr(todayRes.date);
      
      const [trend, report] = await Promise.all([
        fetchApi('/reports/trend'),
        fetchApi(`/reports/daily/${todayRes.date}`)
      ]);
      setTrendData(trend);
      setTodayData(report);
    } catch (e) {
      console.error(e);
    }
  };

  const handleExcelDownload = async () => {
    // Standard link download approach for files
    window.open(`${API_BASE}/reports/excel?start_date=${todayStr}&end_date=${todayStr}`);
  };

  if (session.role !== 'admin') return null;

  return (
    <div className="page-wrapper">
      <Sidebar />
      <main className="main-content">
        <h1 style={{ marginBottom: '2rem' }}>Administrator Dashboard</h1>

        <div className="grid-3" style={{ marginBottom: '2rem' }}>
          <div className="metric-card">
            <div className="metric-label">Today's Revenue</div>
            <div className="metric-value">₹ {todayData.total_revenue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">7-Day Trend</div>
            <div className="metric-value">
              ₹ {trendData.reduce((sum: number, item: any) => sum + item.revenue, 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </div>
          </div>
          <div className="metric-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <button className="btn btn-primary" onClick={handleExcelDownload} style={{ width: '100%' }}>
              ⬇ Download Excel Report
            </button>
          </div>
        </div>

        <div className="glass-card animate-fade-in" style={{ marginBottom: '2rem' }}>
          <h2>7-Day Sales History</h2>
          <div style={{ height: '300px', width: '100%', marginTop: '1rem' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={trendData}>
                <XAxis dataKey="date" stroke="var(--text-secondary)" />
                <YAxis stroke="var(--text-secondary)" />
                <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{ backgroundColor: 'var(--bg-tertiary)', border: 'none', borderRadius: '8px' }} />
                <Bar dataKey="revenue" fill="var(--accent-gold)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass-card animate-fade-in">
          <h2>Today's Quick Summary</h2>
          {todayData.data.length > 0 ? (
            <div className="data-table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Brand</th>
                    <th>2L Sold</th>
                    <th>1L Sold</th>
                    <th>Q Sold</th>
                    <th>P Sold</th>
                    <th>N Sold</th>
                    <th>Revenue generated (₹)</th>
                  </tr>
                </thead>
                <tbody>
                  {todayData.data.filter((b: any) => b.revenue > 0).map((brand: any, idx) => (
                    <tr key={idx}>
                      <td>{brand.brand}</td>
                      <td>{brand['2L_sold']}</td>
                      <td>{brand['1L_sold']}</td>
                      <td>{brand['Q_sold']}</td>
                      <td>{brand['P_sold']}</td>
                      <td>{brand['N_sold']}</td>
                      <td><span className="text-accent">{brand.revenue.toFixed(2)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-muted">No sales data available for today yet.</p>
          )}
        </div>
      </main>
    </div>
  );
}
