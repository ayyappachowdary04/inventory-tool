import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { AuthProvider } from '@/context/AuthContext';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Wine Shop Manager',
  description: 'Premium inventory management for wine shops',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        {/* We need to ensure AuthProvider only runs on client to access localStorage or handle SSR properly. 
            A simple approach here uses a client wrapper, or simply renders children if we skip checking auth in layout. 
            AuthContext has "use client"; so it's a Client Component. */}
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
