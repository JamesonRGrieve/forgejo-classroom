const path = require('path');
const frameworkDir = path.resolve(__dirname, '../../client-framework');

/** @type {import('next').NextConfig} */
module.exports = {
  output: 'standalone',
  typescript: { ignoreBuildErrors: true },
  transpilePackages: ['zephyrex', '@zephyrex/auth', '@zephyrex/zod2gql', '@jgrieve/forms'],
  turbopack: {
    root: path.resolve(__dirname, '../..'),
    resolveAlias: {
      '@/components': path.join(frameworkDir, 'src/components'),
      '@/lib': path.join(frameworkDir, 'src/lib'),
      '@/hooks': path.join(frameworkDir, 'src/hooks'),
      '@jgrieve/appwrapper': path.join(frameworkDir, 'src/components/appwrapper/src'),
    },
  },
};
