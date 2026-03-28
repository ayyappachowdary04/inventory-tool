'use client';
import { useState, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import { useAuth } from '@/context/AuthContext';
import { fetchApi, postApi } from '@/lib/api';

export default function ApprovalsPage() {
  const { session } = useAuth();
  const [pendingDates, setPendingDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [reportData, setReportData] = useState<any>({ data: [], total_revenue: 0 });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadPendingDates();
  }, []);

  const loadPendingDates = async () => {
    try {
      const dates = await fetchApi('/pending-approvals');
      setPendingDates(dates);
      if (dates.length > 0 && !selectedDate) {
        setSelectedDate(dates[0]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (selectedDate) {
      loadReport(selectedDate);
    } else {
      setReportData({ data: [], total_revenue: 0 });
    }
  }, [selectedDate]);

  const loadReport = async (date: string) => {
    setLoading(true);
    try {
      const report = await fetchApi(`/reports/daily/${date}`);
      setReportData(report);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (action: 'approve' | 'reject') => {
    if (!selectedDate) return;
    try {
      if (action === 'approve') {
        await postApi(`/inventory/approve/${selectedDate}`, {});
        alert(`Report for ${selectedDate} has been Approved and Locked!`);
      } else {
        await postApi(`/inventory/reject/${selectedDate}`, {});
        alert(`Report for ${selectedDate} has been rejected. Sent back to Shopkeeper.`);
      }
      setSelectedDate('');
      loadPendingDates();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  if (session.role !== 'admin') return null;

  return (
    <div className="page-wrapper">
      <Sidebar />
      <main className="main-content">
        <h1 style={{ marginBottom: '2rem' }}>Daily Report Approvals</h1>

        {pendingDates.length === 0 ? (
          <div className="glass-card animate-fade-in" style={{ backgroundColor: 'rgba(46, 139, 87, 0.1)', borderColor: 'var(--success)' }}>
            <h3 className="text-success">🎉 All caught up!</h3>
            <p>No reports are currently pending approval.</p>
          </div>
        ) : (
          <>
            <div className="glass-card animate-fade-in" style={{ marginBottom: '2rem' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">Select Date to Review</label>
                <select 
                  className="form-input" 
                  value={selectedDate} 
                  onChange={(e) => setSelectedDate(e.target.value)}
                  style={{ maxWidth: '300px' }}
                >
                  <option value="" disabled>-- Select a Date --</option>
                  {pendingDates.map(date => (
                    <option key={date} value={date}>{date}</option>
                  ))}
                </select>
              </div>
            </div>

            {selectedDate && reportData.data.length > 0 && (
              <div className="glass-card animate-fade-in">
                <div className="flex-between" style={{ marginBottom: '2rem' }}>
                  <h2>Reviewing Report: {selectedDate}</h2>
                  <div className="metric-value">₹ {reportData.total_revenue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
                </div>

                <div className="data-table-container" style={{ marginBottom: '2rem' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Brand</th>
                        <th>Variant</th>
                        <th>Opening</th>
                        <th>Closing</th>
                        <th>Sold</th>
                        <th>Revenue (₹)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportData.data.map((brand: any, idx: number) => {
                        return ['2L', '1L', 'Q', 'P', 'N'].map(v => {
                          const available = brand[`${v}_available`];
                          const closing = brand[`${v}_closing`];
                          const sold = brand[`${v}_sold`];
                          if (available === 0 && closing === 0 && sold === 0) return null;
                          return (
                            <tr key={`${idx}-${v}`}>
                              <td>{brand.brand}</td>
                              <td>{v}</td>
                              <td>{available}</td>
                              <td>{closing}</td>
                              <td>{sold}</td>
                              <td>--</td>
                            </tr>
                          );
                        });
                      })}
                      <tr>
                        <td colSpan={5} style={{ textAlign: 'right', fontWeight: 'bold' }}>Total Revenue</td>
                        <td style={{ fontWeight: 'bold', color: 'var(--accent-gold)' }}>
                          {reportData.total_revenue.toFixed(2)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div className="grid-2" style={{ gap: '1rem' }}>
                  <button className="btn btn-outline" style={{ color: 'var(--danger)', borderColor: 'var(--danger)' }} onClick={() => handleAction('reject')}>
                    ❌ Reject (Send back to Shopkeeper)
                  </button>
                  <button className="btn btn-success" onClick={() => handleAction('approve')}>
                    🔒 Approve & Lock Report
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
