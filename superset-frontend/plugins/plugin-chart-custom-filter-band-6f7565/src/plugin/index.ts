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
import { CustomFilterBandFormData } from '../types';

export default class CustomFilterBandPlugin extends ChartPlugin<
  CustomFilterBandFormData,
  ChartProps<QueryFormData>
> {
  constructor() {
    const metadata = new ChartMetadata({
      behaviors: [Behavior.NativeFilter, Behavior.InteractiveChart],
      category: t('Filter'),
      description: t(
        'Four selects with no visible commit button; one component drives all four, applying each selection live as changed and pushing extraFormData per control.',
      ),
      name: t('Filter Band'),
      tags: [t('Custom Charts'), t('Generated')],
      thumbnail,
      useLegacyApi: false,
    });

    super({
      buildQuery,
      controlPanel,
      loadChart: () => import('../CustomFilterBand'),
      metadata,
      transformProps,
    });
  }
}
