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
  DEFAULT_PERCENT_FORMAT,
  DEFAULT_ROW_LIMIT,
  DEFAULT_SUB_CAPTION,
  DEFAULT_VALUE_FORMAT,
} from '../utils/constants';

// Columns and metrics all arrive through standard controls, so repointing the
// chart at another dataset re-populates them without touching this plugin.
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
              label: t('Period'),
              description: t(
                'Time column that orders the sparkline. Its last point is the value shown.',
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['time_grain_sqla'],
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Value'),
              description: t(
                'Metric shown as the big number and plotted in the sparkline.',
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'deltaMetric',
            config: {
              ...sharedControls.metric,
              label: t('Change (percentage points)'),
              description: t(
                'Optional metric holding the change versus the previous period, stored as ' +
                  'percentage points (12.5 = 12.5%). Left blank, the change is derived from ' +
                  'the last two points of the series.',
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
              label: t('Row limit'),
              description: t('Number of periods fetched for the sparkline.'),
              default: DEFAULT_ROW_LIMIT,
            },
          },
        ],
      ],
    },
    {
      label: t('Card'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'cardLabel',
            config: {
              type: 'TextControl',
              label: t('Card label'),
              default: '',
              description: t(
                'Overrides the label beside the icon. Blank uses the metric name.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'iconGlyph',
            config: {
              type: 'SelectControl',
              label: t('Icon'),
              default: 'cloud',
              choices: [
                ['cloud', t('Cloud')],
                ['currency', t('Currency')],
                ['trend', t('Trend line')],
                ['server', t('Server')],
              ],
              clearable: false,
              freeForm: false,
              renderTrigger: true,
              description: t(
                'Glyph drawn in the accent colour to the left of the label.',
              ),
            },
          },
        ],
        [
          {
            name: 'subCaption',
            config: {
              type: 'TextControl',
              label: t('Caption under the change'),
              default: DEFAULT_SUB_CAPTION,
              renderTrigger: true,
              description: t('Small grey caption beneath the change figure.'),
            },
          },
        ],
        [
          {
            name: 'showSparkline',
            config: {
              type: 'CheckboxControl',
              label: t('Show sparkline'),
              default: true,
              renderTrigger: true,
              description: t(
                'Draws the series inline at the bottom-right of the card.',
              ),
            },
          },
        ],
      ],
    },
    {
      label: t('Formatting'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'valueFormat',
            config: {
              type: 'TextControl',
              label: t('Value format'),
              default: DEFAULT_VALUE_FORMAT,
              renderTrigger: true,
              description: t(
                'D3 format for the big number, e.g. $,.0f for $48,732.',
              ),
            },
          },
        ],
        [
          {
            name: 'percentFormat',
            config: {
              type: 'TextControl',
              label: t('Change format'),
              default: DEFAULT_PERCENT_FORMAT,
              renderTrigger: true,
              description: t(
                'D3 format for the change magnitude. The % sign is appended by the card, ' +
                  'so use ,.1f rather than .1%.',
              ),
            },
          },
        ],
        [
          {
            name: 'deltaSemantics',
            config: {
              type: 'SelectControl',
              label: t('Which direction is good?'),
              default: 'decrease_is_good',
              choices: [
                ['decrease_is_good', t('A decrease is favourable (cost)')],
                [
                  'increase_is_good',
                  t('An increase is favourable (savings, usage)'),
                ],
                ['neutral', t('Never colour by direction')],
              ],
              clearable: false,
              freeForm: false,
              renderTrigger: true,
              description: t(
                'Colours the arrow and the change figure by meaning rather than by sign, so a ' +
                  'fall in spend reads as favourable.',
              ),
            },
          },
        ],
      ],
    },
    {
      label: t('Colors'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'accentColor',
            config: {
              type: 'TextControl',
              label: t('Accent color'),
              default: '',
              renderTrigger: true,
              description: t(
                'Hex colour for the icon and the sparkline. Blank follows the theme primary colour.',
              ),
            },
          },
        ],
        [
          {
            name: 'favorableColor',
            config: {
              type: 'TextControl',
              label: t('Favourable change color'),
              default: '',
              renderTrigger: true,
              description: t(
                'Hex colour. Blank follows the theme success colour.',
              ),
            },
          },
        ],
        [
          {
            name: 'unfavorableColor',
            config: {
              type: 'TextControl',
              label: t('Unfavourable change color'),
              default: '',
              renderTrigger: true,
              description: t(
                'Hex colour. Blank follows the theme error colour.',
              ),
            },
          },
        ],
      ],
    },
  ],
};

export default config;
