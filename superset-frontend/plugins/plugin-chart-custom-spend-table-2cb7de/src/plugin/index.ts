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
import { SpendTableQueryFormData } from '../types';

export default class CustomSpendTablePlugin extends ChartPlugin<
  SpendTableQueryFormData,
  ChartProps<SpendTableQueryFormData>
> {
  constructor() {
    const metadata = new ChartMetadata({
      behaviors: [
        Behavior.InteractiveChart,
        Behavior.DrillToDetail,
        Behavior.DrillBy,
      ],
      category: t('Table'),
      description: t(
        'A card-framed table whose cells are drawn rather than written: a ' +
          'tinted month-over-month pill, a per-row sparkline, a share-of-total ' +
          'column and a shaded Total footer, with expandable child rows, ' +
          'per-column sorting and a built-in search box.',
      ),
      name: t('Custom Spend Table'),
      tags: [t('Table'), t('Trend'), t('Comparison'), t('CK Lens')],
      thumbnail,
      useLegacyApi: false,
      enableNoResults: false,
    });

    super({
      buildQuery,
      controlPanel,
      loadChart: () => import('../SpendTable'),
      metadata,
      transformProps,
    });
  }
}
