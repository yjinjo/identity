import logging
from datetime import datetime
from typing import Dict, List, Union

from mongoengine import QuerySet
from spaceone.core.error import ERROR_INVALID_PARAMETER, ERROR_NOT_FOUND
from spaceone.core.service import (
    BaseService,
    authentication_handler,
    authorization_handler,
    event_handler,
    mutation_handler,
    transaction,
)
from spaceone.core.service.utils import (
    append_keyword_filter,
    append_query_filter,
    convert_model,
)

from spaceone.identity.error.error_role import (
    ERROR_NOT_ALLOWED_ROLE_TYPE,
    ERROR_NOT_ALLOWED_USER_STATE,
)
from spaceone.identity.manager.role_binding_manager import RoleBindingManager
from spaceone.identity.manager.role_manager import RoleManager
from spaceone.identity.manager.user_manager import UserManager
from spaceone.identity.manager.workspace_group_manager import WorkspaceGroupManager
from spaceone.identity.manager.workspace_group_user_manager import (
    WorkspaceGroupUserManager,
)
from spaceone.identity.manager.workspace_manager import WorkspaceManager
from spaceone.identity.model import WorkspaceGroup
from spaceone.identity.model.workspace_group.database import WorkspaceGroupUser
from spaceone.identity.model.workspace_group.request import (
    WorkspaceGroupAddUsersRequest,
    WorkspaceGroupCreateRequest,
    WorkspaceGroupDeleteRequest,
    WorkspaceGroupGetRequest,
    WorkspaceGroupRemoveUsersRequest,
    WorkspaceGroupSearchQueryRequest,
    WorkspaceGroupStatQueryRequest,
    WorkspaceGroupUpdateRequest,
    WorkspaceGroupUpdateRoleRequest,
)
from spaceone.identity.model.workspace_group.response import (
    WorkspaceGroupResponse,
    WorkspaceGroupsResponse,
)
from spaceone.identity.model.workspace_group_user.request import (
    WorkspaceGroupUserAddRequest,
)
from spaceone.identity.service.role_binding_service import RoleBindingService

_LOGGER = logging.getLogger(__name__)


