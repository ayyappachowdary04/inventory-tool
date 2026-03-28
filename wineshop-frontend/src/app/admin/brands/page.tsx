'use client';
import { useState, useEffect, useRef } from 'react';
import Sidebar from '@/components/Sidebar';
import { useAuth } from '@/context/AuthContext';
import { fetchApi, postApi, putApi, API_BASE } from '@/lib/api';

export default function BrandsPage() {
  const { session } = useAuth();
  const [brands, setBrands] = useState<any[]>([]);
  const [selectedBrandId, setSelectedBrandId] = useState<number | 'none'>('none');
  const [newBrandName, setNewBrandName] = useState('');
  const [prices, setPrices] = useState({ '2L': 0, '1L': 0, 'Q': 0, 'P': 0, 'N': 0 });
  const [auditLog, setAuditLog] = useState<any[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadBrands();
    loadAudit();
  }, []);

  const loadBrands = async () => {
    try {
      const b = await fetchApi('/brands');
      setBrands(b);
    } catch (e) {
      console.error(e);
    }
  };

  const loadAudit = async () => {
    try {
      const a = await fetchApi('/price-audit');
      setAuditLog(a);
    } catch (e) {
      console.error(e);
    }
  };

  const loadPrices = async (brandId: number) => {
    try {
      const p = await fetchApi(`/prices/${brandId}`);
      const mapping = { '2L': 0, '1L': 0, 'Q': 0, 'P': 0, 'N': 0 };
      p.forEach((item: any) => {
        (mapping as any)[item.variant] = item.price || 0;
      });
      setPrices(mapping);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (selectedBrandId !== 'none') {
      loadPrices(Number(selectedBrandId));
    }
  }, [selectedBrandId]);

  const handleAddBrand = async () => {
    if (!newBrandName.trim()) return;
    try {
      await postApi('/brands', { name: newBrandName });
      alert(`✅ Added '${newBrandName}' successfully!`);
      setNewBrandName('');
      loadBrands();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleSavePrices = async () => {
    if (selectedBrandId === 'none') return;
    try {
      await putApi(`/prices/${selectedBrandId}`, { prices });
      alert(`✅ Prices updated!`);
      loadAudit();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleListUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await fetch(`${API_BASE}/import/brands-excel`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      
      let msg = `✅ Import Complete!\n• Brands Processed: ${data.brands_processed}\n• Prices Updated: ${data.prices_updated}`;
      if (data.typos_fixed > 0) msg += `\n• 🪄 Auto-corrected ${data.typos_fixed} typos.`;
      
      alert(msg);
      loadBrands();
      loadAudit();
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err: any) {
      alert(`Error: ${err.message}`);
    }
  };

  if (session.role !== 'admin') return null;

  return (
    <div className="page-wrapper">
      <Sidebar />
      <main className="main-content">
        <h1 style={{ marginBottom: '2rem' }}>Brand & Price Manager</h1>

        <div className="grid-2">
          {/* Add Brand & Edit Prices */}
          <div>
            <div className="glass-card animate-fade-in" style={{ marginBottom: '2rem' }}>
              <h2>➕ Add New Brand Manually</h2>
              <div className="flex-start" style={{ marginTop: '1rem' }}>
                <input 
                  type="text" className="form-input" placeholder="New Brand Name"
                  value={newBrandName} onChange={(e) => setNewBrandName(e.target.value)}
                  style={{ flex: 1 }}
                />
                <button className="btn btn-primary" onClick={handleAddBrand}>Add Brand</button>
              </div>
            </div>

            <div className="glass-card animate-fade-in" style={{ marginBottom: '2rem' }}>
              <h2>Edit Prices</h2>
              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Select Brand to Edit</label>
                <select 
                  className="form-input" 
                  value={selectedBrandId} 
                  onChange={(e) => setSelectedBrandId(e.target.value === 'none' ? 'none' : Number(e.target.value))}
                >
                  <option value="none" disabled>-- Select Brand --</option>
                  {brands.map((b: any) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </select>
              </div>

              {selectedBrandId !== 'none' && (
                <div style={{ marginTop: '1.5rem' }}>
                  <div className="grid-3" style={{ gap: '1rem' }}>
                    {Object.keys(prices).map(v => (
                      <div key={v}>
                        <label className="form-label">{v} (₹)</label>
                        <input 
                          type="number" min="0" step="10" className="form-input" 
                          value={(prices as any)[v]} 
                          onChange={(e) => setPrices({ ...prices, [v]: Number(e.target.value) || 0 })}
                        />
                      </div>
                    ))}
                  </div>
                  <button className="btn btn-primary" onClick={handleSavePrices} style={{ marginTop: '2rem', width: '100%' }}>
                    💾 Save Updated Prices
                  </button>
                </div>
              )}
            </div>
            
            <div className="glass-card animate-fade-in">
              <h2>📥 Load Full Brand / Price List (Master Import)</h2>
              <p className="text-muted" style={{ marginBottom: '1.5rem', fontSize: '0.9rem' }}>
                Quickly add hundreds of brands or update all prices at once using an Excel or CSV file.
              </p>
              
              <div className="file-upload-zone">
                <div className="upload-icon">📊</div>
                <div className="upload-text">Click or Drag Excel File Here</div>
                <div className="upload-hint">Supports .xlsx, .xls, .csv</div>
                <input 
                  type="file" 
                  className="file-upload-input"
                  ref={fileInputRef} 
                  onChange={handleListUpload} 
                  accept=".xlsx,.xls,.csv" 
                />
              </div>

              <div style={{ padding: '1rem', background: 'rgba(212, 175, 55, 0.1)', borderRadius: '8px', border: '1px solid var(--accent-gold)' }}>
                <p style={{ fontSize: '0.85rem', color: 'var(--accent-gold)' }}>
                  <strong>💡 Pro Tip:</strong> Your Excel should have brand names in any column labeled "Brand" or "Name", and prices in columns like "750", "375", "180", or "Full/Half".
                </p>
              </div>
            </div>
          </div>

          {/* Audit History */}
          <div className="glass-card animate-fade-in">
            <h2>📜 Price Change History</h2>
            <div className="data-table-container" style={{ marginTop: '1rem', maxHeight: '600px', overflowY: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date & Time</th>
                    <th>Brand</th>
                    <th>Size</th>
                    <th>Old (₹)</th>
                    <th>New (₹)</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLog.length === 0 ? (
                    <tr><td colSpan={5} style={{ textAlign: 'center' }}>No price changes recorded</td></tr>
                  ) : (
                    auditLog.map((log: any, idx) => (
                      <tr key={idx}>
                        <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{log.timestamp}</td>
                        <td>{log.brand}</td>
                        <td>{log.variant}</td>
                        <td className="text-muted">{log.old_price}</td>
                        <td className="text-accent">{log.new_price}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

      </main>
    </div>
  );
}
