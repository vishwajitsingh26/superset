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
// Extended from the seeded version with `Input` (the box itself), plus
// `ExtraFormData` and `SetDataMaskHook`, needed to push the cross-filter
// mask this widget emits on every keystroke. Every symbol the seeded file
// already exported is kept.
import {
  Behavior,
  ChartMetadata,
  ChartPlugin,
  buildQueryContext,
  getMetricLabel,
  getNumberFormatter,
  ensureIsArray,
  getColumnLabel,
} from '@superset-ui/core';
import type {
  ChartProps,
  DataRecord,
  ExtraFormData,
  QueryFormColumn,
  QueryFormData,
  QueryFormMetric,
  SetDataMaskHook,
} from '@superset-ui/core';
import {
  styled as styledComponent,
  useTheme as useThemeHook,
} from '@apache-superset/core/theme';
import { t as translate } from '@apache-superset/core/translation';
import { Input as InputComponent } from '@superset-ui/core/components';
import {
  sharedControls,
  getStandardizedControls,
} from '@superset-ui/chart-controls';
import type { ControlPanelConfig } from '@superset-ui/chart-controls';

export const styled = styledComponent;
export const useTheme = useThemeHook;
export const t = translate;
export const Input = InputComponent;

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
};

export type {
  ChartProps,
  ControlPanelConfig,
  DataRecord,
  ExtraFormData,
  QueryFormColumn,
  QueryFormData,
  QueryFormMetric,
  SetDataMaskHook,
};
