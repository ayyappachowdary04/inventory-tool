'use client';
import { useState, useEffect } from 'react';
import Sidebar from '@/components/Sidebar';
import { useAuth } from '@/context/AuthContext';
import { fetchApi, postApi, putApi } from '@/lib/api';
import { Search, Save, Upload, Eye } from 'lucide-react';

export default function ShopkeeperPage() {
  const { session } = useAuth();
  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [inventory, setInventory] = useState<any[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [currentBrandIdx, setCurrentBrandIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'wizard' | 'import' | 'preview'>('wizard');

  useEffect(() => {
    loadDay();
  }, [date]);

  const loadDay = async () => {
    setLoading(true);
    try {
      await postApi(`/inventory/init/${date}`, {});
      const data = await fetchApi(`/inventory/${date}`);
      setInventory(data);
      
      const uniqueBrands = Array.from(new Set(data.map((item: any) => item.name))) as string[];
      setBrands(uniqueBrands);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleClosingChange = (brandId: number, variant: string, val: string, maxVal: number) => {
    const num = Math.min(Math.max(0, parseInt(val) || 0), maxVal);
    setInventory(prev => prev.map(item => 
      (item.brand_id === brandId && item.variant === variant) ? { ...item, closing: num } : item
    ));
    // Save to DB instantly
    putApi('/inventory/closing', { date, brand_id: brandId, variant, closing: num });
  };

  const submitReport = async () => {
    if (confirm("Submit final report to Admin?")) {
      await postApi(`/inventory/submit/${date}`, {});
      alert("Report submitted successfully!");
      loadDay(); // refresh to show locked status (if admin sets it) or pending
    }
  };

  if (!session.role) return null;

  const currentBrand = brands[currentBrandIdx];
  const brandItems = inventory.filter(i => i.name === currentBrand);
  const hasItems = brandItems.length > 0;
  
  // Calculate preview data
  const totalRevenue = inventory.reduce((sum, item) => {
    const available = item.opening + item.receipts;
    const sold = available - item.closing;
    return sum + (sold * item.price);
  }, 0);

  return (
    <div className="page-wrapper">
      <Sidebar />
      <main className="main-content">
        <div className="flex-between" style={{ marginBottom: '2rem' }}>
          <div>
            <h1>Daily Closing Wizard</h1>
            <p className="text-muted">Enter end of day actual stock counts</p>
          </div>
          <div>
            <input 
              type="date" 
              className="form-input" 
              value={date} 
              onChange={(e) => setDate(e.target.value)}
              style={{ padding: '0.5rem 1rem', width: 'auto' }}
            />
          </div>
        </div>

        {inventory.length > 0 && inventory[0].status === 2 && (
          <div className="glass-card" style={{ marginBottom: '2rem', borderColor: 'var(--success)', backgroundColor: 'rgba(46, 139, 87, 0.1)' }}>
            <h3 className="text-success">🔒 Report Approved & Locked</h3>
            <p>Admin has approved business for this date. Editing is disabled.</p>
          </div>
        )}

        <div style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid var(--border)', marginBottom: '2rem' }}>
          {[
            { id: 'wizard', label: 'Manual Entry' },
            { id: 'import', label: 'Import Excel' },
            { id: 'preview', label: 'Final Preview' }
          ].map(tab => (
            <button 
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              style={{
                background: 'none', border: 'none', borderBottom: activeTab === tab.id ? '2px solid var(--accent-gold)' : '2px solid transparent',
                color: activeTab === tab.id ? 'var(--accent-gold)' : 'var(--text-secondary)',
                padding: '0.5rem 1rem', cursor: 'pointer', fontSize: '1rem', fontWeight: 500
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'wizard' && hasItems && inventory[0]?.status !== 2 && (
          <div className="glass-card animate-fade-in" style={{ maxWidth: '800px', margin: '0 auto' }}>
            <div className="flex-between" style={{ marginBottom: '2rem' }}>
              <span className="text-muted">Brand {currentBrandIdx + 1} of {brands.length}</span>
              <select 
                className="form-input" 
                style={{ width: '250px', padding: '0.5rem' }}
                value={currentBrandIdx}
                onChange={(e) => setCurrentBrandIdx(Number(e.target.value))}
              >
                {brands.map((b, i) => <option key={i} value={i}>{b}</option>)}
              </select>
            </div>

            <h2 style={{ textAlign: 'center', marginBottom: '2rem', color: 'var(--accent-gold)' }}>🍾 {currentBrand}</h2>

            <div className="grid-3" style={{ marginBottom: '2rem' }}>
              {brandItems.map(item => {
                const available = item.opening + item.receipts;
                return (
                  <div key={item.variant} style={{ background: 'var(--bg-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border)' }}>
                    <div className="flex-between" style={{ marginBottom: '0.5rem' }}>
                      <span style={{ fontWeight: 600 }}>{item.variant}</span>
                      <span className="text-muted" style={{ fontSize: '0.8rem' }}>Max: {available}</span>
                    </div>
                    <input 
                      type="number" 
                      className="form-input"
                      style={{ padding: '0.5rem' }}
                      value={item.closing}
                      min="0"
                      max={available}
                      onChange={(e) => handleClosingChange(item.brand_id, item.variant, e.target.value, available)}
                      disabled={available === 0}
                    />
                  </div>
                );
              })}
            </div>

            <div className="flex-between" style={{ borderTop: '1px solid var(--border)', paddingTop: '1.5rem' }}>
              <button 
                className="btn btn-outline" 
                onClick={() => setCurrentBrandIdx(Math.max(0, currentBrandIdx - 1))}
                disabled={currentBrandIdx === 0}
              >
                &larr; Previous
              </button>
              <button 
                className="btn btn-primary" 
                onClick={() => setCurrentBrandIdx(Math.min(brands.length - 1, currentBrandIdx + 1))}
              >
                {currentBrandIdx === brands.length - 1 ? 'Check Preview' : 'Next Brand \u2192'}
              </button>
            </div>
          </div>
        )}

        {activeTab === 'preview' && (
          <div className="glass-card animate-fade-in">
            <div className="flex-between" style={{ marginBottom: '1.5rem' }}>
              <h2>Final Report Summary</h2>
              <div className="metric-value">₹ {totalRevenue.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
            </div>
            
            <div className="data-table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Brand</th>
                    <th>Variant</th>
                    <th>Opening + Rcpt</th>
                    <th>Closing Stock</th>
                    <th>Sold</th>
                    <th>Revenue</th>
                  </tr>
                </thead>
                <tbody>
                  {inventory.filter(i => (i.opening + i.receipts) > 0).map((item, idx) => {
                    const available = item.opening + item.receipts;
                    const sold = available - item.closing;
                    return (
                      <tr key={idx}>
                        <td>{item.name}</td>
                        <td>{item.variant}</td>
                        <td>{available}</td>
                        <td><span style={{ color: 'var(--accent-gold)' }}>{item.closing}</span></td>
                        <td>{sold}</td>
                        <td>₹ {(sold * item.price).toFixed(2)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div style={{ marginTop: '2rem', textAlign: 'right' }}>
              <button className="btn btn-primary" onClick={submitReport} disabled={inventory[0]?.status === 2 || inventory[0]?.status === 1}>
                {inventory[0]?.status === 1 ? 'Pending Approval' : inventory[0]?.status === 2 ? 'Locked' : 'Submit Final Report to Admin'}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
