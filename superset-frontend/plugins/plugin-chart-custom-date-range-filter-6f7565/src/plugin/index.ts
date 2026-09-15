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
  t,
  Behavior,
  ChartMetadata,
  ChartPlugin,
  ChartProps,
  QueryFormData,
} from '../adapters/supersetAdapter';
import buildQuery from './buildQuery';
import controlPanel from './controlPanel';
import transformProps from './transformProps';
import thumbnail from '../images/thumbnail.png';
import { CustomDateRangeFilterFormData } from '../types';

export default class CustomDateRangeFilterPlugin extends ChartPlugin<
  CustomDateRangeFilterFormData,
  ChartProps<QueryFormData>
> {
  constructor() {
    const metadata = new ChartMetadata({
      behaviors: [Behavior.NativeFilter, Behavior.InteractiveChart],
      category: t('Filter'),
      description: t(
        'Date-range controls are always a filter_widget bound to the range_start/range_end view, so the calendar is bounded to the data’s real min/max date rather than…',
      ),
      name: t('Date Range Filter'),
      tags: [t('Custom Charts'), t('Generated')],
      thumbnail,
      useLegacyApi: false,
    });

    super({
      buildQuery,
      controlPanel,
      loadChart: () => import('../CustomDateRangeFilter'),
      metadata,
      transformProps,
    });
  }
}
