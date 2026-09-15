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

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'x_axis',
            config: {
              ...sharedControls.x_axis,
              label: t('Date'),
              description: t('Temporal column the trend is plotted against.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'groupby',
            config: {
              ...sharedControls.groupby,
              label: t('Provider'),
              description: t(
                'Column identifying each stacked series (e.g. cloud provider).',
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Spend'),
              description: t('Metric plotted as the stacked area value.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['adhoc_filters'],
        [
          {
            name: 'grain',
            config: {
              type: 'SelectControl',
              label: t('Time Grain'),
              description: t(
                'Aggregation period for the trend: Daily, Weekly or Monthly.',
              ),
              default: 'P1D',
              clearable: false,
              renderTrigger: false,
              choices: [
                ['P1D', t('Daily')],
                ['P1W', t('Weekly')],
                ['P1M', t('Monthly')],
              ],
            },
          },
        ],
        [
          {
            name: 'row_limit',
            config: {
              ...sharedControls.row_limit,
              default: 1000,
            },
          },
        ],
      ],
    },
    {
      label: t('Customize'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'seriesColors',
            config: {
              type: 'TextControl',
              label: t('Series Colors'),
              default: '',
              description: t(
                'Comma-separated hex colors, one per series, assigned in alphabetical ' +
                  'order of the series name. Falls back to the theme palette when unset.',
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
