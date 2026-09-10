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
import { t } from '../adapters/supersetAdapter';
import { formatDayLong } from './format';

export interface TooltipRow {
  axisValue: string | number;
  seriesName: string;
  value: number | null;
  color: string;
}

export interface TooltipColors {
  title: string;
  label: string;
  value: string;
  divider: string;
}

export interface TooltipOptions {
  totals: Record<string, number>;
  showTotal: boolean;
  money: (value: number) => string;
  colors: TooltipColors;
}

function swatch(color: string): string {
  return `<span style="width:8px;height:8px;border-radius:2px;background:${color};display:inline-block;flex-shrink:0"></span>`;
}

export default function createTooltipFormatter(
  options: TooltipOptions,
): (params: unknown) => string {
  const { colors, money } = options;
  return (params: unknown): string => {
    const rows = (Array.isArray(params) ? params : [params]) as TooltipRow[];
    const visible = rows.filter(
      row => row && row.value !== null && row.value !== undefined,
    );
    if (visible.length === 0) return '';

    const axisValue = Number(visible[0].axisValue);
    const head = `<div style="font-family:inherit;font-size:12px;font-weight:600;color:${colors.title};padding-bottom:8px">${formatDayLong(axisValue)}</div>`;

    const body = visible
      .map(
        row =>
          `<div style="display:flex;justify-content:space-between;align-items:center;gap:24px;font-size:11px;line-height:18px"><span style="display:flex;align-items:center;gap:6px;color:${colors.label}">${swatch(row.color)}${row.seriesName}</span><span style="color:${colors.value};font-weight:600;white-space:nowrap">${money(Number(row.value))}</span></div>`,
      )
      .join('');

    const total = options.totals[String(axisValue)];
    const totalRow =
      options.showTotal && total !== undefined
        ? `<div style="border-top:1px solid ${colors.divider};margin-top:8px;padding-top:8px;display:flex;justify-content:space-between;gap:24px;font-size:11px;line-height:18px"><span style="color:${colors.value};font-weight:600">${t('Total')}</span><span style="color:${colors.value};font-weight:600;white-space:nowrap">${money(total)}</span></div>`
        : '';

    return `${head}${body}${totalRow}`;
  };
}
