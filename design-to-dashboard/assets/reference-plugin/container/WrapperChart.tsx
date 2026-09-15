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
// @ts-ignore – React is needed at runtime for JSX
import React, { FC, useMemo, useState } from "react";
import { Empty } from "@superset-ui/core/components";
import { styled, t } from "../adapters/supersetAdapter";
import { WrapperFilter, WrapperFilterValues, WrapperTab } from "./types";
import TabContent from "./TabContent";

// The prop shape `transformProps` produces and this component consumes.
// Kept here rather than in `types.ts` because it describes this component's
// interface, not the plugin's formData or the filter mechanism.
export interface WrapperChartProps {
  width: number;
  height: number;
  dashboardId?: number;
  tabs: WrapperTab[];
  wrapperFilters: WrapperFilter[];
  filterValues: WrapperFilterValues;
}

const Root = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
`;

const TabStrip = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.sizeUnit}px;
  padding: ${({ theme }) => theme.sizeUnit * 2}px;
  border-bottom: 1px solid ${({ theme }) => theme.colorBorderSecondary};
`;

const TabButton = styled.button<{ $active: boolean }>`
  border: none;
  background: ${({ $active, theme }) =>
    $active ? theme.colorPrimaryBg : "transparent"};
  color: ${({ $active, theme }) =>
    $active ? theme.colorPrimaryText : theme.colorText};
  padding: ${({ theme }) => theme.sizeUnit}px ${({ theme }) => theme.sizeUnit * 3}px;
  border-radius: ${({ theme }) => theme.borderRadius}px;
  cursor: pointer;
  font-weight: ${({ $active, theme }) =>
    $active ? theme.fontWeightStrong : theme.fontWeightNormal};
`;

const Centered = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
`;

const WrapperChart: FC<WrapperChartProps> = ({
  width,
  height,
  dashboardId,
  tabs,
  wrapperFilters,
  filterValues,
}) => {
  // Local state, not derived from props on every render: it is the viewer's
  // own selection, and re-deriving it would snap back to `tabs[0]` the
  // instant an unrelated prop (e.g. `width`, on a browser resize) changed.
  const [activeTabId, setActiveTabId] = useState<string | null>(
    tabs[0]?.id ?? null,
  );

  const activeTab = useMemo(
    () => tabs.find((tab) => tab.id === activeTabId) ?? tabs[0] ?? null,
    [tabs, activeTabId],
  );

  // The tab strip only earns its place once there is something to switch
  // between; a single tab renders as a plain hosted chart.
  const showTabStrip = tabs.length > 1;
  const tabStripHeight = showTabStrip ? 48 : 0;

  if (!activeTab) {
    return (
      <Root style={{ width, height }} data-test="wrapper-chart-root">
        <Centered>
          <Empty
            description={t(
              "No tabs configured. Open the control panel and add a tab.",
            )}
          />
        </Centered>
      </Root>
    );
  }

  return (
    <Root style={{ width, height }} data-test="wrapper-chart-root">
      {showTabStrip && (
        <TabStrip>
          {tabs.map((tab) => (
            <TabButton
              key={tab.id}
              type="button"
              $active={tab.id === activeTab.id}
              onClick={() => setActiveTabId(tab.id)}
              data-test={`wrapper-tab-button-${tab.id}`}
            >
              {tab.label}
            </TabButton>
          ))}
        </TabStrip>
      )}
      <TabContent
        key={activeTab.id}
        chartId={activeTab.chartId}
        dashboardId={dashboardId}
        width={width}
        height={height - tabStripHeight}
        isInView
        wrapperFilters={wrapperFilters}
        filterValues={filterValues}
      />
    </Root>
  );
};

export default WrapperChart;
