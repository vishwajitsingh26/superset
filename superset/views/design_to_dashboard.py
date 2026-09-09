# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from flask_appbuilder import expose, has_access
from flask_appbuilder.hooks import before_request
from werkzeug.exceptions import NotFound

from superset import is_feature_enabled
from superset.constants import MODEL_VIEW_RW_METHOD_PERMISSION_MAP
from superset.superset_typing import FlaskResponse
from superset.views.base import BaseSupersetView


class DesignToDashboardView(BaseSupersetView):
    """Serves the Design-to-Dashboard SPA shell.

    The frontend route is registered in
    ``superset-frontend/src/views/routes.tsx`` behind the same feature flag.
    """

    route_base = "/design-to-dashboard"
    class_permission_name = "DesignToDashboard"
    method_permission_name = MODEL_VIEW_RW_METHOD_PERMISSION_MAP

    @staticmethod
    def is_enabled() -> bool:
        return is_feature_enabled("DESIGN_TO_DASHBOARD")

    @before_request
    def ensure_enabled(self) -> None:
        if not self.is_enabled():
            raise NotFound()

    @expose("/")
    @has_access
    def list(self) -> FlaskResponse:
        return super().render_app_template()
