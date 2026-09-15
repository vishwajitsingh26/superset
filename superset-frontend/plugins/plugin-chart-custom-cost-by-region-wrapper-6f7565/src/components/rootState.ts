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
// Narrow shape of the dashboard's redux store this wrapper reads from --
// only the slices a hosted chart needs to bootstrap and render, typed
// instead of cast so a renamed field fails at compile time, not at render.
import type { ChartState, ChartStatus, Datasource } from 'src/explore/types';
import type { JsonObject, QueryFormData } from '../adapters/supersetAdapter';

export interface ChartEntry {
  id: number;
  chartStatus?: ChartStatus;
  chartAlert?: string | null;
  chartStackTrace?: string | null;
  queriesResponse?: ChartState['queriesResponse'];
  triggerQuery?: boolean;
  annotationData?: JsonObject;
  latestQueryFormData?: QueryFormData;
  queryController?: AbortController | null;
}

export interface SliceEntry {
  slice_id: number;
  slice_name: string;
  viz_type: string;
}

export interface DataMaskEntry {
  ownState?: JsonObject;
  extraFormData?: JsonObject;
}

export interface RootState {
  charts: Record<number, ChartEntry>;
  sliceEntities?: { slices?: Record<number, SliceEntry> };
  datasources?: Record<string, Datasource>;
  dataMask?: Record<string, DataMaskEntry | undefined>;
  dashboardInfo?: {
    id?: number;
    common?: { conf?: { SUPERSET_WEBSERVER_TIMEOUT?: number } };
    crossFiltersEnabled?: boolean;
  };
  dashboardState?: { datasetsStatus?: 'loading' | 'error' | 'complete' };
}
