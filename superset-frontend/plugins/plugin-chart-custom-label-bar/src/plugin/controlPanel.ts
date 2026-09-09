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
  ControlPanelConfig,
  sharedControls,
  t,
  validateNonEmpty,
} from '../adapters/supersetAdapter';
import {
  DEFAULT_BAR_HEIGHT,
  DEFAULT_NUMBER_FORMAT,
  DEFAULT_ROW_LIMIT,
} from '../constants';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'groupby',
            config: {
              ...sharedControls.groupby,
              label: t('Dimension'),
              description: t('Column that produces one bar per value.'),
              multi: false,
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Metric'),
              description: t('Metric that sets each bar length.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['adhoc_filters'],
        [
          {
            name: 'row_limit',
            config: {
              ...sharedControls.row_limit,
              label: t('Number of bars'),
              description: t(
                'Top rows kept, ranked by the metric in descending order.',
              ),
              default: DEFAULT_ROW_LIMIT,
            },
          },
        ],
      ],
    },
    {
      label: t('Chart Options'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'barColor',
            config: {
              type: 'TextControl',
              label: t('Bar color'),
              default: null,
              description: t(
                'Hex color used for every bar. Leave empty to follow the theme primary color.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'barHeight',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('Bar thickness (px)'),
              default: DEFAULT_BAR_HEIGHT,
              description: t('Height of each horizontal bar in pixels.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'numberFormat',
            config: {
              type: 'TextControl',
              label: t('Value format'),
              default: DEFAULT_NUMBER_FORMAT,
              description: t(
                'D3 format string applied to the value shown beside each bar.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'valueSuffix',
            config: {
              type: 'TextControl',
              label: t('Value suffix'),
              default: '',
              description: t(
                'Text appended to every formatted value, for example a magnitude suffix.',
              ),
              renderTrigger: true,
            },
          },
        ],
      ],
    },
  ],
};

export default config;
