import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });
const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
});

export const metadata: Metadata = {
  title: 'Contrarian Alpha',
  description: 'PEAD Reversal Strategy for Quantitative Trading',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} ${jetbrainsMono.variable}`}>
        <div className="min-h-screen bg-gray-50">
          <header className="bg-white shadow-sm">
            <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
              <div>
                <a href="/" className="text-2xl font-bold text-gray-900 hover:text-gray-700 transition-colors">
                  Contrarian Alpha
                </a>
                <p className="text-sm text-gray-500">
                  PEAD Reversal Strategy for Quantitative Trading
                </p>
              </div>
              <nav className="flex items-center gap-4">
                <a
                  href="/"
                  className="text-sm text-gray-600 hover:text-gray-900 transition-colors"
                >
                  Analysis
                </a>
                <a
                  href="/paper-trading"
                  className="text-sm text-gray-600 hover:text-gray-900 transition-colors font-medium"
                >
                  Paper Trading
                </a>
              </nav>
            </div>
          </header>
          <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
