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
// This plugin's single door onto Superset. No other file in the package
// imports `@superset-ui/*` or `@apache-superset/*` directly, so when an
// upstream module moves there is one line to change rather than twenty.
//
// Seeded, not owned: extend it with whatever else this plugin needs and
// return the whole file. The symbols below are the ones `src/plugin/index.ts`
// already imports, so removing one breaks the package. This copy adds the
// symbols the container archetype needs to host a saved chart by id.
import {
  Behavior,
  ChartMetadata,
  ChartPlugin,
  buildQueryContext,
  getMetricLabel,
  getNumberFormatter,
  ensureIsArray,
  getColumnLabel,
  SupersetClient,
} from '@superset-ui/core';
import type {
  ChartProps,
  DataRecord,
  JsonObject,
  QueryFormColumn,
  QueryFormData,
  QueryFormMetric,
  TimeGranularity,
} from '@superset-ui/core';
import { Empty } from '@superset-ui/core/components';
import {
  styled as styledComponent,
  useTheme as useThemeHook,
} from '@apache-superset/core/theme';
import { t as translate } from '@apache-superset/core/translation';
import {
  sharedControls,
  getStandardizedControls,
} from '@superset-ui/chart-controls';
import type { ControlPanelConfig } from '@superset-ui/chart-controls';

export const styled = styledComponent;
export const useTheme = useThemeHook;
export const t = translate;

export {
  Behavior,
  ChartMetadata,
  ChartPlugin,
  buildQueryContext,
  getMetricLabel,
  getNumberFormatter,
  ensureIsArray,
  getColumnLabel,
  sharedControls,
  getStandardizedControls,
  SupersetClient,
  Empty,
};

export type {
  ChartProps,
  ControlPanelConfig,
  DataRecord,
  JsonObject,
  QueryFormColumn,
  QueryFormData,
  QueryFormMetric,
  TimeGranularity,
};

// This wrapper's own alias: the shape of the extra-filter payload merged
// into the hosted chart's form data (native filters, cross-filters).
export type ExtraFormData = JsonObject;
