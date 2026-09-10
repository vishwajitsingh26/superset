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
import { QueryFormData } from './adapters/supersetAdapter';

export interface TileTablePanelStylesProps {
  width: number;
  height: number;
}

// Control names are snake_case because they double as form_data keys.
export interface TileTablePanelCustomizeProps {
  panel_title?: string;
  panel_info?: string;
  tile_chart_ids?: string | number[];
  table_title?: string;
  table_chart_id?: string | number | null;
  show_placeholder_tile?: boolean;
  placeholder_label?: string;
  placeholder_text?: string;
  accent_color?: string | null;
  dashboardId?: number;
}

export type TileTablePanelFormData = QueryFormData &
  TileTablePanelCustomizeProps;

export interface TileTablePanelProps extends TileTablePanelStylesProps {
  panelTitle: string;
  panelInfo: string;
  tileChartIds: number[];
  tableTitle: string;
  tableChartId: number | null;
  showPlaceholderTile: boolean;
  placeholderLabel: string;
  placeholderText: string;
  accentColor: string | null;
  dashboardId?: number;
}

export interface ChildChartProps {
  chartId: number;
  dashboardId?: number;
  width: number;
  height: number;
}

export interface EmbeddedChartState {
  id?: number;
  chartStatus?: string;
  chartAlert?: string | null;
  annotationData?: unknown;
  queriesResponse?: unknown;
  triggerQuery?: boolean;
  form_data?: Record<string, unknown>;
  queryController?: AbortController | null;
}

export interface EmbeddedSlice {
  slice_id: number;
  slice_name: string;
  viz_type: string;
}

export interface EmbeddedRootState {
  charts?: Record<number, EmbeddedChartState>;
  sliceEntities?: { slices?: Record<number, EmbeddedSlice> };
  datasources?: Record<string, unknown>;
  dataMask?: Record<string, { ownState?: unknown } | undefined>;
  dashboardInfo?: {
    common?: { conf?: { SUPERSET_WEBSERVER_TIMEOUT?: number } };
    crossFiltersEnabled?: boolean;
  };
  dashboardState?: { datasetsStatus?: 'loading' | 'error' | 'complete' };
}
