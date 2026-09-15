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
import { DEFAULT_TREND_PERIODS } from '../utils/constants';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Value'),
              description: t('The measure shown as the headline figure.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['granularity_sqla'],
        ['time_range'],
        ['time_grain_sqla'],
        ['adhoc_filters'],
        [
          {
            name: 'trendPeriods',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('Trend periods'),
              default: DEFAULT_TREND_PERIODS,
              description: t(
                'Number of periods, at the selected time grain, fetched for the ' +
                  'background sparkline and the period-over-period comparison. At least 2.',
              ),
            },
          },
        ],
      ],
    },
    {
      label: t('Display'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'label',
            config: {
              type: 'TextControl',
              label: t('Label'),
              default: '',
              description: t(
                'Text drawn next to the icon. Falls back to the metric name.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'icon',
            config: {
              type: 'TextControl',
              label: t('Icon'),
              default: 'cloud',
              description: t(
                'One of cloud, compute, storage, network -- or a URL to a custom image, ' +
                  'for a brand mark none of those cover.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'accentColor',
            config: {
              type: 'TextControl',
              label: t('Accent color'),
              default: '',
              description: t(
                "Hex color driving the icon, the sparkline and the card's tint. " +
                  'Falls back to the theme primary color when unset.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'valueFormat',
            config: {
              type: 'TextControl',
              label: t('Value format'),
              default: '$,.0f',
              description: t('A d3-format string for the headline value.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'comparisonSuffix',
            config: {
              type: 'TextControl',
              label: t('Comparison caption'),
              default: 'vs. last month',
              description: t('Caption drawn under the delta percentage.'),
              renderTrigger: true,
            },
          },
        ],
      ],
    },
  ],
};

export default config;
