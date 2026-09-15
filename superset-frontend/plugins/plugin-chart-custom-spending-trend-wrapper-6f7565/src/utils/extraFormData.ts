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

// Shallow-merges two ExtraFormData objects, concatenating any array-valued
// keys so filters from multiple sources (native filters, cross-filters) all
// reach the hosted chart's query rather than the last one winning.
export function mergeExtraFormData(
  base: ExtraFormData,
  extra: ExtraFormData,
): ExtraFormData {
  const merged: ExtraFormData = { ...base };
  Object.entries(extra).forEach(([key, value]) => {
    const existing = merged[key];
    if (Array.isArray(existing) && Array.isArray(value)) {
      merged[key] = [...existing, ...value];
    } else {
      merged[key] = value;
    }
  });
  return merged;
}
