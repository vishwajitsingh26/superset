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

// The design groups digits the Indian way (2,34,502) in the tooltip total.
const GROUPING_LOCALE = 'en-IN';
const DATE_LOCALE = 'en-GB';

export function formatMoney(
  value: number,
  symbol: string,
  showDecimals: boolean,
): string {
  const digits = showDecimals ? 2 : 0;
  const amount = Number(value || 0).toLocaleString(GROUPING_LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${symbol}${amount}`;
}

export function formatAxis(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${Math.round(value / 1e9)}B`;
  if (abs >= 1e6) return `${Math.round(value / 1e6)}M`;
  if (abs >= 1e3) return `${Math.round(value / 1e3)}K`;
  return value === 0 ? '0K' : `${Math.round(value)}`;
}

export function formatDayAxis(time: number): string {
  const date = new Date(time);
  const day = date.toLocaleDateString(DATE_LOCALE, {
    day: '2-digit',
    timeZone: 'UTC',
  });
  const month = date.toLocaleDateString(DATE_LOCALE, {
    month: 'short',
    timeZone: 'UTC',
  });
  return `${day}\n${month}`;
}

export function formatDayLong(time: number): string {
  return new Date(time).toLocaleDateString(DATE_LOCALE, {
    day: '2-digit',
    month: 'long',
    timeZone: 'UTC',
  });
}

export function parseColorList(input?: string): string[] {
  if (!input) return [];
  return input
    .split(',')
    .map(entry => entry.trim())
    .filter(Boolean);
}
