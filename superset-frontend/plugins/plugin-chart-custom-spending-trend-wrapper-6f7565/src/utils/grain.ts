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
import { SpendingTrendView } from '../types';
import { TimeGranularity } from '../adapters/supersetAdapter';

// Maps the card's own Daily/Weekly/Monthly toggle onto the standard Superset
// time-grain values, so it can override the hosted chart's `time_grain_sqla`
// without either side needing to know the other's control names. Typed as
// `TimeGranularity` (not a bare string) so it flows into `ChartContainer`'s
// `formData` — typed as `SqlaFormData` — without a cast at the call site.
const GRAIN_BY_VIEW: Record<SpendingTrendView, TimeGranularity> = {
  Daily: 'P1D',
  Weekly: 'P1W',
  Monthly: 'P1M',
};

export function viewToGrain(view: SpendingTrendView): TimeGranularity {
  return GRAIN_BY_VIEW[view];
}
