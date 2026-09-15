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
import { DataRecord } from '../adapters/supersetAdapter';

export interface PivotResult {
  categories: string[];
  providers: string[];
  series: number[][];
}

// Runs once per data change in `transformProps`, never in the component.
// Providers sort alphabetically -- which happens to match the design's own
// legend order (AWS, Azure, Google Cloud, Oracle Cloud) without hardcoding
// any provider name, so a re-pointed dataset still orders sensibly.
export function buildSeries(
  data: DataRecord[],
  xAxisLabel: string | null,
  groupbyLabel: string | null,
  metricLabel: string | null,
): PivotResult {
  if (!data.length || !xAxisLabel || !groupbyLabel || !metricLabel) {
    return { categories: [], providers: [], series: [] };
  }

  const categorySet = new Set<string>();
  const providerSet = new Set<string>();
  const lookup = new Map<string, number>();

  data.forEach(row => {
    const rawX = row[xAxisLabel];
    const category = rawX === null || rawX === undefined ? '' : String(rawX);
    const provider = String(row[groupbyLabel] ?? '');
    const value = Number(row[metricLabel] ?? 0);
    if (!category || !provider) return;
    categorySet.add(category);
    providerSet.add(provider);
    lookup.set(`${category}__${provider}`, value);
  });

  const categories = Array.from(categorySet).sort(
    (a, b) => new Date(a).getTime() - new Date(b).getTime(),
  );
  const providers = Array.from(providerSet).sort((a, b) => a.localeCompare(b));

  const series = providers.map(provider =>
    categories.map(category => lookup.get(`${category}__${provider}`) ?? 0),
  );

  return { categories, providers, series };
}
