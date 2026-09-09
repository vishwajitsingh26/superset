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
import { PieChartQueryFormData } from '../types';

export default class CustomPieChartPlugin extends ChartPlugin<
  PieChartQueryFormData,
  ChartProps<QueryFormData>
> {
  constructor() {
    const metadata = new ChartMetadata({
      behaviors: [
        Behavior.InteractiveChart,
        Behavior.DrillToDetail,
        Behavior.DrillBy,
      ],
      category: t('Part of a Whole'),
      description: t(
        'A CK Lens cost pie chart that displays cloud spend distribution across cloud providers with interactive drill-down.',
      ),
      name: t('CK Lens Pie Chart'),
      tags: [t('Categorical'), t('Comparison'), t('CK Lens'), t('Popular')],
      thumbnail,
      enableNoResults: false,
    });

    super({
      buildQuery,
      controlPanel,
      loadChart: () => import('../PieChart'),
      metadata,
      transformProps,
    });
  }
}
