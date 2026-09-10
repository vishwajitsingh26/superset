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
import { ChartProps } from '../adapters/supersetAdapter';
import { TileTablePanelFormData, TileTablePanelProps } from '../types';

function toId(value: unknown): number | null {
  const id = Number(value);
  return Number.isFinite(id) && id > 0 ? id : null;
}

function parseIds(raw: string | number[] | undefined): number[] {
  const parts = Array.isArray(raw) ? raw : String(raw ?? '').split(',');
  return parts
    .map(part => toId(typeof part === 'string' ? part.trim() : part))
    .filter((id): id is number => id !== null);
}

export default function transformProps(
  chartProps: ChartProps<TileTablePanelFormData>,
): TileTablePanelProps {
  const { width, height, formData } = chartProps;

  return {
    width: width ?? 0,
    height: height ?? 0,
    panelTitle: formData.panel_title ?? '',
    panelInfo: formData.panel_info ?? '',
    tileChartIds: parseIds(formData.tile_chart_ids),
    tableTitle: formData.table_title ?? '',
    tableChartId: toId(formData.table_chart_id),
    showPlaceholderTile: formData.show_placeholder_tile ?? false,
    placeholderLabel: formData.placeholder_label ?? '',
    placeholderText: formData.placeholder_text ?? '',
    accentColor: formData.accent_color ?? null,
    dashboardId: formData.dashboardId,
  };
}
