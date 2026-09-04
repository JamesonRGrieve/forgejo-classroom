// SPDX-License-Identifier: AGPL-3.0-or-later
import { ZephyrexApp } from 'zephyrex';
import type { ReactNode } from 'react';
import config from '@/zephyrex.config';

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ZephyrexApp config={config}>
          {children}
        </ZephyrexApp>
      </body>
    </html>
  );
}