@authentication_handler
@authorization_handler
@mutation_handler
@event_handler
class WorkspaceGroupService(BaseService):
    resource = "WorkspaceGroup"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace_group_mgr = WorkspaceGroupManager()
        self.workspace_group_user_mgr = WorkspaceGroupUserManager()
        self.workspace_mgr = WorkspaceManager()
        self.user_mgr = UserManager()
        self.role_mgr = RoleManager()
        self.rb_mgr = RoleBindingManager()
        self.rb_svc = RoleBindingService()

    @transaction(
        permission="identity:WorkspaceGroup.write", role_types=["DOMAIN_ADMIN"]
    )
    @convert_model
    def create(
        self, params: WorkspaceGroupCreateRequest
    ) -> Union[WorkspaceGroupResponse, dict]:
        """Create workspace group
        Args:
            params (WorkspaceGroupCreateRequest): {
                'name': 'str',                  # required
                'tags': 'dict',
                'workspace_id': 'str',          # injected from auth
                'domain_id': 'str',             # injected from auth (required)
            }
        Returns:
            WorkspaceGroupResponse:
        """
        params_data = params.dict(exclude_unset=True)
        params_data["created_by"] = self.transaction.get_meta("authorization.audience")
        params_data["workspace_count"] = 0
        workspace_group_vo = self.workspace_group_mgr.create_workspace_group(
            params_data
        )
        return WorkspaceGroupResponse(**workspace_group_vo.to_dict())

    @transaction(
        permission="identity:WorkspaceGroup.write", role_types=["DOMAIN_ADMIN"]
    )
    @convert_model
    def update(
        self, params: WorkspaceGroupUpdateRequest
    ) -> Union[WorkspaceGroupResponse, dict]:
        """Update workspace group name and tags
        Args:
            params (WorkspaceGroupUpdateRequest): {
                'workspace_group_id': 'str',    # required
                'name': 'str',
                'tags': 'dict',
                'workspace_id': 'str',          # injected from auth
                'domain_id': 'str',             # injected from auth (required)
        Returns:
            WorkspaceGroupResponse:
        """
        workspace_group_vo = self.workspace_group_mgr.get_workspace_group(
            params.workspace_group_id, params.domain_id
        )

        params_data = params.dict(exclude_unset=True)
        params_data["updated_by"] = self.transaction.get_meta("authorization.audience")
        params_data["updated_at"] = datetime.utcnow()

        workspace_group_vo = self.workspace_group_mgr.update_workspace_group_by_vo(
            params_data, workspace_group_vo
        )

        return WorkspaceGroupResponse(**workspace_group_vo.to_dict())

    @transaction(
        permission="identity:WorkspaceGroup.write", role_types=["DOMAIN_ADMIN"]
    )
    @convert_model
    def delete(self, params: WorkspaceGroupDeleteRequest) -> None:
        """Delete workspace group
        Args:
            params (WorkspaceGroupDeleteRequest): {
                'workspace_group_id': 'str',    # required
                'workspace_id': 'str',          # injected from auth
                'domain_id': 'str',             # injected from auth (required)
            }
        Returns:
            None
        """
        workspace_group_vo = self.workspace_group_mgr.get_workspace_group(
            params.workspace_group_id, params.domain_id
        )

        self.workspace_group_mgr.delete_workspace_group_by_vo(workspace_group_vo)

    @transaction(
        permission="identity:WorkspaceGroup.write", role_types=["DOMAIN_ADMIN"]
    )
    @convert_model
    def add_users(
        self, params: WorkspaceGroupAddUsersRequest
    ) -> Union[WorkspaceGroupResponse, dict]:
        """Add users to workspace group
        Args:
            params (WorkspaceGroupAddUsersRequest): {
                'workspace_group_id': 'str',      # required
                'users': [                        # required
                    {
                        'user_id': 'str',         # required
                        'role_id': 'str',         # required
                    }
                ],
                'workspace_id': 'str',            # injected from auth
                'domain_id': 'str',               # injected from auth (required)
            }
        Returns:
           WorkspaceGroupResponse:
        """
        return self.process_add_users(params, role_type="DOMAIN_ADMIN")

    @transaction(
        permission="identity:WorkspaceGroup.write", role_types=["DOMAIN_ADMIN"]
    )
    @convert_model
    def remove_users(
        self, params: WorkspaceGroupRemoveUsersRequest
    ) -> Union[WorkspaceGroupResponse, dict]:
        """Remove users from workspace group
        Args:
            params (WorkspaceGroupRemoveUsersRequest): {
                'workspace_group_id': 'str',         # required
                'users': [
                    'user_id': 'str'
                ],                                   # required
                'workspace_id': 'str',               # injected from auth
                'domain_id': 'str',                  # injected from auth (required)
            }
        Returns:
            WorkspaceGroupResponse:
        """
        workspace_id = params.workspace_id
        workspace_group_id = params.workspace_group_id
        users = params.users
        domain_id = params.domain_id

        old_user_ids, user_ids = self.workspace_group_mgr.get_unique_user_ids(
            users, workspace_group_id, domain_id
        )

        self.workspace_group_mgr.check_user_ids_exist_in_workspace_group(
            old_user_ids, user_ids
        )

        workspace_group_vo = self.workspace_group_mgr.get_workspace_group(
            params.workspace_group_id, params.domain_id
        )
        workspace_group_dict = workspace_group_vo.to_mongo().to_dict()
        old_users = workspace_group_dict["users"]
        updated_users = self.remove_users_from_workspace_group(
            user_ids, old_users, workspace_group_id, domain_id, workspace_id
        )
        params.users = updated_users

        workspace_group_vo = self.workspace_group_mgr.update_workspace_group_by_vo(
            params.dict(exclude_unset=True), workspace_group_vo
        )

        return WorkspaceGroupResponse(**workspace_group_vo.to_dict())

    @transaction(
        permission="identity:WorkspaceGroup.write", role_types=["DOMAIN_ADMIN"]
    )
    @convert_model
    def update_role(
        self, params: WorkspaceGroupUpdateRoleRequest
    ) -> Union[WorkspaceGroupResponse, dict]:
        """Update workspace group's user's role

        Args:
            params (WorkspaceGroupUpdateRoleRequest): {
                'workspace_group_id': 'str',        # required
                'user_id': 'str',                   # required
                'role_id': 'str',                   # required
                'workspace_id': 'str',              # injected from auth
                'domain_id': 'str',                 # injected from auth (required)
            }
        Returns:
            WorkspaceGroupResponse:
        """
        workspace_group_id = params.workspace_group_id
        user_id = params.user_id
        role_id = params.role_id
        domain_id = params.domain_id

        workspace_group_vo = self.workspace_group_mgr.get_workspace_group(
            workspace_group_id, domain_id
        )
        user_vo = self.user_mgr.get_user(user_id, domain_id)
        old_user_id = user_vo.user_id
        old_user_state = user_vo.state
        self.check_user_state(old_user_id, old_user_state)

        role_vo = self.role_mgr.get_role(params.role_id, params.domain_id)
        role_type = role_vo.role_type
        self.check_role_type(role_type)
        self.update_user_role_of_workspace_group(
            role_id, role_type, user_id, workspace_group_id, domain_id
        )

        update_workspace_group_params = {"users": workspace_group_vo.users or []}
        for user_info in update_workspace_group_params.get("users", []):
            if user_info["user_id"] == user_vo.user_id:
                user_info["role_id"] = role_id
                user_info["role_type"] = role_type
                break

        workspace_group_vo = self.workspace_group_mgr.update_workspace_group_by_vo(
            update_workspace_group_params, workspace_group_vo
        )

        return WorkspaceGroupResponse(**workspace_group_vo.to_dict())

    @transaction(permission="identity:WorkspaceGroup.read", role_types=["DOMAIN_ADMIN"])
    @convert_model
    def get(
        self, params: WorkspaceGroupGetRequest
    ) -> Union[WorkspaceGroupResponse, dict]:
        """Get workspace group

        Args:
            params (WorkspaceGroupGetRequest): {
                'workspace_group_id': 'str', # required
                'workspace_id': 'str',       # injected from auth
                'domain_id': 'str',          # injected from auth (required)
            }
        Returns:
            WorkspaceGroupResponse:
        """
        workspace_group_id = params.workspace_group_id
        domain_id = params.domain_id

        workspace_group_vo = self.workspace_group_mgr.get_workspace_group(
            workspace_group_id, domain_id
        )

        workspace_group_user_ids = []
        if workspace_group_vo.users:
            old_users, new_users = self.workspace_group_mgr.get_unique_user_ids(
                workspace_group_vo.users, workspace_group_id, domain_id
            )

            workspace_group_user_ids: List[str] = old_users + new_users

        workspace_group_dict = self.add_user_name_and_state_to_users(
            workspace_group_user_ids, workspace_group_vo, domain_id
        )
        return WorkspaceGroupResponse(**workspace_group_dict)

    @transaction(permission="identity:WorkspaceGroup.read", role_types=["DOMAIN_ADMIN"])
    @append_query_filter(["workspace_group_id", "name", "domain_id"])
    @append_keyword_filter(["workspace_group_id", "name"])
    @convert_model
    def list(
        self, params: WorkspaceGroupSearchQueryRequest
    ) -> Union[WorkspaceGroupsResponse, dict]:
        """List workspace groups
        Args:
            params (WorkspaceGroupSearchQueryRequest): {
                'query': 'dict (spaceone.api.core.v1.Query)',
                'workspace_group_id': 'str',         # required
                'name': 'str',
                'created_by': 'str',
                'updated_by': 'str',
                'workspace_id': 'str',               # injected from auth
                'domain_id': 'str',                  # injected from auth (required)
            }
        Returns:
            WorkspaceGroupsResponse:
        """
        query = params.query

        workspace_group_vos, total_count = (
            self.workspace_group_mgr.list_workspace_groups(query)
        )

        workspace_groups_info = []
        for workspace_group_vo in workspace_group_vos:
            workspace_group_users = workspace_group_vo.users or []
            old_users = list(
                set(
                    [user_info["user_id"] for user_info in workspace_group_users]
                    if workspace_group_users
                    else []
                )
            )
            new_users = list(
                set([user_info["user_id"] for user_info in workspace_group_users])
            )

            workspace_group_user_ids: List[str] = old_users + new_users

            workspace_group_dict = self.add_user_name_and_state_to_users(
                workspace_group_user_ids, workspace_group_vo, params.domain_id
            )
            workspace_groups_info.append(workspace_group_dict)

        return WorkspaceGroupsResponse(
            results=workspace_groups_info, total_count=total_count
        )

    @transaction(permission="identity:WorkspaceGroup.read", role_types=["DOMAIN_ADMIN"])
    @append_query_filter(["workspace_id", "workspace_group_id", "domain_id"])
    @convert_model
    def stat(self, params: WorkspaceGroupStatQueryRequest) -> dict:
        """Stat workspace groups
        Args:
            params (WorkspaceGroupStatQueryRequest): {
                'query': 'dict (spaceone.api.core.v1.StatisticsQuery)', # required
                'workspace_id': 'str',             # injected from auth
                'domain_id': 'str',                # injected from auth (required)
            }
        Returns:
            dict: {
                'results': 'list',
                'total_count': 'int'
            }
        """
        query = params.query

        return self.workspace_group_mgr.stat_workspace_group(query)

    def process_add_users(
        self,
        params: Union[WorkspaceGroupAddUsersRequest, WorkspaceGroupUserAddRequest],
        role_type: str,
    ) -> WorkspaceGroupResponse:
        domain_id = params.domain_id
        workspace_group_id = params.workspace_group_id
        new_users_info_list = params.users

        old_user_ids, new_user_ids = self.workspace_group_mgr.get_unique_user_ids(
            new_users_info_list, workspace_group_id, domain_id
        )
        self.workspace_group_mgr.check_new_users_already_in_workspace_group(
            old_user_ids, new_user_ids
        )
        self.check_new_users_exist_in_domain(new_user_ids, domain_id)

        workspace_group_vo = self.workspace_group_mgr.get_workspace_group(
            workspace_group_id, domain_id
        )

        if role_type == "USER":
            user_id = params.user_id
            user_vo = self.user_mgr.get_user(user_id, domain_id)

            # Role type USER has two roles: DOMAIN_ADMIN and USER
            if user_vo.role_type == "USER":
                workspace_group_old_users_info = workspace_group_vo.users or []
                if workspace_group_old_users_info:
                    self.workspace_group_user_mgr.check_user_role_type(
                        workspace_group_old_users_info, user_id
                    )

        new_users_role_map = self.get_role_map(new_users_info_list, domain_id)
        workspace_group_workspace_ids = self.get_workspace_ids(
            workspace_group_id, domain_id
        )
        if workspace_group_workspace_ids:
            self.delete_workspace_users_role_binding(
                new_user_ids, workspace_group_workspace_ids, domain_id
            )

        users_info_list = self.get_users_info_list(
            new_users_info_list,
            new_users_role_map,
            workspace_group_workspace_ids,
            workspace_group_vo,
            domain_id,
        )
        params.users = users_info_list

        workspace_group_vo = self.workspace_group_mgr.update_workspace_group_by_vo(
            params.dict(exclude_unset=True), workspace_group_vo
        )

        workspace_group_user_ids: List[str] = old_user_ids + new_user_ids
        workspace_group_user_info = self.add_user_name_and_state_to_users(
            workspace_group_user_ids, workspace_group_vo, domain_id
        )

        return WorkspaceGroupResponse(**workspace_group_user_info)

    def check_new_users_exist_in_domain(
        self, new_users: List[str], domain_id: str
    ) -> None:
        user_vos = self.user_mgr.filter_users(user_id=new_users, domain_id=domain_id)
        if not user_vos.count() == len(new_users):
            raise ERROR_NOT_FOUND(key="user_id", value=new_users)

    def get_role_map(
        self, users: List[Dict[str, str]], domain_id: str
    ) -> Dict[str, str]:
        role_ids = list(set([user["role_id"] for user in users]))
        role_vos = self.role_mgr.filter_roles(
            role_id=role_ids,
            domain_id=domain_id,
            role_type=["WORKSPACE_OWNER", "WORKSPACE_MEMBER"],
        )
        role_map = {role_vo.role_id: role_vo.role_type for role_vo in role_vos}

        for role_id in role_ids:
            if role_id not in role_map:
                raise ERROR_INVALID_PARAMETER(
                    key=role_id, reason=f"{role_id} is invalid."
                )

        return role_map

    def get_workspace_ids(self, workspace_group_id: str, domain_id: str) -> List[str]:
        workspace_vos = self.workspace_mgr.filter_workspaces(
            workspace_group_id=workspace_group_id, domain_id=domain_id
        )
        workspace_ids = [workspace_vo.workspace_id for workspace_vo in workspace_vos]

        return workspace_ids

    def delete_workspace_users_role_binding(
        self,
        new_users: List[str],
        workspace_group_workspace_ids: List[str],
        domain_id: str,
    ) -> None:
        rb_vos = self.rb_mgr.filter_role_bindings(
            user_id=new_users,
            workspace_id=workspace_group_workspace_ids,
            domain_id=domain_id,
        )
        for rb_vo in rb_vos:
            self.rb_mgr.delete_role_binding_by_vo(rb_vo)

    def add_users_to_workspace_group(
        self,
        new_users_info_list: List[Dict[str, str]],
        new_users_role_map: Dict[str, str],
        workspace_group_workspace_ids: List[str],
        workspace_group_id: str,
        domain_id: str,
    ) -> List[Dict[str, str]]:
        workspace_group_new_users_info_list = []
        unique_user_ids = set()

        def add_user(user_info, workspace_group_workspace_id=None):
            if user_info["user_id"] not in unique_user_ids:
                role_type = new_users_role_map[user_info["role_id"]]
                user_data = {
                    "user_id": user_info["user_id"],
                    "role_id": user_info["role_id"],
                    "role_type": role_type,
                }

                if workspace_group_workspace_id:
                    role_binding_params = {
                        **user_data,
                        "resource_group": "WORKSPACE",
                        "domain_id": domain_id,
                        "workspace_group_id": workspace_group_id,
                        "workspace_id": workspace_group_workspace_id,
                    }
                    new_user_rb_vo = self.rb_svc.create_role_binding(
                        role_binding_params
                    )
                    user_data = {
                        "user_id": new_user_rb_vo.user_id,
                        "role_id": new_user_rb_vo.role_id,
                        "role_type": new_user_rb_vo.role_type,
                    }
                workspace_group_new_users_info_list.append(user_data)
                unique_user_ids.add(user_data["user_id"])

        if workspace_ids := workspace_group_workspace_ids:
            for workspace_id in workspace_ids:
                for new_user_info in new_users_info_list:
                    add_user(new_user_info, workspace_id)
        else:
            for new_user_info in new_users_info_list:
                add_user(new_user_info)

        return workspace_group_new_users_info_list

    def add_user_name_and_state_to_users(
        self,
        workspace_group_user_ids: List[str],
        workspace_group_info: Union[WorkspaceGroup, Dict[str, str]],
        domain_id: str,
    ) -> Dict[str, str]:
        """Add user's name and state to users in workspace group.
        Since the user's name and state are not in user of workspace group in database,
        we need to add user's name and state to users in the Application layer.
        Args:
            workspace_group_user_ids: 'List[str]'
            workspace_group_info: 'Union[WorkspaceGroup, Dict[str, str]]'
            domain_id: 'str'
        Returns:
            workspace_group_info: 'Dict[str, str]'
        """

        def get_users(workspace_group_user_info: Union[WorkspaceGroup, Dict[str, str]]):
            if isinstance(workspace_group_user_info, dict):
                return workspace_group_user_info.get("users", [])
            else:
                return workspace_group_user_info.users or []

        def create_user_info_map(
            user_vos_param: QuerySet,
        ) -> Dict[str, Dict[str, str]]:
            user_info_dict = {}
            for user_vo in user_vos_param:
                user_info_dict[user_vo.user_id] = {
                    "name": user_vo.name,
                    "state": user_vo.state,
                }
            return user_info_dict

        def update_user_info(
            user: Union[WorkspaceGroupUser, Dict[str, str]],
            user_info_dict: Dict[str, Dict[str, str]],
        ) -> Dict[str, str]:
            if isinstance(user, dict):
                user_id = user.get("user_id", "")
            else:
                user_id = getattr(user, "user_id", "") or ""
                user = user.to_mongo().to_dict()

            user_info = user_info_dict.get(user_id, {})

            user.update(
                {
                    "user_name": user_info.get("name", ""),
                    "state": user_info.get("state", ""),
                }
            )

            return user

        workspace_group_users = get_users(workspace_group_info)
        user_vos = self.user_mgr.filter_users(
            user_id=workspace_group_user_ids, domain_id=domain_id
        )
        user_info_map = create_user_info_map(user_vos)

        if workspace_group_users:
            updated_users = [
                update_user_info(user, user_info_map) for user in workspace_group_users
            ]
            workspace_group_info.users = updated_users
            return workspace_group_info.to_dict()

    def get_users_info_list(
        self,
        new_users_info_list: List[Dict[str, str]],
        new_users_role_map: Dict[str, str],
        workspace_group_workspace_ids: List[str],
        workspace_group_vo: WorkspaceGroup,
        domain_id: str,
    ) -> List[Dict[str, str]]:
        workspace_group_old_users_info_list = workspace_group_vo.users or []
        workspace_group_new_users_info_list = self.add_users_to_workspace_group(
            new_users_info_list,
            new_users_role_map,
            workspace_group_workspace_ids,
            workspace_group_vo.workspace_group_id,
            domain_id,
        )
        return workspace_group_old_users_info_list + workspace_group_new_users_info_list

    def remove_users_from_workspace_group(
        self,
        user_ids: List[str],
        old_users: List[Dict[str, str]],
        workspace_group_id: str,
        domain_id: str,
        workspace_id: str = None,
    ) -> List[Dict[str, str]]:
        rb_vos = self.rb_mgr.filter_role_bindings(
            user_id=user_ids,
            workspace_group_id=workspace_group_id,
            domain_id=domain_id,
        )

        if rb_vos.count() > 0:
            for rb_vo in rb_vos:
                self.rb_mgr.delete_role_binding_by_vo(rb_vo)

        updated_users = [user for user in old_users if user["user_id"] not in user_ids]

        if not workspace_id:
            workspace_vos = self.workspace_mgr.filter_workspaces(
                workspace_group_id=workspace_group_id, domain_id=domain_id
            )
            for workspace_vo in workspace_vos:
                user_rb_ids = self.rb_mgr.stat_role_bindings(
                    query={
                        "distinct": "user_id",
                        "filter": [
                            {
                                "k": "workspace_id",
                                "v": workspace_vo.workspace_id,
                                "o": "eq",
                            },
                            {"k": "domain_id", "v": domain_id, "o": "eq"},
                        ],
                    }
                ).get("results", [])
                user_rb_total_count = len(user_rb_ids)

                self.workspace_mgr.update_workspace_by_vo(
                    {"user_count": user_rb_total_count}, workspace_vo
                )
        else:
            workspace_vo = self.workspace_mgr.get_workspace(workspace_id, domain_id)
            if workspace_vo:
                user_rb_ids = self.rb_mgr.stat_role_bindings(
                    query={
                        "distinct": "user_id",
                        "filter": [
                            {"k": "workspace_id", "v": workspace_id, "o": "eq"},
                            {"k": "domain_id", "v": domain_id, "o": "eq"},
                        ],
                    }
                ).get("results", [])
                user_rb_total_count = len(user_rb_ids)

                self.workspace_mgr.update_workspace_by_vo(
                    {"user_count": user_rb_total_count}, workspace_vo
                )

        return updated_users

    @staticmethod
    def check_user_state(old_user_id: str, old_user_state: str) -> None:
        if old_user_state in ["DISABLED", "DELETED"]:
            _LOGGER.error(f"User ID {old_user_id}'s state is {old_user_state}.")
            raise ERROR_NOT_ALLOWED_USER_STATE(
                user_id=old_user_id, state=old_user_state
            )

    @staticmethod
    def check_role_type(role_type: str) -> None:
        if role_type not in ["WORKSPACE_OWNER", "WORKSPACE_MEMBER"]:
            raise ERROR_NOT_ALLOWED_ROLE_TYPE()

    def update_user_role_of_workspace_group(
        self,
        role_id: str,
        role_type: str,
        user_id: str,
        workspace_group_id: str,
        domain_id: str,
    ) -> None:
        role_binding_vos = self.rb_mgr.filter_role_bindings(
            user_id=user_id,
            workspace_group_id=workspace_group_id,
            domain_id=domain_id,
        )

        for role_binding_vo in role_binding_vos:
            role_binding_vo.update({"role_id": role_id, "role_type": role_type})
