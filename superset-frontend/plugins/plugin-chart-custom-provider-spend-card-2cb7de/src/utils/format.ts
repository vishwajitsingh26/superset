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
import {
  DataRecordValue,
  getTimeFormatter,
} from '../adapters/supersetAdapter';

export function toNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function formatTemporal(
  value: DataRecordValue | undefined,
  format: string,
): string {
  if (value === null || value === undefined) {
    return '';
  }
  const date =
    value instanceof Date
      ? value
      : new Date(typeof value === 'number' ? value : String(value));
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return getTimeFormatter(format)(date);
}

export function signedLabel(
  value: number,
  formatter: (input: number) => string,
): string {
  const sign = value >= 0 ? '+' : '-';
  return `${sign}${formatter(Math.abs(value))}`;
}
