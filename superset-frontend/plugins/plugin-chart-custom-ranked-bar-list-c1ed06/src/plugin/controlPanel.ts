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
  DEFAULT_DECIMAL_PLACES,
  DEFAULT_MAX_ITEMS,
  DEFAULT_VALUE_SUFFIX,
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
              label: t('Category'),
              multi: false,
              description: t('Column whose values label each bar.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Value'),
              description: t('Metric that sets each bar length.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['adhoc_filters'],
        [
          {
            name: 'maxItems',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('Number of bars'),
              default: DEFAULT_MAX_ITEMS,
              description: t(
                'How many top categories to show, ranked descending.',
              ),
              renderTrigger: false,
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
            name: 'chartTitle',
            config: {
              type: 'TextControl',
              label: t('Card title'),
              default: '',
              description: t(
                'Bold title drawn at the top left of the card. Leave blank to hide.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'barColor',
            config: {
              type: 'TextControl',
              label: t('Bar colour'),
              default: '',
              description: t(
                'Hex colour for every bar. Leave blank to use the theme primary colour.',
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
              default: DEFAULT_VALUE_SUFFIX,
              description: t(
                'Magnitude suffix appended to each value, for example M.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'decimalPlaces',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('Decimal places'),
              default: DEFAULT_DECIMAL_PLACES,
              description: t('Decimals shown in the value column.'),
              renderTrigger: true,
            },
          },
        ],
      ],
    },
  ],
};

export default config;
