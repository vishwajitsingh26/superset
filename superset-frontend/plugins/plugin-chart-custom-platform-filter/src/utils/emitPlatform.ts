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
import { DataMask, ExtraFormData } from '../adapters/supersetAdapter';

// An empty selection means "all platforms", so it emits no filter at all.
export function buildExtraFormData(
  column: string,
  values: string[],
): ExtraFormData {
  if (!column || values.length === 0) {
    return {};
  }
  return {
    filters: [{ col: column, op: 'IN', val: values }],
  } as ExtraFormData;
}

export function buildSelectionLabel(
  filterLabel: string,
  placeholder: string,
  values: string[],
): string {
  return `${filterLabel}: ${values.length > 0 ? values.join(', ') : placeholder}`;
}

export function buildPlatformDataMask(
  column: string,
  values: string[],
  filterLabel: string,
  placeholder: string,
): DataMask {
  return {
    extraFormData: buildExtraFormData(column, values),
    filterState: {
      value: values.length > 0 ? values : null,
      label: buildSelectionLabel(filterLabel, placeholder, values),
    },
  };
}
