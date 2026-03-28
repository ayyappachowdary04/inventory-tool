'use client';
import { useState, useEffect, useRef } from 'react';
import Sidebar from '@/components/Sidebar';
import { useAuth } from '@/context/AuthContext';
import { fetchApi, postApi, putApi, API_BASE } from '@/lib/api';

export default function StockIntakePage() {
  const { session } = useAuth();
  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [activeTab, setActiveTab] = useState<'manual' | 'excel' | 'pdf'>('manual');
  const [brands, setBrands] = useState<any[]>([]);
  const [selectedBrandId, setSelectedBrandId] = useState<number | 'none'>('none');
  const [manualQs, setManualQs] = useState({ '2L': 0, '1L': 0, 'Q': 0, 'P': 0, 'N': 0 });
  const [pdfData, setPdfData] = useState<any[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchApi('/brands').then(setBrands).catch(console.error);
  }, []);

  const handleManualSave = async () => {
    if (selectedBrandId === 'none') return alert('Select a brand');
    try {
      for (const [v, qty] of Object.entries(manualQs)) {
        if (qty > 0) {
          await putApi('/inventory/receipts', { date, brand_id: Number(selectedBrandId), variant: v, qty });
        }
      }
      alert('Stock receipts updated successfully!');
      setManualQs({ '2L': 0, '1L': 0, 'Q': 0, 'P': 0, 'N': 0 });
      setSelectedBrandId('none');
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleExcelUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await fetch(`${API_BASE}/import/receipts-excel?date=${date}`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      alert(`✅ Successfully imported ${data.imported} brands!`);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err: any) {
      alert(`Error: ${err.message}`);
    }
  };

  const handlePdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await fetch(`${API_BASE}/import/pdf`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      if (data.items.length === 0) {
        alert('❌ No data found in PDF.');
      } else {
        setPdfData(data.items.map((i: any) => ({ ...i, date })));
      }
    } catch (err: any) {
      alert(`Error: ${err.message}`);
    }
  };

  const savePdfToDb = async () => {
    if (!pdfData) return;
    try {
      await postApi('/import/pdf-save', pdfData);
      alert(`✅ Saved ${pdfData.length} items to database!`);
      setPdfData(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  if (session.role !== 'admin') return null;

  return (
    <div className="page-wrapper">
      <Sidebar />
      <main className="main-content">
        <div className="flex-between" style={{ marginBottom: '2rem' }}>
          <div>
            <h1>Add New Stock (Receipts)</h1>
            <p className="text-muted">Record inward stock from suppliers</p>
          </div>
          <div>
            <input 
              type="date" className="form-input" 
              value={date} onChange={(e) => setDate(e.target.value)}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid var(--border)', marginBottom: '2rem' }}>
          {[
            { id: 'manual', label: '✋ Manual Entry' },
            { id: 'excel', label: '📂 Import Excel' },
            { id: 'pdf', label: '📄 Scan PDF Invoice' }
          ].map(tab => (
            <button 
              key={tab.id} onClick={() => setActiveTab(tab.id as any)}
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

        {activeTab === 'manual' && (
          <div className="glass-card animate-fade-in" style={{ maxWidth: '800px', margin: '0 auto' }}>
            <h2>Manual Item Entry</h2>
            <div className="form-group" style={{ marginTop: '1.5rem' }}>
              <label className="form-label">Select Brand Received</label>
              <select 
                className="form-input" 
                value={selectedBrandId} 
                onChange={(e) => setSelectedBrandId(e.target.value === 'none' ? 'none' : Number(e.target.value))}
              >
                <option value="none" disabled>-- Select Brand --</option>
                {brands.map(b => (
                  <option key={b.id} value={b.id}>{b.name}</option>
                ))}
              </select>
            </div>

            {selectedBrandId !== 'none' && (
              <div style={{ marginTop: '2rem' }}>
                <h4 style={{ marginBottom: '1rem' }}>Enter Quantities received:</h4>
                <div className="grid-3" style={{ gap: '1rem' }}>
                  {Object.keys(manualQs).map(v => (
                    <div key={v}>
                      <label className="form-label">{v}</label>
                      <input 
                        type="number" min="0" className="form-input" 
                        value={(manualQs as any)[v]} 
                        onChange={(e) => setManualQs({ ...manualQs, [v]: parseInt(e.target.value) || 0 })}
                      />
                    </div>
                  ))}
                </div>
                <button className="btn btn-primary" onClick={handleManualSave} style={{ marginTop: '2rem' }}>
                  💾 Save Receipts
                </button>
              </div>
            )}
          </div>
        )}

        {(activeTab === 'excel' || activeTab === 'pdf') && (
          <div className="glass-card animate-fade-in" style={{ maxWidth: '800px', margin: '0 auto', textAlign: 'center' }}>
            <h2 style={{ marginBottom: '1.5rem' }}>Upload {activeTab === 'excel' ? 'Excel/CSV Report' : 'Supplier PDF Invoice'}</h2>
            
            <div style={{ padding: '3rem', border: '2px dashed var(--border)', borderRadius: '12px', background: 'var(--bg-secondary)', marginBottom: '2rem' }}>
              <input 
                type="file" 
                accept={activeTab === 'excel' ? ".xlsx,.xls,.csv" : ".pdf"}
                onChange={activeTab === 'excel' ? handleExcelUpload : handlePdfUpload}
                ref={fileInputRef}
                style={{ fontSize: '1.1rem' }}
              />
            </div>
            {activeTab === 'excel' && <p className="text-muted">We will match Excel headers like "750ml" or "Q" and Brand Names to update incoming intake for {date}.</p>}

            {pdfData && (
              <div style={{ marginTop: '2rem', textAlign: 'left' }}>
                <h3 className="text-success">✅ Found {pdfData.length} items to import</h3>
                <div className="data-table-container" style={{ margin: '1rem 0' }}>
                  <table className="data-table">
                    <thead><tr><th>Extracted Brand Name</th><th>Variant</th><th>Qty (Bottles)</th></tr></thead>
                    <tbody>
                      {pdfData.map((d, idx) => (
                        <tr key={idx}><td>{d.brand_name}</td><td>{d.variant}</td><td>{d.qty}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button className="btn btn-primary" onClick={savePdfToDb}>🚀 Save to Database</button>
              </div>
            )}
          </div>
        )}

      </main>
    </div>
  );
}
