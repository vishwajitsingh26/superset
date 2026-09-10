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
import thumbnail from '../images/thumbnail.png';
import { CustomTextFormData } from '../types';

export default class CustomTextPlugin extends ChartPlugin<
  CustomTextFormData,
  ChartProps<CustomTextFormData>
> {
  constructor() {
    super({
      buildQuery,
      controlPanel,
      loadChart: () => import('../CustomText'),
      metadata: new ChartMetadata({
        behaviors: [Behavior.InteractiveChart],
        category: t('Text'),
        description: t(
          'Styled free text for a dashboard: headings, captions and callouts. ' +
            'Font size, weight, alignment and colour are set per chart, so one ' +
            'plugin serves any design without a new package.',
        ),
        name: t('Custom Text'),
        tags: [t('Text'), t('Layout')],
        thumbnail,
        useLegacyApi: false,
      }),
      transformProps,
    });
  }
}
