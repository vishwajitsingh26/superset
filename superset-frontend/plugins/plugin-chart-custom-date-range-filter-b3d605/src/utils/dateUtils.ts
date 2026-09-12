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
import { DataRecordValue } from '../adapters/supersetAdapter';
import { DateRangeValue } from '../types';

export const MONTH_LABELS = [
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

export const MONTH_FULL_LABELS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

export const WEEKDAY_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

// En dash, as the design draws it between the two dates.
export const RANGE_SEPARATOR = '\u2013';

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

export function isoFromParts(year: number, month: number, day: number): string {
  return `${year}-${pad(month + 1)}-${pad(day)}`;
}

function isoFromDate(date: Date): string {
  return isoFromParts(
    date.getUTCFullYear(),
    date.getUTCMonth(),
    date.getUTCDate(),
  );
}

export function dateFromIso(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

export function toIsoDate(value: DataRecordValue | undefined): string | null {
  if (value === null || value === undefined) return null;
  if (value instanceof Date) return isoFromDate(value);
  if (typeof value === 'number') return isoFromDate(new Date(value));
  const text = String(value).trim();
  if (!text) return null;
  const matched = /^(\d{4})-(\d{2})-(\d{2})/.exec(text);
  if (matched) return `${matched[1]}-${matched[2]}-${matched[3]}`;
  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : isoFromDate(parsed);
}

export function yearOf(iso: string): number {
  return Number(iso.slice(0, 4));
}

export function monthIndexOf(iso: string): number {
  return Number(iso.slice(5, 7)) - 1;
}

export function formatDisplayDate(iso: string): string {
  const month = MONTH_LABELS[monthIndexOf(iso)] ?? iso.slice(5, 7);
  return `${month} ${Number(iso.slice(8, 10))}, ${yearOf(iso)}`;
}

export function formatRangeLabel(range: DateRangeValue): string {
  return `${formatDisplayDate(range.start)} ${RANGE_SEPARATOR} ${formatDisplayDate(
    range.end,
  )}`;
}

export function nextDayIso(iso: string): string {
  const date = dateFromIso(iso);
  date.setUTCDate(date.getUTCDate() + 1);
  return isoFromDate(date);
}

export function addMonths(
  year: number,
  month: number,
  delta: number,
): { year: number; month: number } {
  const total = year * 12 + month + delta;
  return { year: Math.floor(total / 12), month: ((total % 12) + 12) % 12 };
}

export function firstOfMonthIso(year: number, month: number): string {
  return isoFromParts(year, month, 1);
}

export function lastOfMonthIso(year: number, month: number): string {
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return isoFromParts(year, month, lastDay);
}

// 7-column grid, leading and trailing blanks padded so weeks line up.
export function buildMonthCells(
  year: number,
  month: number,
): (string | null)[] {
  const offset = new Date(Date.UTC(year, month, 1)).getUTCDay();
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const cells: (string | null)[] = [];
  for (let blank = 0; blank < offset; blank += 1) cells.push(null);
  for (let day = 1; day <= daysInMonth; day += 1)
    cells.push(isoFromParts(year, month, day));
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

function clampIso(iso: string, min: string, max: string): string {
  if (iso < min) return min;
  if (iso > max) return max;
  return iso;
}

// A date outside the bounds returns nothing, so a selection is pulled back
// inside them rather than offered as an empty dashboard.
export function clampRangeToBounds(
  range: DateRangeValue | null | undefined,
  bounds: DateRangeValue | null,
): DateRangeValue | null {
  if (!range || !range.start || !range.end) return null;
  const ordered: DateRangeValue =
    range.start <= range.end
      ? { start: range.start, end: range.end }
      : { start: range.end, end: range.start };
  if (!bounds) return ordered;
  return {
    start: clampIso(ordered.start, bounds.start, bounds.end),
    end: clampIso(ordered.end, bounds.start, bounds.end),
  };
}
