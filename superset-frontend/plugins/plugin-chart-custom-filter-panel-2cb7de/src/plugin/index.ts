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
  t,
} from '../adapters/supersetAdapter';
import buildQuery from './buildQuery';
import controlPanel from './controlPanel';
import transformProps from './transformProps';
import thumbnail from '../images/thumbnail';
import { FilterPanelFormData } from '../types';

const metadata = new ChartMetadata({
  name: t('Custom Filter Panel'),
  category: t('Custom Charts'),
  description: t(
    'A collapsed "Filter" button that sits in the dashboard grid and opens a ' +
      'panel of multi-select fields. Applying the panel pushes one IN filter ' +
      'per field to every other chart on the dashboard.',
  ),
  behaviors: [Behavior.NativeFilter, Behavior.InteractiveChart],
  tags: [t('Custom Charts'), t('Filter'), t('Dropdown'), t('Multi-Variables')],
  thumbnail,
  useLegacyApi: false,
  enableNoResults: false,
});

export default class CustomFilterPanelPlugin extends ChartPlugin<
  FilterPanelFormData,
  ChartProps<FilterPanelFormData>
> {
  constructor() {
    super({
      buildQuery,
      controlPanel,
      loadChart: () =>
        import('../components/FilterPanel').then(module => module.default),
      metadata,
      transformProps,
    });
  }
}
