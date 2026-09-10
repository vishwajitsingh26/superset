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
  DEFAULT_RATE_FORMAT,
  DEFAULT_RATE_HOURS,
  DEFAULT_SHARE_FORMAT,
  DEFAULT_TIMESTAMP_FORMAT,
  DEFAULT_TREND_LABEL_FORMAT,
  DEFAULT_TREND_PERIODS,
  DEFAULT_VALUE_FORMAT,
} from '../constants';

const textControl = (
  name: string,
  label: string,
  description: string,
  defaultValue: string | number = '',
  isInt = false,
) => ({
  name,
  config: {
    type: 'TextControl',
    label,
    description,
    default: defaultValue,
    isInt,
    renderTrigger: true,
  },
});

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
              description: t('The spend value shown as the big number.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'shareTotalMetric',
            config: {
              ...sharedControls.metric,
              label: t('Share denominator'),
              description: t(
                'Optional total used for the "share of spend" line. Fetched alongside the value, no extra query.',
              ),
              validators: [],
            },
          },
        ],
        [
          {
            name: 'x_axis',
            config: {
              ...sharedControls.x_axis,
              label: t('Trend period'),
              description: t(
                'Column the sparkline is bucketed by. Latest bucket drives the value and the deltas.',
              ),
              validators: [validateNonEmpty],
            },
          },
        ],
        ['time_grain_sqla'],
        [
          {
            name: 'driverDimension',
            config: {
              ...sharedControls.entity,
              label: t('Cost driver'),
              description: t(
                'Dimension used for the "top cost driver" strip, e.g. the service name.',
              ),
              validators: [],
            },
          },
        ],
        ['adhoc_filters'],
        [
          textControl(
            'trendPeriods',
            t('Trend periods'),
            t('How many periods the sparkline shows.'),
            DEFAULT_TREND_PERIODS,
            true,
          ),
        ],
      ],
    },
    {
      label: t('Card'),
      expanded: true,
      controlSetRows: [
        [
          textControl(
            'cardLabel',
            t('Card label'),
            t('Heading shown at the top left of the card.'),
          ),
        ],
        [
          textControl(
            'logoUrl',
            t('Logo URL'),
            t('Optional image shown at the top right of the card.'),
          ),
        ],
        [
          textControl(
            'shareLabel',
            t('Share caption'),
            t('Text after the share percentage, e.g. "of Database Spend".'),
          ),
        ],
        [
          textControl(
            'driverLabel',
            t('Cost driver caption'),
            t('Bold text that opens the cost driver strip.'),
          ),
        ],
        [
          textControl(
            'trendCaption',
            t('Sparkline caption'),
            t('Small caption under the sparkline, e.g. "Last 6 Months".'),
          ),
        ],
        [
          textControl(
            'rateHours',
            t('Hours per period'),
            t('Divisor used for the hourly rate line.'),
            DEFAULT_RATE_HOURS,
            true,
          ),
        ],
      ],
    },
    {
      label: t('Formatting'),
      expanded: false,
      controlSetRows: [
        [
          textControl(
            'valueFormat',
            t('Value format'),
            t('D3 format for the big number, the delta and the driver amount.'),
            DEFAULT_VALUE_FORMAT,
          ),
        ],
        [
          textControl(
            'rateFormat',
            t('Rate format'),
            t('D3 format for the hourly rate.'),
            DEFAULT_RATE_FORMAT,
          ),
        ],
        [
          textControl(
            'percentFormat',
            t('Percent delta format'),
            t('D3 format for the percentage change.'),
            DEFAULT_PERCENT_FORMAT,
          ),
        ],
        [
          textControl(
            'shareFormat',
            t('Share format'),
            t('D3 format for the share percentage.'),
            DEFAULT_SHARE_FORMAT,
          ),
        ],
        [
          textControl(
            'trendLabelFormat',
            t('Trend label format'),
            t('D3 time format for sparkline period labels.'),
            DEFAULT_TREND_LABEL_FORMAT,
          ),
        ],
        [
          textControl(
            'timestampFormat',
            t('Last updated format'),
            t('D3 time format for the footer timestamp.'),
            DEFAULT_TIMESTAMP_FORMAT,
          ),
        ],
      ],
    },
    {
      label: t('Link'),
      expanded: false,
      controlSetRows: [
        [
          textControl(
            'linkLabel',
            t('Link label'),
            t('Footer link text, e.g. "AWS Lens".'),
          ),
        ],
        [
          textControl(
            'linkUrl',
            t('Link URL'),
            t('Target the footer link opens in a new tab.'),
          ),
        ],
      ],
    },
    {
      label: t('Colors'),
      expanded: false,
      controlSetRows: [
        [
          textControl(
            'accentColor',
            t('Sparkline color'),
            t(
              'Hex color for the sparkline line and fill. Leave blank to follow the theme primary color.',
            ),
          ),
        ],
      ],
    },
  ],
};

export default config;
