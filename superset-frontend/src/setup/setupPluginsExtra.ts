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

import { CustomTextPlugin } from '@superset-ui/plugin-chart-custom-text';

import { CustomSearchFilterPlugin } from '@superset-ui/plugin-chart-custom-search-filter-6f7565';

import { CustomDateRangeFilterPlugin } from '@superset-ui/plugin-chart-custom-date-range-filter-6f7565';

import { CustomFilterBandPlugin } from '@superset-ui/plugin-chart-custom-filter-band-6f7565';

import { CustomKpiCardPlugin } from '@superset-ui/plugin-chart-custom-kpi-card-6f7565';

import { CustomSpendingTrendWrapperPlugin } from '@superset-ui/plugin-chart-custom-spending-trend-wrapper-6f7565';

import { CustomSpendingTrendChartPlugin } from '@superset-ui/plugin-chart-custom-spending-trend-chart-6f7565';

import { CustomDonutChartPlugin } from '@superset-ui/plugin-chart-custom-donut-chart-6f7565';

import { CustomTableWithBarPlugin } from '@superset-ui/plugin-chart-custom-table-with-bar-6f7565';

import { CustomCostByRegionWrapperPlugin } from '@superset-ui/plugin-chart-custom-cost-by-region-wrapper-6f7565';

import { CustomRegionMapPlugin } from '@superset-ui/plugin-chart-custom-region-map-6f7565';

import { CustomActivityFeedPlugin } from '@superset-ui/plugin-chart-custom-activity-feed-6f7565';

export default function setupPluginsExtra() {
  new CustomTextPlugin().configure({ key: 'custom_text' }).register();
  new CustomSearchFilterPlugin()
    .configure({ key: 'custom_search_filter' })
    .register();
  new CustomDateRangeFilterPlugin()
    .configure({ key: 'custom_date_range_filter' })
    .register();
  new CustomFilterBandPlugin()
    .configure({ key: 'custom_filter_band' })
    .register();
  new CustomKpiCardPlugin().configure({ key: 'custom_kpi_card' }).register();
  new CustomSpendingTrendWrapperPlugin()
    .configure({ key: 'custom_spending_trend_wrapper' })
    .register();
  new CustomSpendingTrendChartPlugin()
    .configure({ key: 'custom_spending_trend_chart' })
    .register();
  new CustomDonutChartPlugin()
    .configure({ key: 'custom_donut_chart' })
    .register();
  new CustomTableWithBarPlugin()
    .configure({ key: 'custom_table_with_bar' })
    .register();
  new CustomCostByRegionWrapperPlugin()
    .configure({ key: 'custom_cost_by_region_wrapper' })
    .register();
  new CustomRegionMapPlugin()
    .configure({ key: 'custom_region_map' })
    .register();
  new CustomActivityFeedPlugin()
    .configure({ key: 'custom_activity_feed' })
    .register();
}
