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

// The mechanism a `map` archetype plugin actually needs: Datamaps drawing a
// choropleth keyed by ISO alpha-3 country code, colored from a real Superset
// colour scheme. `datamaps` is already a dependency this Superset checkout
// carries -- Superset's own stock `legacy-plugin-chart-world-map` depends on
// it, and a `map` archetype plugin's generated `package.json` already lists
// it too. There is nothing to add; only to import.
import { useEffect, useMemo, useRef } from "react";
// @ts-ignore -- Datamaps ships no type declarations.
import Datamap from "datamaps/dist/datamaps.all.min";
import { getSequentialSchemeRegistry } from "@superset-ui/core";
import { useTheme } from "../adapters/supersetAdapter";
import { createProjection } from "./projection";

export interface CountryValue {
  // ISO alpha-3 (e.g. "USA", "IND") -- the id Datamaps' own world topology
  // keys its geographies by. A 2-letter or free-text country name will not
  // match any geography and silently renders as unfilled.
  countryCode: string;
  label: string;
  value: number;
}

interface ChoroplethProps {
  width: number;
  height: number;
  data: CountryValue[];
  colorScheme: string;
  valueLabel: string;
  formatValue: (value: number) => string;
}

function Choropleth({
  width,
  height,
  data,
  colorScheme,
  valueLabel,
  formatValue,
}: ChoroplethProps) {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<{ updateChoropleth: (d: unknown) => void } | null>(
    null,
  );

  const byCountry = useMemo(() => {
    const scheme = getSequentialSchemeRegistry().get(colorScheme);
    // An unregistered `colorScheme` id falls back to the theme's own palette
    // rather than a literal hex pair -- `check-custom-rules.js` rejects a
    // hard-coded colour, and the theme fallback stays correct if the theme
    // changes later.
    const colors = scheme?.colors ?? [theme.colorFillSecondary, theme.colorPrimary];
    const values = data.map((row) => row.value);
    const min = values.length > 0 ? Math.min(...values) : 0;
    const max = values.length > 0 ? Math.max(...values) : 1;
    const colorFn = buildColorScale(colors, min, max);

    const entries: Record<string, { fillColor: string; label: string; value: number }> =
      {};
    data.forEach((row) => {
      entries[row.countryCode] = {
        fillColor: colorFn(row.value),
        label: row.label,
        value: row.value,
      };
    });
    return entries;
  }, [data, colorScheme, theme]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    // Datamaps draws by mutating the DOM node it is given; re-instantiating
    // rather than reusing across data changes is what keeps a previous
    // render's SVG from lingering underneath the new one.
    element.innerHTML = "";

    const map = new Datamap({
      element,
      width,
      height,
      responsive: false,
      setProjection: (datamap: unknown) =>
        createProjection(datamap, width, height),
      data: byCountry,
      fills: { defaultFill: theme.colorFillSecondary },
      geographyConfig: {
        popupOnHover: true,
        highlightOnHover: true,
        borderWidth: 1,
        borderColor: theme.colorBgContainer,
        popupTemplate: (
          geo: { properties?: { name?: string } },
          countryDatum: { label?: string; value?: number } | undefined,
        ) => {
          if (!countryDatum) return "";
          const name = countryDatum.label ?? geo?.properties?.name ?? "";
          return `<div class="hoverinfo"><strong>${name}</strong><br/>${valueLabel}: ${formatValue(
            countryDatum.value ?? 0,
          )}</div>`;
        },
      },
    });
    map.updateChoropleth(byCountry);
    mapRef.current = map;

    return () => {
      element.innerHTML = "";
      mapRef.current = null;
    };
    // Re-running the whole effect on every data change is deliberate: Datamap
    // has no partial-update path for its projection or geography config, only
    // for the fill data, and this component's data volume (one point per
    // country) never makes that worth optimising around.
  }, [byCountry, width, height, valueLabel, formatValue, theme]);

  return <div ref={containerRef} style={{ width, height }} data-test="choropleth" />;
}

// Linear interpolation across a colour scheme's stops. Superset's own scheme
// registry hands back a fixed palette, not a continuous scale, and a
// choropleth needs one colour per data value, not per palette entry.
function buildColorScale(colors: string[], min: number, max: number) {
  const range = max - min || 1;
  return (value: number): string => {
    const t = Math.max(0, Math.min(1, (value - min) / range));
    const position = t * (colors.length - 1);
    const lowIndex = Math.floor(position);
    const highIndex = Math.min(lowIndex + 1, colors.length - 1);
    const weight = position - lowIndex;
    return mixHex(colors[lowIndex], colors[highIndex], weight);
  };
}

function mixHex(from: string, to: string, weight: number): string {
  const a = hexToRgb(from);
  const b = hexToRgb(to);
  const mix = (lo: number, hi: number) => Math.round(lo + (hi - lo) * weight);
  return `rgb(${mix(a.r, b.r)}, ${mix(a.g, b.g)}, ${mix(a.b, b.b)})`;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const normalized = hex.replace("#", "");
  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  };
}

export default Choropleth;
