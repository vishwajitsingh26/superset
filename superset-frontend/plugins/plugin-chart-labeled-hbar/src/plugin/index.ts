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
import { ChartMetadata, ChartPlugin } from '@superset-ui/core';
// In 6.x the translation helper `t` moved out of @superset-ui/core.
import { t } from '@apache-superset/core/translation';
import buildQuery from './buildQuery';
import controlPanel from './controlPanel';
import transformProps from './transformProps';
import thumbnail from '../images/thumbnail.png';

export default class SupersetPluginChartLabeledHbar extends ChartPlugin {
  constructor() {
    const metadata = new ChartMetadata({
      // The region declares no interactions, so no cross-filter behavior is
      // advertised. Add Behavior.InteractiveChart together with a setDataMask
      // implementation if cross-filtering is required later.
      behaviors: [],
      category: t('Ranking'),
      description: t(
        'Horizontal bars ranked by value on a shared left baseline. Each category name sits above its bar and the formatted value sits outside the right end of the bar. No axis, ticks, gridlines or legend.',
      ),
      name: t('Custom Labeled Horizontal Bar'),
      tags: [
        t('Bar'),
        t('Categorical'),
        t('Comparison'),
        t('Ranking'),
        t('Custom'),
      ],
      thumbnail,
      useLegacyApi: false,
    });

    super({
      buildQuery,
      controlPanel,
      loadChart: () => import('../LabeledHbar'),
      metadata,
      transformProps,
    });
  }
}
