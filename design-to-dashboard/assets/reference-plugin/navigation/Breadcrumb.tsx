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

import { memo, useCallback, useMemo } from "react";

// A navigation control does not filter anything on this dashboard -- it moves
// the *embedding* application to a different page or drill level. That is
// why it reaches for `window.parent.postMessage` here instead of
// `setDataMask`: `setDataMask` changes what other charts on this page query,
// which is the filter_widget mechanism, and is the wrong tool when nothing on
// this page is meant to react. A breadcrumb or drill header that also needs
// to filter its own dashboard combines both mechanisms; it does not use this
// one in place of that one.

export interface Crumb {
  // What the parent app navigates to when this crumb is clicked. Opaque to
  // this component -- it is passed straight through in the message.
  route: string;
  label: string;
}

interface BreadcrumbProps {
  width: number;
  height: number;
  crumbs: Crumb[];
}

const NAV_MESSAGE_TYPE = "superset-nav";

interface NavMessage {
  type: typeof NAV_MESSAGE_TYPE;
  route: string;
  label: string;
}

// Every embed has a different parent origin, and posting to the wrong one is
// silently dropped by the browser rather than raising an error -- resolving
// it from `document.referrer` is what makes the message actually arrive,
// instead of failing in a way nothing here would ever surface.
function resolveParentOrigin(): string {
  try {
    const { referrer } = document;
    if (referrer) {
      return new URL(referrer).origin;
    }
  } catch {
    // Malformed or absent referrer -- fall back below rather than throw.
  }
  return "*";
}

function Breadcrumb({ width, height, crumbs }: BreadcrumbProps) {
  const parentOrigin = useMemo(() => resolveParentOrigin(), []);

  const handleCrumbClick = useCallback(
    (index: number) => {
      const crumb = crumbs[index];
      if (!crumb) return;
      const message: NavMessage = {
        type: NAV_MESSAGE_TYPE,
        route: crumb.route,
        label: crumb.label,
      };
      window.parent.postMessage(message, parentOrigin);
    },
    [crumbs, parentOrigin],
  );

  if (crumbs.length === 0) {
    return <div style={{ width, height }} data-test="breadcrumb-empty" />;
  }

  const lastIndex = crumbs.length - 1;

  return (
    <nav
      aria-label="Breadcrumb navigation"
      style={{ width, height, display: "flex", alignItems: "center", gap: 4 }}
      data-test="breadcrumb-nav"
    >
      {crumbs.map((crumb, index) => {
        const isActive = index === lastIndex;
        return (
          <span key={crumb.route} style={{ display: "inline-flex", gap: 4 }}>
            {index > 0 && <span aria-hidden="true">/</span>}
            {isActive ? (
              // The current position is not a link -- there is nowhere left
              // to navigate to from here.
              <span aria-current="page">{crumb.label}</span>
            ) : (
              <span
                role="button"
                tabIndex={0}
                onClick={() => handleCrumbClick(index)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    handleCrumbClick(index);
                  }
                }}
                style={{ cursor: "pointer" }}
                aria-label={`Navigate to ${crumb.label}`}
              >
                {crumb.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}

export default memo(Breadcrumb);
