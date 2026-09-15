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
  ControlPanelState,
  sharedControls,
  t,
  validateNonEmpty,
} from '../adapters/supersetAdapter';

function columnChoices(state: ControlPanelState): {
  choices: [string, string][];
} {
  return {
    choices: (state.datasource?.columns ?? []).map(col => [
      col.column_name,
      ('verbose_name' in col && col.verbose_name) || col.column_name,
    ]),
  };
}

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Query'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'titleColumn',
            config: {
              type: 'SelectControl',
              label: t('Title column'),
              description: t("Column holding each activity item's headline."),
              mapStateToProps: columnChoices,
              freeForm: false,
              validators: [validateNonEmpty],
            },
          },
        ],
        [
          {
            name: 'descriptionColumn',
            config: {
              type: 'SelectControl',
              label: t('Description column'),
              description: t(
                "Column holding each activity item's detail line.",
              ),
              mapStateToProps: columnChoices,
              freeForm: false,
              validators: [],
            },
          },
        ],
        [
          {
            name: 'severityColumn',
            config: {
              type: 'SelectControl',
              label: t('Severity column'),
              description: t(
                'Column whose value picks the badge icon and colour (error / info / success).',
              ),
              mapStateToProps: columnChoices,
              freeForm: false,
              validators: [],
            },
          },
        ],
        [
          {
            name: 'timestampColumn',
            config: {
              type: 'SelectControl',
              label: t('Timestamp column'),
              description: t(
                'Column holding the display text for when the activity happened. ' +
                  'Shown as literal text, never formatted as a date.',
              ),
              mapStateToProps: columnChoices,
              freeForm: false,
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
              description: t('Maximum number of activity items to display.'),
              default: 5,
            },
          },
        ],
      ],
    },
    {
      label: t('Header'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'viewAllLabel',
            config: {
              type: 'TextControl',
              label: t('Link label'),
              default: 'View all',
              description: t('Text for the header link.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'viewAllUrl',
            config: {
              type: 'TextControl',
              label: t('Link URL'),
              default: '',
              description: t(
                'Where the header link goes. Leave blank to show it with no destination.',
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
