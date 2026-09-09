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
import { validateNonEmpty } from '@superset-ui/core';
// In 6.x the translation helper `t` moved out of @superset-ui/core.
import { t } from '@apache-superset/core/translation';
import { ControlPanelConfig, sharedControls } from '@superset-ui/chart-controls';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'series',
            config: {
              ...sharedControls.entity,
              label: t('Category'),
              description: t(
                'The column whose values are drawn as the label above each bar',
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
              description: t('The measure that sets the length of each bar'),
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
              default: 5,
              description: t(
                'How many bars to draw. The query returns the highest values first, so this is the top-N cut.',
              ),
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
            name: 'header_text',
            config: {
              type: 'TextControl',
              default: '',
              renderTrigger: true,
              label: t('Header text'),
              description: t(
                'Optional heading rendered inside the chart. Leave empty when the dashboard card already shows the title.',
              ),
            },
          },
        ],
        [
          {
            name: 'number_format',
            config: {
              type: 'SelectControl',
              freeForm: true,
              default: ',.0f',
              renderTrigger: true,
              label: t('Value format'),
              choices: [
                [',.0f', '1,751'],
                [',.1f', '1,751.3'],
                [',.2f', '1,751.25'],
                [',d', '1,751 (integers only)'],
              ],
              description: t('d3 format string applied to the value label'),
            },
          },
        ],
        [
          {
            name: 'value_suffix',
            config: {
              type: 'TextControl',
              default: '',
              renderTrigger: true,
              label: t('Value suffix'),
              description: t(
                'Unit annotation appended to the formatted value, for example M when the data is already denominated in millions',
              ),
            },
          },
        ],
        [
          {
            name: 'bar_thickness',
            config: {
              type: 'SliderControl',
              default: 24,
              min: 8,
              max: 48,
              step: 1,
              renderTrigger: true,
              label: t('Bar height'),
              description: t('Height of each bar, in pixels'),
            },
          },
        ],
        [
          {
            name: 'bar_color',
            config: {
              type: 'TextControl',
              renderTrigger: true,
              label: t('Bar color'),
              description: t(
                'CSS color used as the flat fill for every bar. Defaults to ' +
                  'the theme primary color.',
              ),
            },
          },
        ],
      ],
    },
  ],
};

export default config;
