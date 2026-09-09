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
import {
  ControlPanelConfig,
  sharedControls,
} from '@superset-ui/chart-controls';

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
              multi: false,
              label: t('Category'),
              description: t('The dimension labelling each bar'),
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
              description: t('The value each bar is sized by'),
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
              label: t('Bars'),
              description: t(
                'How many bars to show. The database returns the highest values first.',
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
            name: 'card_title',
            config: {
              type: 'TextControl',
              label: t('Card title'),
              default: '',
              renderTrigger: true,
              description: t(
                'Title drawn inside the card. Leave empty when the dashboard ' +
                  'chart header already shows it.',
              ),
            },
          },
        ],
        [
          {
            name: 'bar_color',
            config: {
              type: 'TextControl',
              label: t('Bar colour'),
              renderTrigger: true,
              description: t(
                'Fill colour of every bar, as a CSS colour. Defaults to the ' +
                  'theme primary colour.',
              ),
            },
          },
        ],
        [
          {
            name: 'bar_thickness',
            config: {
              type: 'SliderControl',
              label: t('Bar thickness'),
              default: 12,
              min: 4,
              max: 32,
              step: 1,
              renderTrigger: true,
              description: t('Height of each bar in pixels'),
            },
          },
        ],
        [
          {
            name: 'number_format',
            config: {
              type: 'TextControl',
              label: t('Number format'),
              default: ',.0f',
              renderTrigger: true,
              description: t('d3-format string applied to the value label'),
            },
          },
        ],
        [
          {
            name: 'value_suffix',
            config: {
              type: 'TextControl',
              label: t('Value suffix'),
              default: '',
              renderTrigger: true,
              description: t(
                'Magnitude suffix appended after the formatted value, e.g. M',
              ),
            },
          },
        ],
        [
          {
            name: 'show_card_border',
            config: {
              type: 'CheckboxControl',
              label: t('Card border'),
              default: false,
              renderTrigger: true,
              description: t(
                'Draw a border around the card. Off by default because the ' +
                  'dashboard chart holder already draws one.',
              ),
            },
          },
        ],
      ],
    },
  ],
};

export default config;
