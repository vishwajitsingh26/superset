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
import { MAX_MONTH_OPTIONS, MONTH_LABELS } from '../constants';
import { MonthOption, Period } from '../types';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

// Accepts an epoch number or any parseable date string, which is what the
// MIN()/MAX() bounds query returns depending on the database driver.
export function parsePeriod(value: unknown): Period | null {
  if (value === null || value === undefined || value === '') return null;
  const date =
    typeof value === 'number' ? new Date(value) : new Date(String(value));
  if (Number.isNaN(date.getTime())) return null;
  return { month: date.getUTCMonth() + 1, year: date.getUTCFullYear() };
}

export function periodKey(period: Period): string {
  return `${period.year}-${pad(period.month)}`;
}

export function formatPeriod(period: Period): string {
  return `${MONTH_LABELS[period.month - 1]} ${period.year}`;
}

// Newest month first: the design shows the most recent month selected.
export function buildMonthOptions(min: Period, max: Period): MonthOption[] {
  const options: MonthOption[] = [];
  let { year, month } = min;
  while (
    (year < max.year || (year === max.year && month <= max.month)) &&
    options.length < MAX_MONTH_OPTIONS
  ) {
    const period = { month, year };
    options.push({
      ...period,
      value: periodKey(period),
      label: formatPeriod(period),
    });
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return options.reverse();
}
