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
const MONTH_ABBR = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

// Accepts whatever the backend returned for a date column -- an ISO
// string, a timestamp number, or already-formatted text -- and normalises
// it to a plain YYYY-MM-DD string, or null if it cannot be read as a date.
export function toISODateString(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'string') {
    const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (match) return match[0];
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? null
      : parsed.toISOString().slice(0, 10);
  }
  if (typeof value === 'number') {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? null
      : parsed.toISOString().slice(0, 10);
  }
  return null;
}

// "Apr 1, 2025" -- built from the string's own digits rather than a Date
// object, so no timezone conversion can ever shift the day by one.
export function formatDisplayDate(iso: string | null): string | null {
  if (!iso) return null;
  const match = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return null;
  const [, year, month, day] = match;
  const monthIndex = Number(month) - 1;
  if (monthIndex < 0 || monthIndex > 11) return null;
  return `${MONTH_ABBR[monthIndex]} ${Number(day)}, ${year}`;
}

// Superset's `time_range` end is exclusive; the calendar's own end date is
// the last inclusive day of data, so the emitted range advances it by one.
export function addDaysISO(iso: string, days: number): string {
  const match = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return iso;
  const [, y, m, d] = match;
  const date = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
  date.setUTCDate(date.getUTCDate() + days);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}
