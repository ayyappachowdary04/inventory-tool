import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, CheckSquare, PackagePlus, Tags, Settings, LogOut, Wine } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

export default function Sidebar() {
  const pathname = usePathname();
  const { session, logout } = useAuth();
  
  if (!session.role) return null;

  const adminLinks = [
    { href: '/admin', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/admin/approvals', label: 'Approvals', icon: CheckSquare },
    { href: '/admin/intake', label: 'Stock Intake', icon: PackagePlus },
    { href: '/admin/brands', label: 'Brand Manager', icon: Tags },
    { href: '/admin/settings', label: 'Settings', icon: Settings },
  ];

  const shopkeeperLinks = [
    { href: '/shopkeeper', label: 'Daily Wizard', icon: LayoutDashboard },
  ];

  const links = session.role === 'admin' ? adminLinks : shopkeeperLinks;

  return (
    <div className="sidebar animate-fade-in" style={{ height: '100vh', position: 'sticky', top: 0 }}>
      <div style={{ padding: '0 1rem 2rem' }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0, fontSize: '1.25rem', color: 'var(--text-primary)' }}>
          <Wine size={24} color="var(--accent-gold)" />
          Wine Manager
        </h2>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginLeft: '2rem' }}>
          {session.role.toUpperCase()}
        </span>
      </div>

      <nav style={{ flex: 1 }}>
        {links.map((link) => {
          const Icon = link.icon;
          const isActive = pathname === link.href;
          return (
            <Link 
              key={link.href} 
              href={link.href} 
              className={`sidebar-link ${isActive ? 'active' : ''}`}
            >
              <Icon size={20} />
              {link.label}
            </Link>
          );
        })}
      </nav>

      <div style={{ marginTop: 'auto', borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
        <button 
          onClick={logout} 
          className="sidebar-link" 
          style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', color: 'var(--danger)' }}
        >
          <LogOut size={20} />
          Logout
        </button>
      </div>
    </div>
  );
}
