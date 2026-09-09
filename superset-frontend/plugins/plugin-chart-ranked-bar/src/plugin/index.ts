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

export default class RankedBarChartPlugin extends ChartPlugin {
  constructor() {
    const metadata = new ChartMetadata({
      // The design specifies no interactions for this card, so the chart does
      // not emit cross-filters. Add Behavior.InteractiveChart together with a
      // setDataMask click handler if that requirement ever changes.
      behaviors: [],
      category: t('Ranking'),
      credits: [],
      description: t(
        'Ranked horizontal bars with the category label above each bar and the ' +
          'formatted value beside it. No axis, gridlines, ticks or legend, for ' +
          'compact "top N" cards where the labels are the axis.',
      ),
      name: t('Custom Ranked Bar'),
      tags: [t('Bar'), t('Categorical'), t('Comparison'), t('Ranking')],
      thumbnail,
      useLegacyApi: false,
    });

    super({
      buildQuery,
      controlPanel,
      loadChart: () => import('../RankedBar'),
      metadata,
      transformProps,
    });
  }
}
