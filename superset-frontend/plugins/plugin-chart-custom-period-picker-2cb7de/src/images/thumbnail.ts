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

// Inline data URI so the package ships a thumbnail without a binary asset and
// without depending on the host webpack image loader.
const thumbnail =
  'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIzMjAiIGhlaWdodD0iMTgwIj48cmVjdCB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgZmlsbD0id2hpdGUiLz48cmVjdCB4PSI4MCIgeT0iNzAiIHdpZHRoPSIxNjAiIGhlaWdodD0iNDAiIHJ4PSIxMCIgZmlsbD0id2hpdGUiIHN0cm9rZT0iZ3JheSIvPjx0ZXh0IHg9IjEwMCIgeT0iOTYiIGZvbnQtZmFtaWx5PSJzYW5zLXNlcmlmIiBmb250LXNpemU9IjE2IiBmaWxsPSJncmF5Ij5TZXB0ZW1iZXIgMjAyNTwvdGV4dD48L3N2Zz4=';

export default thumbnail;
