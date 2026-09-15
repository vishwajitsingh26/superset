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
              label: t('Region'),
              description: t(
                'Column holding the region name, e.g. "US East (N. Virginia)".',
              ),
              multi: false,
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'metric',
            config: {
              ...sharedControls.metric,
              label: t('Spend'),
              description: t('Metric used to size each marker.'),
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
              default: 25,
            },
          },
        ],
      ],
    },
    {
      label: t('Markers'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'markerColor',
            config: {
              type: 'TextControl',
              label: t('Marker color'),
              description: t(
                'Hex color for every marker except the highlighted region. ' +
                  'Leave blank to use the theme primary color.',
              ),
              default: '',
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'highlightColor',
            config: {
              type: 'TextControl',
              label: t('Highlighted marker color'),
              description: t(
                'Hex color for the region matched below. Leave blank to use the theme error color.',
              ),
              default: '',
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'highlightMatch',
            config: {
              type: 'TextControl',
              label: t('Highlighted region'),
              description: t(
                'Region name (or part of it) to draw in the highlighted color, e.g. "Singapore".',
              ),
              default: 'Singapore',
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'sizeByMetric',
            config: {
              type: 'CheckboxControl',
              label: t('Size markers by spend'),
              default: true,
              renderTrigger: true,
            },
          },
        ],
      ],
    },
  ],
};

export default config;
