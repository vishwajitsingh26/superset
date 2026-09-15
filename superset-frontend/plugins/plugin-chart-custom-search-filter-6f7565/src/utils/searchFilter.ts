/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { ExtraFormData } from '../adapters/supersetAdapter';

// The three columns named in the region's own decision: account_name (r14 /
// dataset 310), service_name (r13 / dataset 309), region_name (r17 / dataset
// 311). Overridable through the control so a redeploy against different
// target charts does not require touching this file.
export const DEFAULT_SEARCH_COLUMNS = [
  'account_name',
  'service_name',
  'region_name',
];

export const DEFAULT_PLACEHOLDER = 'Search for accounts, services, regions...';

export function parseSearchColumns(
  raw: string | undefined,
  fallback: string[],
): string[] {
  if (!raw || !raw.trim()) return [...fallback];
  const parsed = raw
    .split(',')
    .map(c => c.trim())
    .filter(c => c.length > 0);
  return parsed.length > 0 ? parsed : [...fallback];
}

// One ILIKE clause per configured column, all in the single `filters` array
// a data mask carries. Superset appends this verbatim to every chart in this
// filter's scope -- see this plugin's review_notes for the scoping caveat
// that follows from that (a chart whose dataset lacks one of these columns
// will fail its query if it is in scope and receives this mask).
export function buildSearchExtraFormData(
  columns: string[],
  value: string,
): ExtraFormData {
  const trimmed = value.trim();
  if (!trimmed || columns.length === 0) {
    const empty: Record<string, unknown> = {};
    return empty as unknown as ExtraFormData;
  }
  const pattern = `%${trimmed}%`;
  const extra: Record<string, unknown> = {
    filters: columns.map(col => ({ col, op: 'ILIKE', val: pattern })),
  };
  return extra as unknown as ExtraFormData;
}
