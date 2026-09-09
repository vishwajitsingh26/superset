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
  QueryFormData,
  t,
} from '../adapters/supersetAdapter';
import buildQuery from './buildQuery';
import controlPanel from './controlPanel';
import transformProps from './transformProps';
import thumbnail from '../images/thumbnail.png';
import { PlatformFilterFormData } from '../types';

const metadata = new ChartMetadata({
  name: t('Custom Platform Filter'),
  category: t('Custom Charts'),
  description: t(
    'A full-width filter bar that lives in the dashboard grid: one categorical ' +
      'multi-select whose distinct values come from a column. An empty selection ' +
      'applies no filter, so every value is included by default.',
  ),
  behaviors: [Behavior.InteractiveChart, Behavior.NativeFilter],
  tags: [t('Custom Charts'), t('Filter'), t('Dropdown'), t('Categorical')],
  thumbnail,
  useLegacyApi: false,
  enableNoResults: false,
});

export default class CustomPlatformFilterPlugin extends ChartPlugin<
  PlatformFilterFormData,
  ChartProps<QueryFormData>
> {
  constructor() {
    super({
      buildQuery,
      controlPanel,
      loadChart: () =>
        import('../components/PlatformFilter').then(module => module.default),
      metadata,
      transformProps,
    });
  }
}
