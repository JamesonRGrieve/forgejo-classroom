// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import { ZephyrexRouter } from 'zephyrex';
import { use, type ReactNode } from 'react';

export default function CatchAll({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string[] }>;
  searchParams: Promise<Record<string, string>>;
}): ReactNode {
  return <ZephyrexRouter params={use(params)} searchParams={use(searchParams)} />;
}
