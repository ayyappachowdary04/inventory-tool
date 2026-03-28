'use client';
import { useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { useAuth } from '@/context/AuthContext';
import { putApi, API_BASE } from '@/lib/api';

export default function SettingsPage() {
  const { session, logout } = useAuth();
  const [adminPass, setAdminPass] = useState('');
  const [shopPin, setShopPin] = useState('');
  const [confirmInv, setConfirmInv] = useState(false);
  const [confirmAll, setConfirmAll] = useState(false);

  if (session.role !== 'admin') return null;

  const handleAdminPass = async () => {
    if (!adminPass) return;
    try {
      await putApi('/settings/password', { username: session.username || 'admin', new_password: adminPass });
      alert('Admin password updated successfully!');
      setAdminPass('');
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleShopPin = async () => {
    if (!shopPin) return;
    try {
      await putApi('/settings/pin', { new_pin: shopPin });
      alert(`Shopkeeper PIN changed to: ${shopPin}`);
      setShopPin('');
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleBackup = () => {
    window.open(`${API_BASE}/settings/backup`, '_blank');
  };

  const handleResetInventory = async () => {
    if (!confirmInv) return alert('Please check the confirmation box.');
    try {
      const res = await fetch(`${API_BASE}/settings/reset-inventory`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      alert('✅ Inventory history has been wiped.');
      setConfirmInv(false);
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  const handleResetAll = async () => {
    if (!confirmAll) return alert('Please check the confirmation box.');
    try {
      const res = await fetch(`${API_BASE}/settings/reset-all`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      alert('✅ System Wiped: All Brands, Prices, and Inventory deleted. You will be logged out.');
      setConfirmAll(false);
      logout();
    } catch (e: any) {
      alert(`Error: ${e.message}`);
    }
  };

  return (
    <div className="page-wrapper">
      <Sidebar />
      <main className="main-content">
        <h1 style={{ marginBottom: '2rem' }}>Administrator Settings</h1>

        <div className="grid-2">
          {/* Access Control */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <div className="glass-card animate-fade-in">
              <h2>👤 Change Admin Password</h2>
              <div className="flex-start" style={{ marginTop: '1rem' }}>
                <input 
                  type="password" placeholder="New Admin Password" 
                  className="form-input" style={{ flex: 1 }}
                  value={adminPass} onChange={(e) => setAdminPass(e.target.value)}
                />
                <button className="btn btn-primary" onClick={handleAdminPass}>Update</button>
              </div>
            </div>

            <div className="glass-card animate-fade-in">
              <h2>🏪 Shopkeeper Access</h2>
              <p className="text-muted" style={{ fontSize: '0.9rem', marginBottom: '1rem' }}>
                Update the PIN used by shopkeepers on the login screen.
              </p>
              <div className="flex-start">
                <input 
                  type="password" placeholder="New Shopkeeper PIN" maxLength={6}
                  className="form-input" style={{ flex: 1 }}
                  value={shopPin} onChange={(e) => setShopPin(e.target.value)}
                />
                <button className="btn btn-primary" onClick={handleShopPin}>Update PIN</button>
              </div>
            </div>

            <div className="glass-card animate-fade-in" style={{ backgroundColor: 'rgba(207, 168, 86, 0.1)', borderColor: 'var(--accent-gold)' }}>
              <h2 className="text-accent">💾 System Backup</h2>
              <p style={{ marginBottom: '1.5rem', fontSize: '0.9rem' }}>
                Download a full backup of the SQLite database containing all brands, prices, and past inventory.
              </p>
              <button className="btn btn-primary" style={{ width: '100%' }} onClick={handleBackup}>
                📥 Download wineshop.db
              </button>
            </div>
          </div>

          {/* Danger Zone */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <div className="glass-card animate-fade-in" style={{ borderColor: 'var(--danger)' }}>
              <h2 className="text-danger">⚠️ Danger Zone</h2>
              <p className="text-muted" style={{ marginBottom: '2rem' }}>Irreversible destructive actions.</p>
              
              <div style={{ padding: '1.5rem', border: '1px solid rgba(217, 83, 79, 0.3)', borderRadius: '8px', marginBottom: '1.5rem' }}>
                <h3>🔥 Clear Inventory History (Keep Brands)</h3>
                <p style={{ fontSize: '0.9rem', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
                  Deletes all daily counts (Opening, Closing, Sold). Sales history is wiped, but Brands & Prices remain. Use for new financial years.
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                  <input type="checkbox" id="chkInv" checked={confirmInv} onChange={(e) => setConfirmInv(e.target.checked)} />
                  <label htmlFor="chkInv" style={{ color: 'var(--danger)', fontSize: '0.9rem' }}>I confirm I want to wipe inventory</label>
                </div>
                <button className="btn btn-danger" onClick={handleResetInventory}>Clear Inventory Data</button>
              </div>

              <div style={{ padding: '1.5rem', backgroundColor: 'rgba(217, 83, 79, 0.1)', border: '1px solid var(--danger)', borderRadius: '8px' }}>
                <h3 className="text-danger">💀 Factory Reset (Delete All)</h3>
                <p style={{ fontSize: '0.9rem', marginBottom: '1rem', color: 'var(--text-primary)' }}>
                  Deletes ALL Brand Names, Prices, and Inventory. The system will be completely empty.
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                  <input type="checkbox" id="chkAll" checked={confirmAll} onChange={(e) => setConfirmAll(e.target.checked)} />
                  <label htmlFor="chkAll" style={{ color: 'var(--danger)', fontWeight: 600, fontSize: '0.9rem' }}>I want to wipe EVERYTHING permanently</label>
                </div>
                <button className="btn btn-danger" style={{ width: '100%' }} onClick={handleResetAll}>Delete System Data</button>
              </div>
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}
