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
import { KpiCardQueryFormData } from '../types';

export default class CustomKpiCardPlugin extends ChartPlugin<
  KpiCardQueryFormData,
  ChartProps<KpiCardQueryFormData>
> {
  constructor() {
    const metadata = new ChartMetadata({
      behaviors: [Behavior.InteractiveChart, Behavior.DrillToDetail],
      category: t('KPI'),
      description: t(
        'A single-value card: a small caption above one large left-aligned number, with an optional literal unit suffix for values that are already scaled.',
      ),
      name: t('Custom KPI Card'),
      tags: [t('Big Number'), t('Report'), t('Formattable')],
      thumbnail,
      useLegacyApi: false,
      enableNoResults: false,
    });

    super({
      buildQuery,
      controlPanel,
      loadChart: () => import('../KpiCard'),
      metadata,
      transformProps,
    });
  }
}
