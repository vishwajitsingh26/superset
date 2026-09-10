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
import { DEFAULT_ROW_LIMIT, DEFAULT_VALUE_FORMAT } from '../constants';

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
              description: t(
                'Row dimensions. The first column is the top-level row; ' +
                  'an optional second column becomes the expandable child rows.',
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'providerColumn',
            config: {
              ...sharedControls.groupby,
              multi: false,
              label: t('Breakdown columns'),
              description: t(
                'Optional column whose values become one numeric column each ' +
                  '(for example one column per cloud provider).',
              ),
              validators: [],
            },
          },
        ],
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Value'),
              description: t('Metric shown in the value cells and totals.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'momMetric',
            config: {
              ...sharedControls.metric,
              label: t('Change %'),
              description: t(
                'Optional metric, already expressed as a percentage, rendered ' +
                  'as the tinted up/down pill.',
              ),
              default: null,
              validators: [],
            },
          },
        ],
        [
          {
            name: 'trendColumn',
            config: {
              ...sharedControls.groupby,
              multi: false,
              label: t('Trend over'),
              description: t(
                'Optional time column. When set, a second query draws one ' +
                  'sparkline per row over this column.',
              ),
              validators: [],
            },
          },
        ],
        ['adhoc_filters'],
        [
          {
            name: 'row_limit',
            config: {
              ...sharedControls.row_limit,
              default: DEFAULT_ROW_LIMIT,
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
            name: 'cardTitle',
            config: {
              type: 'TextControl',
              label: t('Card title'),
              default: '',
              description: t('Title drawn in the card header.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'showSearch',
            config: {
              type: 'CheckboxControl',
              label: t('Show search box'),
              default: true,
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'showPercentOfTotal',
            config: {
              type: 'CheckboxControl',
              label: t('Show % of Total column'),
              default: true,
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'showTotalRow',
            config: {
              type: 'CheckboxControl',
              label: t('Show Total footer row'),
              default: true,
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
              default: DEFAULT_VALUE_FORMAT,
              description: t('D3 format string used for every value cell.'),
              renderTrigger: true,
            },
          },
        ],
        ['currency_format'],
        [
          {
            name: 'accentColor',
            config: {
              type: 'ColorPickerControl',
              label: t('Sparkline colour'),
              default: null,
              description: t(
                'Colour of the trend sparkline. Falls back to the theme ' +
                  'primary colour when unset.',
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
