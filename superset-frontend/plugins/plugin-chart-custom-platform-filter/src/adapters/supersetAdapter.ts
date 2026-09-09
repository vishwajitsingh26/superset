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
  Behavior,
  ChartMetadata,
  ChartPlugin,
  ChartProps,
  DataMask,
  DataRecord,
  ExtraFormData,
  QueryFormColumn,
  QueryFormData,
  SetDataMaskHook,
  buildQueryContext,
  ensureIsArray,
  getColumnLabel,
  validateNonEmpty,
} from '@superset-ui/core';

// Superset 6.1 moved these out of @superset-ui/core. This barrel is exactly
// why: call sites never change, only this file does.
import {
  styled as styledComponent,
  useTheme as useThemeHook,
} from '@apache-superset/core/theme';
import { t as translate } from '@apache-superset/core/translation';
import { Select as SelectComponent } from '@superset-ui/core/components';
import {
  ControlPanelConfig,
  sharedControls,
} from '@superset-ui/chart-controls';

export const styled = styledComponent;
export const useTheme = useThemeHook;
export const t = translate;
export const Select = SelectComponent;

export type {
  ChartProps,
  DataMask,
  DataRecord,
  ExtraFormData,
  QueryFormColumn,
  QueryFormData,
  SetDataMaskHook,
  ControlPanelConfig,
};

export {
  Behavior,
  ChartMetadata,
  ChartPlugin,
  buildQueryContext,
  ensureIsArray,
  getColumnLabel,
  validateNonEmpty,
  sharedControls,
};
