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
  DataRecord,
  getColumnLabel,
  QueryFormColumn,
} from '../adapters/supersetAdapter';

// The options dataset stores every dropdown's choices as (type, value) rows;
// this pulls out the distinct values belonging to one dropdown's type key.
export function distinctValuesForType(
  data: DataRecord[],
  typeColumn: QueryFormColumn,
  valueColumn: QueryFormColumn,
  typeKey: string,
): string[] {
  const typeLabel = getColumnLabel(typeColumn);
  const valueLabel = getColumnLabel(valueColumn);
  const seen = new Set<string>();

  data.forEach(row => {
    const rowType = row[typeLabel];
    if (rowType === undefined || rowType === null) return;
    if (String(rowType) !== typeKey) return;
    const value = row[valueLabel];
    if (value === undefined || value === null || String(value) === '') return;
    seen.add(String(value));
  });

  return Array.from(seen).sort((a, b) => a.localeCompare(b));
}
