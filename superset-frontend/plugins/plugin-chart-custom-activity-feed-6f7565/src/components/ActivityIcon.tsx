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
import { SeverityKind } from '../types';

interface ActivityIconProps {
  severity: SeverityKind;
  size: number;
}

// Outline glyphs matching the dashboard's own icon style; each draws with
// `stroke="currentColor"` so the badge sets the colour exactly once.
function IconPath({ severity }: { severity: SeverityKind }) {
  if (severity === 'error') {
    return (
      <>
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </>
    );
  }
  if (severity === 'success') {
    return <polyline points="20 6 9 17 4 12" />;
  }
  return (
    <>
      <line x1="12" y1="16" x2="12" y2="11" />
      <line x1="12" y1="7.5" x2="12.01" y2="7.5" />
    </>
  );
}

export default function ActivityIcon({ severity, size }: ActivityIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      data-testid="activity-icon"
    >
      <IconPath severity={severity} />
    </svg>
  );
}
