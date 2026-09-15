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
import { styled, useTheme } from '../adapters/supersetAdapter';

const LinkRow = styled.div`
  display: flex;
  justify-content: flex-end;
  align-items: center;
  margin-bottom: ${({ theme }) => theme.sizeUnit * 2}px;
`;

const LinkText = styled.span<{ $interactive: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 500;
  color: ${({ theme }) => theme.colorPrimary};
  cursor: ${({ $interactive }) => ($interactive ? 'pointer' : 'default')};
  text-decoration: none;
`;

interface ViewAllLinkProps {
  label: string;
  url?: string;
}

// This is `chrome.actions`, not the region's title -- `chrome.title` is
// "plain", so "Recent Activity" itself is left for Superset's own header.
// Superset's plain header has no slot for a custom link, so this renders
// as the first row of the component body instead.
export default function ViewAllLink({ label, url }: ViewAllLinkProps) {
  const theme = useTheme();
  const content = (
    <LinkText $interactive={Boolean(url)}>
      {label}
      <svg
        width={14}
        height={14}
        viewBox="0 0 24 24"
        fill="none"
        stroke={theme.colorPrimary}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M5 12h14" />
        <path d="M13 6l6 6-6 6" />
      </svg>
    </LinkText>
  );
  return (
    <LinkRow data-testid="activity-feed-view-all">
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          style={{ textDecoration: 'none', display: 'inline-flex' }}
        >
          {content}
        </a>
      ) : (
        content
      )}
    </LinkRow>
  );
}
