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
  Currency,
  CurrencyFormatter,
  getNumberFormatter,
} from '../adapters/supersetAdapter';
import { MISSING, MOM_DECIMALS, PCT_DECIMALS } from '../constants';
import { ColorValue, NullableNumber } from '../types';

export type ValueFormatter = (value: NullableNumber) => string;

export function makeValueFormatter(
  format: string,
  currency?: Currency,
): ValueFormatter {
  const formatter = currency?.symbol
    ? new CurrencyFormatter({ currency, d3Format: format })
    : getNumberFormatter(format);
  return (value: NullableNumber) =>
    value === null || value === undefined || !Number.isFinite(value)
      ? MISSING
      : formatter(value);
}

export function formatSignedPercent(value: NullableNumber): string {
  if (value === null || !Number.isFinite(value)) return MISSING;
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(MOM_DECIMALS)}%`;
}

export function formatShare(value: NullableNumber): string {
  if (value === null || !Number.isFinite(value)) return MISSING;
  return `${value.toFixed(PCT_DECIMALS)}%`;
}

const channel = (component: number): string =>
  Math.max(0, Math.min(255, Math.round(component))).toString(16).padStart(2, '0');

// Accepts either a saved colour string or a ColorPickerControl value; returns
// undefined so the caller can fall back to a theme token.
export function resolveColor(color?: ColorValue): string | undefined {
  if (!color) return undefined;
  if (typeof color === 'string') {
    return color.trim() ? color.trim() : undefined;
  }
  if (
    Number.isFinite(color.r) &&
    Number.isFinite(color.g) &&
    Number.isFinite(color.b)
  ) {
    return `#${channel(color.r)}${channel(color.g)}${channel(color.b)}`;
  }
  return undefined;
}
