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
import { MONTH_NAMES } from '../constants';
import { MonthOption } from '../types';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

export function getRowValue(
  row: Record<string, unknown>,
  key: string,
): unknown {
  if (key in row) return row[key];
  const lower = key.toLowerCase();
  const match = Object.keys(row).find(k => k.toLowerCase() === lower);
  return match ? row[match] : undefined;
}

export function toMonthKey(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  const date =
    typeof value === 'number' ? new Date(value) : new Date(String(value));
  if (Number.isNaN(date.getTime())) return null;
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}`;
}

export function monthLabel(key: string): string {
  const [year, month] = key.split('-');
  const name = MONTH_NAMES[Number(month) - 1] ?? key;
  return `${name} ${year}`;
}

function monthBounds(key: string): { start: string; endExclusive: string } {
  const [yearPart, monthPart] = key.split('-');
  const year = Number(yearPart);
  const month = Number(monthPart);
  const nextYear = month === 12 ? year + 1 : year;
  const nextMonth = month === 12 ? 1 : month + 1;
  return {
    start: `${year}-${pad(month)}-01`,
    endExclusive: `${nextYear}-${pad(nextMonth)}-01`,
  };
}

// Distinct months, newest first, so "latest" is always index 0.
export function buildMonthOptions(
  rows: Record<string, unknown>[],
  column: string,
): MonthOption[] {
  if (!column) return [];
  const keys = new Set<string>();
  rows.forEach(row => {
    const key = toMonthKey(getRowValue(row, column));
    if (key) keys.add(key);
  });
  return Array.from(keys)
    .sort()
    .reverse()
    .map(key => ({ key, label: monthLabel(key), ...monthBounds(key) }));
}
