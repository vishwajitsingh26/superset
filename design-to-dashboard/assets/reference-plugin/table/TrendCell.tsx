/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

import React from "react";
import { useTheme } from "../../adapters/supersetAdapter";
import Sparkline from "../Sparkline";
import TrendUpSvg from "../../assets/TrendUp.svg";
import TrendDownSvg from "../../assets/TrendDown.svg";
import TrendSteadySvg from "../../assets/TrendSteady.svg";
import { classifyTrend, TREND_LABELS } from "../../utils/trend";

// Sparkline with trend icon and label.
const TrendCell: React.FC<{
  series: [number, number][];
  pct: number | null;
}> = ({ series, pct }) => {
  const theme = useTheme();
  const trend = classifyTrend(series);
  const TrendIcon =
    trend === "accelerating"
      ? TrendUpSvg
      : trend === "slight_dip"
        ? TrendDownSvg
        : TrendSteadySvg;
  return (
    <span
      style={{
        display: "flex",
        alignItems: "center",
        width: "100%",
        gap: 4,
      }}
    >
      <span style={{ width: 72, flexShrink: 0 }}>
        <Sparkline data={series} positive={pct !== null && pct >= 0} />
      </span>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          whiteSpace: "nowrap",
        }}
      >
        <TrendIcon width={12} height={12} style={{ flexShrink: 0 }} />
        <span
          style={{
            fontFamily: "Inter, sans-serif",
            fontSize: 10,
            fontWeight: 400,
            lineHeight: "16px",
            letterSpacing: "0%",
            color: theme.colorText,
          }}
        >
          {TREND_LABELS[trend]}
        </span>
      </span>
    </span>
  );
};

export default TrendCell;
