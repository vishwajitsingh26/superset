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
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Value'),
              description: t('The headline spend value of this card.'),
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'x_axis',
            config: {
              ...sharedControls.x_axis,
              label: t('Period'),
              description: t(
                'Column the trend is grouped by. Latest period is the headline value; the previous period drives the change.',
              ),
            },
          },
        ],
        [
          {
            name: 'share_metric',
            config: {
              ...sharedControls.metric,
              label: t('Share denominator'),
              description: t(
                'Optional. Total the headline value is expressed as a share of.',
              ),
              validators: [],
            },
          },
        ],
        [
          {
            name: 'rate_metric',
            config: {
              ...sharedControls.metric,
              label: t('Hourly rate'),
              description: t(
                'Optional. Rate shown in the sub-line. If unset it is derived from the value and Hours in period.',
              ),
              validators: [],
            },
          },
        ],
        [
          {
            name: 'driver_dimension',
            config: {
              ...sharedControls.groupby,
              label: t('Cost driver dimension'),
              multi: false,
              default: null,
              description: t(
                'Optional. Dimension whose top member is shown in the cost-driver strip.',
              ),
              validators: [],
            },
          },
        ],
        ['adhoc_filters'],
        [
          {
            name: 'sparkPeriods',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('Periods in trend'),
              default: 6,
              description: t('Number of periods fetched for the sparkline.'),
              renderTrigger: false,
            },
          },
        ],
      ],
    },
    {
      label: t('Card content'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'cardTitle',
            config: {
              type: 'TextControl',
              label: t('Card title'),
              default: '',
              renderTrigger: true,
              description: t('Heading shown at the top left of the card.'),
            },
          },
        ],
        [
          {
            name: 'logoUrl',
            config: {
              type: 'TextControl',
              label: t('Logo URL'),
              default: null,
              renderTrigger: true,
              description: t('Optional image shown at the top right.'),
            },
          },
        ],
        [
          {
            name: 'shareCaption',
            config: {
              type: 'TextControl',
              label: t('Share caption'),
              default: '',
              renderTrigger: true,
              description: t(
                'Text after the share percentage, e.g. "Database Spend".',
              ),
            },
          },
        ],
        [
          {
            name: 'rateCaption',
            config: {
              type: 'TextControl',
              label: t('Rate caption'),
              default: '/ hr',
              renderTrigger: true,
              description: t('Suffix after the hourly rate.'),
            },
          },
        ],
        [
          {
            name: 'hoursInPeriod',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('Hours in period'),
              default: 730,
              renderTrigger: true,
              description: t(
                'Used to derive the hourly rate when no rate metric is set.',
              ),
            },
          },
        ],
        [
          {
            name: 'sparkCaption',
            config: {
              type: 'TextControl',
              label: t('Trend caption'),
              default: 'Last 6 Months',
              renderTrigger: true,
              description: t('Caption under the sparkline.'),
            },
          },
        ],
        [
          {
            name: 'driverLabel',
            config: {
              type: 'TextControl',
              label: t('Cost driver label'),
              default: 'Top Cost Driver',
              renderTrigger: true,
              description: t('Prefix of the cost-driver strip.'),
            },
          },
        ],
        [
          {
            name: 'linkLabel',
            config: {
              type: 'TextControl',
              label: t('Footer link label'),
              default: null,
              renderTrigger: true,
              description: t('Outbound link shown at the bottom right.'),
            },
          },
        ],
        [
          {
            name: 'linkUrl',
            config: {
              type: 'TextControl',
              label: t('Footer link URL'),
              default: null,
              renderTrigger: true,
              description: t('Target of the footer link.'),
            },
          },
        ],
      ],
    },
    {
      label: t('Formatting'),
      expanded: false,
      controlSetRows: [
        [
          {
            name: 'valueFormat',
            config: {
              type: 'TextControl',
              label: t('Value format'),
              default: '$,.0f',
              renderTrigger: true,
              description: t('D3 format for the headline and driver values.'),
            },
          },
        ],
        [
          {
            name: 'deltaFormat',
            config: {
              type: 'TextControl',
              label: t('Change format'),
              default: '$,.0f',
              renderTrigger: true,
              description: t('D3 format for the absolute change.'),
            },
          },
        ],
        [
          {
            name: 'percentFormat',
            config: {
              type: 'TextControl',
              label: t('Percent change format'),
              default: '.2f',
              renderTrigger: true,
              description: t('D3 format for the percentage change.'),
            },
          },
        ],
        [
          {
            name: 'shareFormat',
            config: {
              type: 'TextControl',
              label: t('Share format'),
              default: '.0f',
              renderTrigger: true,
              description: t('D3 format for the share percentage.'),
            },
          },
        ],
        [
          {
            name: 'rateFormat',
            config: {
              type: 'TextControl',
              label: t('Rate format'),
              default: '$,.2f',
              renderTrigger: true,
              description: t('D3 format for the hourly rate.'),
            },
          },
        ],
        [
          {
            name: 'accentColor',
            config: {
              type: 'TextControl',
              label: t('Accent color'),
              default: null,
              renderTrigger: true,
              description: t(
                'Hex color for the sparkline, e.g. #7EC8F0. Falls back to the theme primary color when empty.',
              ),
            },
          },
        ],
      ],
    },
  ],
};

export default config;
