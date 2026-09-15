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
            name: 'groupby',
            config: {
              ...sharedControls.groupby,
              label: t('Category'),
              description: t('Column whose values become donut slices.'),
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
              description: t(
                'Metric that sizes each slice and the centre total.',
              ),
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
              label: t('Row limit'),
              default: 10,
              description: t('Maximum number of slices to display.'),
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
            name: 'centerLabel',
            config: {
              type: 'TextControl',
              label: t('Centre caption'),
              default: 'Total Spend',
              description: t(
                'Caption drawn beneath the total inside the donut.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'sliceColors',
            config: {
              type: 'TextControl',
              label: t('Slice colors'),
              default: '',
              description: t(
                'Comma-separated hex colors, one per slice in the order the ' +
                  'query returns them. Falls back to the theme palette when unset.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'numberFormat',
            config: {
              type: 'TextControl',
              label: t('Number format'),
              default: '$,.0f',
              description: t(
                'D3 format string for the centre total and tooltip values.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'percentFormat',
            config: {
              type: 'TextControl',
              label: t('Percent format'),
              default: '.1%',
              description: t(
                'D3 format string for the legend percentage column.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'tooltipEnabled',
            config: {
              type: 'CheckboxControl',
              label: t('Enable tooltip'),
              default: true,
              description: t('Show a tooltip with the slice value on hover.'),
              renderTrigger: true,
            },
          },
        ],
      ],
    },
  ],
};

export default config;
