// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ZephyrexConfig } from 'zephyrex';
import { classroomExtension } from './extensions/classroom';

const config: ZephyrexConfig = {
  server: {
    baseUrl: process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:2100',
  },
  app: {
    name: 'Forgejo Classroom',
    description: 'GitHub-Classroom-equivalent for Forgejo',
    defaultTheme: 'dark',
  },
  auth: {
    privateRoutes: ['/classroom', '/settings', '/team'],
  },
  extensions: [classroomExtension],
};

export default config;
