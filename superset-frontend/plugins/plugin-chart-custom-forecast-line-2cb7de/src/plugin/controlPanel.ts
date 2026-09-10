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
import { DEFAULT_FORECAST_VALUE, DEFAULT_ROW_LIMIT } from '../constants';

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
              description: t('Column plotted along the horizontal axis.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['time_grain_sqla'],
        [
          {
            name: 'groupby',
            config: {
              ...sharedControls.groupby,
              label: t('Category'),
              description: t(
                'First column = one line per value. Second column = the ' +
                  'actual/forecast flag that decides which lines are dashed.',
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
              label: t('Value'),
              description: t('Value plotted on the vertical axis.'),
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
              default: DEFAULT_ROW_LIMIT,
            },
          },
        ],
      ],
    },
    {
      label: t('Forecast'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'forecastValue',
            config: {
              type: 'TextControl',
              label: t('Forecast flag value'),
              default: DEFAULT_FORECAST_VALUE,
              description: t(
                'Value in the second category column that marks a row as forecast.',
              ),
              renderTrigger: false,
            },
          },
        ],
        [
          {
            name: 'showDivider',
            config: {
              type: 'CheckboxControl',
              label: t('Show forecast divider'),
              default: true,
              description: t(
                'Draw a vertical dashed line where actual values end.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'seriesLabelSuffix',
            config: {
              type: 'TextControl',
              label: t('Series label suffix'),
              default: '',
              description: t('Appended to every legend entry, e.g. "Database".'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'forecastLabelSuffix',
            config: {
              type: 'TextControl',
              label: t('Forecast label suffix'),
              default: 'Forecast',
              description: t('Appended to legend entries of forecast series.'),
              renderTrigger: true,
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
            name: 'chartTitle',
            config: {
              type: 'TextControl',
              label: t('Card title'),
              default: '',
              description: t('Title shown in the card header.'),
              renderTrigger: true,
            },
          },
        ],
        ['currency_format'],
        [
          {
            name: 'showDecimals',
            config: {
              type: 'CheckboxControl',
              label: t('Show decimal values'),
              default: false,
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'showLegend',
            config: {
              type: 'CheckboxControl',
              label: t('Show legend'),
              default: true,
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'showScrollbar',
            config: {
              type: 'CheckboxControl',
              label: t('Show horizontal scrollbar'),
              default: true,
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'showViewToggle',
            config: {
              type: 'CheckboxControl',
              label: t('Show view switcher'),
              default: true,
              description: t('Line, area and list view buttons in the header.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'showTotalInTooltip',
            config: {
              type: 'CheckboxControl',
              label: t('Show total in tooltip'),
              default: true,
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'seriesColors',
            config: {
              type: 'TextControl',
              label: t('Series colors'),
              default: '',
              description: t(
                'Comma-separated colors, one per category, applied in legend ' +
                  'order. Left empty, the chart uses theme colors.',
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
