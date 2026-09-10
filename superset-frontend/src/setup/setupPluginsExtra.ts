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

// For individual deployments to add custom overrides

import { CustomSelectFilterPlugin } from '@superset-ui/plugin-chart-custom-select-filter-c1ed06';

import { CustomKpiCardPlugin } from '@superset-ui/plugin-chart-custom-kpi-card-c1ed06';

import { CustomRankedBarListPlugin } from '@superset-ui/plugin-chart-custom-ranked-bar-list-c1ed06';

import { CustomPeriodPickerPlugin } from '@superset-ui/plugin-chart-custom-period-picker-2cb7de';

import { CustomFilterPanelPlugin } from '@superset-ui/plugin-chart-custom-filter-panel-2cb7de';

import { CustomProviderSpendCardPlugin } from '@superset-ui/plugin-chart-custom-provider-spend-card-2cb7de';

import { CustomSpendTablePlugin } from '@superset-ui/plugin-chart-custom-spend-table-2cb7de';

import { CustomForecastLinePlugin } from '@superset-ui/plugin-chart-custom-forecast-line-2cb7de';

import { CustomTileTablePanelPlugin } from '@superset-ui/plugin-chart-custom-tile-table-panel-2cb7de';

export default function setupPluginsExtra() {
  new CustomSelectFilterPlugin().configure({ key: 'custom_select_filter' }).register();
  new CustomKpiCardPlugin().configure({ key: 'custom_kpi_card' }).register();
  new CustomRankedBarListPlugin().configure({ key: 'custom_ranked_bar_list' }).register();
  new CustomPeriodPickerPlugin().configure({ key: 'custom_period_picker' }).register();
  new CustomFilterPanelPlugin().configure({ key: 'custom_filter_panel' }).register();
  new CustomProviderSpendCardPlugin().configure({ key: 'custom_provider_spend_card' }).register();
  new CustomSpendTablePlugin().configure({ key: 'custom_spend_table' }).register();
  new CustomForecastLinePlugin().configure({ key: 'custom_forecast_line' }).register();
  new CustomTileTablePanelPlugin().configure({ key: 'custom_tile_table_panel' }).register();
}
