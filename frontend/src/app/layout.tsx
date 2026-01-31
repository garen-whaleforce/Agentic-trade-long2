import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Rocket Screener',
  description: 'Earnings Call Analysis for Quantitative Trading',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="min-h-screen bg-gray-50">
          <header className="bg-white shadow-sm">
            <div className="max-w-7xl mx-auto px-4 py-4">
              <h1 className="text-2xl font-bold text-gray-900">
                🚀 Rocket Screener
              </h1>
              <p className="text-sm text-gray-500">
                Earnings Call Analysis for Quantitative Trading
              </p>
            </div>
          </header>
          <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
