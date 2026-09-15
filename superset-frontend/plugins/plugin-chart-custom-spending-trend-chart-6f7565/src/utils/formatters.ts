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

// Built from `axis_formats`, not from a generic guess: x is a date drawn as
// "MMM D" (e.g. "Apr 1"), y is a number drawn as "$" + ",.0f" + "K", except
// the crop draws the zero tick as a bare "$0" with no K suffix.
const MONTHS = [
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

export function formatXAxisLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${MONTHS[date.getUTCMonth()]} ${date.getUTCDate()}`;
}

export function formatYAxisLabel(value: number): string {
  if (value === 0) return '$0';
  const scaled = value / 1000;
  const formatted = scaled.toLocaleString('en-US', {
    maximumFractionDigits: 0,
  });
  return `$${formatted}K`;
}
