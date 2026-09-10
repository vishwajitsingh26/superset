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
import { ExtraFormData } from '../adapters/supersetAdapter';
import { FilterField, FilterPanelValue } from '../types';

export function hasSelection(selected: FilterPanelValue): boolean {
  return Object.values(selected).some(values => values.length > 0);
}

export function emptySelection(fields: FilterField[]): FilterPanelValue {
  const empty: FilterPanelValue = {};
  fields.forEach(field => {
    empty[field.column] = [];
  });
  return empty;
}

// One IN filter per field that has a selection. Every other chart on the
// dashboard receives these through the native-filter extraFormData channel.
export function buildFilterExtraFormData(
  selected: FilterPanelValue,
): ExtraFormData {
  const filters = Object.entries(selected)
    .filter(([column, values]) => column !== '' && values.length > 0)
    .map(([column, values]) => ({
      col: column,
      op: 'IN' as const,
      val: values,
    }));

  return (filters.length > 0 ? { filters } : {}) as ExtraFormData;
}

export function buildFilterLabel(
  selected: FilterPanelValue,
  fields: FilterField[],
): string {
  return fields
    .filter(field => (selected[field.column] ?? []).length > 0)
    .map(field => `${field.label}: ${selected[field.column].join(', ')}`)
    .join(' | ');
}

export function countActive(selected: FilterPanelValue): number {
  return Object.values(selected).filter(values => values.length > 0).length;
}
