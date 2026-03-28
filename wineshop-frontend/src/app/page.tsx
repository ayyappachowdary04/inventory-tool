'use client';
import { useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { postApi } from '@/lib/api';
import { Wine, Lock, User, Key, ArrowRight } from 'lucide-react';

export default function LoginPage() {
  const [role, setRole] = useState<'shopkeeper' | 'admin'>('shopkeeper');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { loginState } = useAuth();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const payload = role === 'admin' 
        ? { username, password, role: 'admin' }
        : { username: 'shopkeeper', password, role: 'shopkeeper' };
        
      const res = await postApi('/login', payload);
      
      if (res.success) {
        loginState(res.role, res.username);
      }
    } catch (err: any) {
      setError(err.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-wrapper" style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div className="glass-card animate-fade-in" style={{ width: '100%', maxWidth: '400px', padding: '2.5rem' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{ display: 'inline-flex', padding: '1rem', backgroundColor: 'rgba(139, 26, 47, 0.1)', borderRadius: '50%', marginBottom: '1rem' }}>
            <Wine size={48} color="var(--accent-gold)" />
          </div>
          <h1>Wine Shop Manager</h1>
          <p className="text-muted">Enter your credentials to continue</p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', backgroundColor: 'var(--bg-secondary)', padding: '0.25rem', borderRadius: '8px' }}>
          <button 
            type="button"
            onClick={() => setRole('shopkeeper')}
            style={{ flex: 1, padding: '0.5rem', border: 'none', background: role === 'shopkeeper' ? 'var(--glass-bg)' : 'transparent', color: role === 'shopkeeper' ? 'var(--text-primary)' : 'var(--text-secondary)', borderRadius: '6px', cursor: 'pointer', transition: 'all 0.2s' }}
          >
            Shopkeeper
          </button>
          <button 
            type="button"
            onClick={() => setRole('admin')}
            style={{ flex: 1, padding: '0.5rem', border: 'none', background: role === 'admin' ? 'var(--glass-bg)' : 'transparent', color: role === 'admin' ? 'var(--text-primary)' : 'var(--text-secondary)', borderRadius: '6px', cursor: 'pointer', transition: 'all 0.2s' }}
          >
            Admin
          </button>
        </div>

        {error && (
          <div style={{ padding: '0.75rem', backgroundColor: 'rgba(217, 83, 79, 0.1)', border: '1px solid var(--danger)', color: 'var(--danger)', borderRadius: '8px', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleLogin}>
          {role === 'admin' && (
            <div className="form-group">
              <label className="form-label">Username</label>
              <div style={{ position: 'relative' }}>
                <User size={18} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
                <input 
                  type="text" 
                  className="form-input" 
                  style={{ paddingLeft: '2.5rem' }}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter admin username"
                  required
                />
              </div>
            </div>
          )}

          <div className="form-group">
            <label className="form-label">{role === 'admin' ? 'Password' : 'PIN Code'}</label>
            <div style={{ position: 'relative' }}>
              <Lock size={18} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
              <input 
                type="password" 
                className="form-input" 
                style={{ paddingLeft: '2.5rem' }}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={role === 'admin' ? "Enter password" : "Enter shopkeeper PIN"}
                required
              />
            </div>
          </div>

          <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: '1rem' }} disabled={loading}>
            {loading ? 'Authenticating...' : 'Sign In'} <ArrowRight size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}
