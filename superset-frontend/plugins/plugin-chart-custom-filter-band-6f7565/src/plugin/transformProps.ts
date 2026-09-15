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
  ChartProps,
  DataRecord,
  QueryFormColumn,
  SetDataMaskHook,
} from '../adapters/supersetAdapter';
import {
  CustomFilterBandFormData,
  CustomFilterBandProps,
  FilterSelection,
  FilterSlotConfig,
  FilterSlotKey,
} from '../types';
import { distinctValuesForType } from '../utils/filterOptions';

const DEFAULT_TYPE_COLUMN = 'filter_type';
const DEFAULT_VALUE_COLUMN = 'filter_value';

const SLOT_DEFAULTS: Record<
  FilterSlotKey,
  { typeKey: string; targetColumn: string; label: string }
> = {
  provider: {
    typeKey: 'provider',
    targetColumn: 'cloud_provider',
    label: 'All Cloud Providers',
  },
  account: {
    typeKey: 'account',
    targetColumn: 'account_name',
    label: 'All Accounts',
  },
  region: { typeKey: 'region', targetColumn: 'region', label: 'All Regions' },
  environment: {
    typeKey: 'environment',
    targetColumn: 'environment',
    label: 'All Environments',
  },
};

const SLOT_ORDER: FilterSlotKey[] = [
  'provider',
  'account',
  'region',
  'environment',
];

// A saved chart can hold an empty override in any of these text controls, so
// every read falls back to this slot's own default rather than throwing. The
// parameter is a plain dictionary rather than `CustomFilterBandFormData`
// itself: the value that reaches this helper from `transformProps` is not
// guaranteed to carry that type's required `datasource`/`viz_type` fields --
// only the dynamic `<slot><Field>` keys this function actually reads.
function readOverride(
  formData: Record<string, unknown>,
  key: FilterSlotKey,
  field: 'TypeKey' | 'TargetColumn' | 'Label',
): string | undefined {
  const name = `${key}${field}`;
  const value = formData[name];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

export default function transformProps(
  chartProps: ChartProps<CustomFilterBandFormData>,
): CustomFilterBandProps {
  const { width, height, queriesData, formData, hooks, filterState } =
    chartProps as ChartProps<CustomFilterBandFormData> & {
      hooks: { setDataMask?: SetDataMaskHook };
      filterState?: { value?: FilterSelection | null };
    };

  const data = (queriesData?.[0]?.data ?? []) as DataRecord[];
  const typeColumn: QueryFormColumn =
    formData.typeColumn || DEFAULT_TYPE_COLUMN;
  const valueColumn: QueryFormColumn =
    formData.valueColumn || DEFAULT_VALUE_COLUMN;

  const slots: FilterSlotConfig[] = SLOT_ORDER.map(key => {
    const fallback = SLOT_DEFAULTS[key];
    const typeKey = readOverride(formData, key, 'TypeKey') || fallback.typeKey;
    const targetColumn =
      readOverride(formData, key, 'TargetColumn') || fallback.targetColumn;
    const allLabel = readOverride(formData, key, 'Label') || fallback.label;

    return {
      key,
      allLabel,
      targetColumn,
      options: distinctValuesForType(data, typeColumn, valueColumn, typeKey),
    };
  });

  const selection: FilterSelection = filterState?.value ?? {
    provider: null,
    account: null,
    region: null,
    environment: null,
  };

  return {
    width: width ?? 800,
    height: height ?? 56,
    slots,
    selection,
    setDataMask: hooks?.setDataMask ?? (() => {}),
  };
}
